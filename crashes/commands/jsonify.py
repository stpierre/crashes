"""Extract the description from all downloaded reports."""

import collections
import datetime
import glob
import json
import multiprocessing
import operator
import os
import re
import traceback

from pdfminer import converter as pdfconverter
from pdfminer import layout as pdflayout
from pdfminer import pdfdocument
from pdfminer import pdfinterp
from pdfminer import pdfpage
from pdfminer import pdfparser
from pdfminer import psparser
from six.moves import queue

from crashes import log
from crashes.commands import base
from crashes.commands import fetch

LOG = log.getLogger(__name__)


def get_text(obj):
    """Get the text content of an object, whatever that means."""
    if hasattr(obj, "get_text"):
        return obj.get_text()
    else:
        try:
            return "".join(get_text(c) for c in obj)
        except TypeError:
            return ""


class LocatorAdjustment(collections.Iterable):
    """A set of coordinate pairs representing an area in a PDF."""

    def __init__(self, xmin, xmax, ymin, ymax):
        self.xmin = xmin
        self.xmax = xmax
        self.ymin = ymin
        self.ymax = ymax

    def __repr__(self):
        return "%s(xmin=%s, xmax=%s, ymin=%s, ymax=%s)" % (
            self.__class__.__name__,
            self.xmin, self.xmax, self.ymin, self.ymax)

    @staticmethod
    def _min(num1, num2):
        """min() function that considers all numbers > None.

        None is less than all numbers by default, but for
        LocatorAdjustments we want to discard a None value as soon as
        we have a real number -- any real number -- to replace it
        with.
        """
        if num1 is None:
            return num2
        elif num2 is None:
            return num1
        else:
            return min(num1, num2)

    @staticmethod
    def _max(num1, num2):
        """max() function for symmetricity.

        max() works just fine with None values, but since we provide
        _min() it's nice to provide _max() as well.
        """
        return max(num1, num2)

    def contains(self, obj):
        """Whether or not an object is contained within the bounds."""
        return ((self.ymin is None or obj.y0 > self.ymin) and
                (self.ymax is None or obj.y1 < self.ymax) and
                (self.xmin is None or obj.x0 > self.xmin) and
                (self.xmax is None or obj.x1 < self.xmax))

    def expand_limits(self, other):
        """Expand the limits of this object with the limits of another.

        Each limit is set to the more prominent value -- i.e., the
        lesser value for minima, the greater value for maxima.
        """
        self.xmin = self._min(other.xmin, self.xmin)
        self.xmax = self._max(other.xmax, self.xmax)
        self.ymin = self._min(other.ymin, self.ymin)
        self.ymax = self._max(other.ymax, self.ymax)

    def contract_limits(self, other):
        """Contract the limits of this object to the limits of another.

        Each limit is set to the less prominent value -- i.e., the
        greater value for minima, the lesser value for maxima.
        """
        self.xmin = self._max(other.xmin, self.xmin)
        self.xmax = self._min(other.xmax, self.xmax)
        self.ymin = self._max(other.ymin, self.ymin)
        self.ymax = self._min(other.ymax, self.ymax)

    def __iter__(self):
        for item in (self.xmin, self.xmax, self.ymin, self.ymax):
            yield item


class Locator(object):
    """Abstract class for PDF locators.

    Locator classes are used to find fields in a PDF by reference to
    the other known fields. See the concrete implementations below for
    examples.

    A concrete Locator object consists of a pattern to match, and how
    to adjust the location of the desired field by the location of
    that pattern. For instance, the 'name' field might be to the right
    of the known text "Name:"; a locator could be used to express this
    relationship. Locators can be combined with other criteria in a
    PDFFinder class.
    """

    def __init__(self, pattern, fuzz=0):
        # pattern can either be a compiled regex, or a string
        # describing a regex
        if not hasattr(pattern, "search"):
            pattern = re.compile(pattern)
        self._pattern = pattern
        self.fuzz = fuzz
        self._adj = LocatorAdjustment(None, None, None, None)

    def matches(self, text):
        """Whether or not the pattern matches the given text."""
        return bool(self._pattern.search(text))

    def check_text(self, obj):
        """Expand limits if obj matches the pattern.

        If the text in the given object matches this Locator's
        pattern, then the bounds are expanded to the location of the
        object and True is returned. Otherwise, False is returned.
        """
        text = get_text(obj)
        if self.matches(text):
            self._adj.expand_limits(self.set_by_object(obj))
            return True
        return False

    def reset(self):
        """Reset the bounds of this locator so it can be reused."""
        self._adj = LocatorAdjustment(None, None, None, None)

    @property
    def bounds(self):
        """Get a LocatorAdjustment containing this Locator's bounds."""
        xmin = self._adj.xmin - self.fuzz if self._adj.xmin else None
        xmax = self._adj.xmax + self.fuzz if self._adj.xmax else None
        ymin = self._adj.ymin - self.fuzz if self._adj.ymin else None
        ymax = self._adj.ymax + self.fuzz if self._adj.ymax else None
        return LocatorAdjustment(xmin, xmax, ymin, ymax)

    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__, self._pattern.pattern)

    def set_by_object(self, obj):
        """Return a LocatorAdjustment based on the given object.

        This must be implemented by concrete Locator implementations,
        which will determine for themselves how to adjust the bounds.
        """
        raise NotImplementedError


class LeftOf(Locator):
    """Field is left of objects matching the pattern.

    Does not imply any vertical alignment; this only sets the maximum
    X value.
    """

    def set_by_object(self, obj):
        return LocatorAdjustment(None, obj.x0, None, None)


class RightOf(Locator):
    """Field is right of objects matching the pattern.

    Does not imply any vertical alignment; this only sets the minimum
    X value.
    """

    def set_by_object(self, obj):
        return LocatorAdjustment(obj.x1, None, None, None)


class Above(Locator):
    """Field is above objects matching the pattern.

    Does not imply any horizontal alignment; this only sets the
    minimum Y value. (Note that the Y axis in PDFs is "backwards"; the
    bottom left of the page is (0, 0), while the top right is
    (1000,600) or something like that.)
    """

    def set_by_object(self, obj):
        return LocatorAdjustment(None, None, obj.y1, None)


class Below(Locator):
    """Field is below objects matching the pattern.

    Does not imply any horizontal alignment; this only sets the
    maximum Y value.
    """

    def set_by_object(self, obj):
        return LocatorAdjustment(None, None, None, obj.y0)


class AlignedWith(Locator):
    """Field is aligned horizontally with objects matching the pattern.

    The field may be on either side of (or even on top of) the
    objects. No horizontal position is implied. This only sets the Y
    values.
    """

    def set_by_object(self, obj):
        return LocatorAdjustment(None, None, obj.y0, obj.y1)


class VAlignedWith(Locator):
    """Field is aligned vertically with objects matching the pattern.

    The field may be on above or below (or even on top of) the
    objects. No vertical position is implied. This only sets the X
    values.
    """

    def set_by_object(self, obj):
        return LocatorAdjustment(obj.x0, obj.x1, None, None)


class NotFound(Exception):
    """Raised when PDFFinder cannot find a datum in a page."""


class PDFFinder(object):
    """Find text in a PDF based on Locators and other criteria."""

    newline_re = re.compile(r'\n')
    _sentinel = object()

    def __init__(self, name, locators, minpage=None, maxpage=None, type=None,
                 multiple=False, default=_sentinel, serialize=None,
                 short_circuit=False):
        self.name = name
        self.locators = locators
        self.minpage = minpage
        self.maxpage = maxpage
        self.type = type
        self.multiple = multiple
        self.short_circuit = short_circuit
        if multiple:
            self._default = []
        else:
            self._default = default
        self._data = self._default
        if serialize is None:
            self.serialize = lambda v: v
        else:
            self.serialize = serialize

    @property
    def bounds(self):
        """Get the coordinate bounds for possible fields.

        This is based only on minpage/maxpage and the locators.
        """
        bounds = LocatorAdjustment(None, None, None, None)
        for locator in self.locators:
            bounds.contract_limits(locator.bounds)
        return bounds

    def _get_bounded_objects(self, layout, page=None):
        """Get all objects within the bounds that are not locators.

        This returns all objects within the bounds determined by the
        Locators given to this PDFFinder, which are not themselves
        used to determine the bounds. (This is only an issue with PDF
        objects that are both used to determine the bounds and are
        within them, e.g., potentially AlignedWith and VAlignedWith
        Locators.)
        """
        if (page is not None and (self.minpage or self.maxpage) and
                ((self.minpage is not None and page < self.minpage) or
                 (self.maxpage is not None and page > self.maxpage))):
            return

        for locator in self.locators:
            locator.reset()

        locator_objs = []
        missing_locators = self.locators[:]
        for obj in layout:
            for locator in missing_locators[:]:
                if locator.check_text(obj):
                    logtext = self.newline_re.sub(r'\\n', get_text(obj))
                    LOG.debug("Found locator %s for %s on page %s: %s ('%s')" %
                              (locator, self.name, page, obj, logtext))
                    locator_objs.append(obj)
                    missing_locators.remove(locator)
        if len(missing_locators):
            LOG.info("Missing locators for %s on page %s: %s" %
                     (self.name, page, missing_locators))
            return
        LOG.debug("Found bounds for %s on page %s: %s" % (
            self.name, page, self.bounds))

        return [obj for obj in layout
                if obj not in locator_objs and self.bounds.contains(obj)]

    def get(self, layout, page=None):
        """Get the value described by this PDFFinder in the layout.

        Raises NotFound if no value is found.
        """
        LOG.debug("Finding %s on page %s" % (self.name, page))
        candidates = self._get_bounded_objects(layout, page=page)
        if not candidates:
            LOG.debug("No %s found on page %s" % (self.name, page))
            raise NotFound()
        if self.type == 'longest':
            longest = ''
            obj = None
            for candidate in candidates:
                text = get_text(candidate)
                if len(text) > len(longest):
                    longest = text
                    obj = candidate
            if longest:
                LOG.debug("Found %s on page %s: %s (%s)" %
                          (self.name, page, longest, obj))
                return longest
            else:
                LOG.debug("No %s found on page %s" % (self.name, page))
                raise NotFound()
        elif self.type:
            for candidate in candidates:
                text = get_text(candidate)
                logtext = self.newline_re.sub(r'\\n', text)
                LOG.debug("%s: Checking text '%s' against type" % (self.name,
                                                                   logtext))
                try:
                    retval = self.type(text)
                    LOG.debug("%s: Converted text '%s' to: %s" %
                              (self.name, logtext, retval))
                    LOG.debug("Found %s on page %s: %s (%s)" %
                              (self.name, page, retval, candidate))
                    return retval
                except Exception as err:
                    LOG.debug("%s: Error converting text '%s' to type: %s" %
                              (self.name, logtext, err))
            LOG.debug("No %s matches correct type on page %s" % (self.name,
                                                                 page))
            raise NotFound()
        else:
            if len(candidates) > 1:
                LOG.warning("Multiple candidates found for %s: %s" %
                            (self.name, candidates))
            obj = candidates[0]
            text = get_text(obj)
            LOG.debug("Found %s on page %s: %s (%s)" % (self.name, page,
                                                        text, obj))
            return text

    def update(self, layout, page=None):
        """Update the value stored by this PDFFinder by searching the layout.

        This is what should usually be used; a PDF can be parsed page
        by page, and each PDFFinder can be update()'d to collect the
        first value, or all values for multi-valued PDFFinders.
        """
        LOG.debug("Updating field %s" % self.name)
        try:
            if self.multiple:
                newval = self.get(layout, page=page)
                self._data.append(newval)
            elif self._data == self._default:
                self._data = self.get(layout, page=page)
        except NotFound:
            pass

        return self._data

    @property
    def value(self):
        """Get the value accumulated with update()."""
        if self._data == self._sentinel:
            return None
        try:
            return self.serialize(self._data)
        except Exception as err:
            LOG.warning("Failed to serialize %s '%s': %s" %
                        (self.name, self._data, err))
            return None


_DATE_SPLIT = re.compile(r'[-/]')


def _parse_date(text):
    """Try to parse a date in the accident report format.

    At least, it's *supposed* to be the accident report
    format. They're also supposed to use slashes, not dashes, but that
    isn't always the case.
    """
    month, day, year = _DATE_SPLIT.split(text)
    return datetime.date(int(year), int(month), int(day))


def _parse_time(text):
    """Try to parse a time in the accident report format."""
    if ":" in text:
        hours, minutes = text.split(":")
    else:
        hours = text[0:2]
        minutes = text[2:4]
    return datetime.time(int(hours), int(minutes))


def _case_number_from_filename(fpath):
    """Get the case number from a report filename."""
    case_id = os.path.splitext(os.path.basename(fpath))[0]
    case_no = "%s-%s" % (case_id[0:2], case_id[2:])
    return case_no


class JSONify(base.Command):
    """Extract the description from all downloaded reports.

    Data is saved to reports.json so it can be more easily consumed in
    the future.
    """

    prerequisites = [fetch.Fetch]

    arguments = [base.Argument("files", nargs='*'),
                 base.Argument("--processes", type=int,
                               default=multiprocessing.cpu_count()),
                 base.Argument("--reparse-curated", action="store_true")]

    def __init__(self, options):
        super(JSONify, self).__init__(options)
        self._work_queue = multiprocessing.Queue()
        self._result_queue = multiprocessing.Queue()
        self._terminate = multiprocessing.Event()
        self._data = {}
        if not self.options.files and os.path.exists(self.options.all_reports):
            self._data = json.load(open(self.options.all_reports))

    def _handle_results(self, timeout=1):
        results = []
        while True:
            try:
                result = self._result_queue.get(True, timeout)
                if result:
                    results.append(result)
            except queue.Empty:
                break
        LOG.debug("Got %s results from result queue" % len(results))

        if len(results):
            if self.options.files:
                print(json.dumps(results))
            else:
                for result in results:
                    self._data[result['case_number']] = result
                LOG.debug("Dumping case data to %s" %
                          self.options.all_reports)
                json.dump(self._data, open(self.options.all_reports, "w"))
        return results

    def __call__(self):
        if self.options.files:
            filelist = self.options.files
        elif self.options.reparse_curated:
            curation = json.load(open(self.options.curation_results))
            filelist = [os.path.join(self.options.pdfdir,
                                     self._data[case_no]['filename'])
                        for case_no in reduce(operator.add, curation.values())]
        else:
            filelist = [
                fpath
                for fpath in glob.glob(os.path.join(self.options.pdfdir, "*"))
                if _case_number_from_filename(fpath) not in self._data]

        if len(filelist) < self.options.processes:
            LOG.debug("Fewer files than processes (%s files, %s processes)" %
                      (len(filelist), self.options.processes))
        nprocs = min(len(filelist), self.options.processes)

        LOG.debug("Building %s worker processes" % nprocs)
        processes = [JSONifyChildProcess(self._terminate,
                                         self._work_queue,
                                         self._result_queue,
                                         self.options,
                                         name="jsonify-child-%s" % i)
                     for i in range(nprocs)]

        for fpath in filelist:
            self._work_queue.put(fpath)
        LOG.debug("Added %s file paths to work queue" %
                  self._work_queue.qsize())

        LOG.debug("Starting %s worker processes" % len(processes))
        for process in processes:
            process.start()

        LOG.debug("Collecting results from result queue")
        while len(processes):
            try:
                # first, collect results that are available with a
                # very short timeout
                self._handle_results()

                # see if any processes have completed
                for process in processes:
                    running = False
                    if process.is_alive():
                        process.join(1)
                        if process.is_alive():
                            running = True
                        else:
                            LOG.debug("Process %s completed" % process.name)
                    elif self._terminate:
                        LOG.debug("Process %s exited" % process.name)
                    else:
                        LOG.warn("Process %s exited unexpectedly" %
                                 process.name)
                    if not running:
                        processes.remove(process)
                LOG.debug("%s processes still running" % len(processes))
                LOG.debug("%s items still in work queue" %
                          self._work_queue.qsize())
            except (SystemExit, KeyboardInterrupt):
                LOG.info("Stopping %s processes" % len(processes))
                self._terminate.set()
            except Exception:
                self._terminate.set()
                LOG.error("Uncaught exception: %s" % traceback.format_exc())

        # handle any more results that have arrived between the time
        # that results were handled and all processes stopped.
        self._handle_results()

        self._work_queue.close()
        self._result_queue.close()

    def satisfied(self):
        return os.path.exists(self.options.all_reports)


class JSONifyChildProcess(multiprocessing.Process):
    """Child process for JSONify command."""

    injury_regions = {
        "01": "Head",
        "02": "Face",
        "03": "Neck",
        "04": "Chest",
        "05": "Back/spine",
        "06": "Shoulder/upper arm",
        "07": "Elbow/lower arm/hand",
        "08": "Abdomen/pelvis",
        "09": "Hip/upper leg",
        "10": "Knee/lower leg/foot",
        "11": "Entire body",
        "12": "Unknown",
        "13": None}

    _injured_name_re = re.compile(r'^\s*(?P<name>[^\d]*?)\s+\d')

    def __init__(self, terminate, work_queue, result_queue, options,
                 name=None):
        super(JSONifyChildProcess, self).__init__(name=name)
        self._terminate = terminate
        self._work_queue = work_queue
        self._result_queue = result_queue
        self.options = options

    def _munge_name(self, name):
        """Anonymize a name so that it can be compared but not read.

        Even though all of this is public data, I don't want to be
        "leaking" it myself. So we munge names to include just
        initials, which should be enough to uniquely identify the
        people in a collision without storing their names.
        """
        match = self._injured_name_re.match(name)
        if match:
            name = match.group("name")
        return "".join(w[0] for w in name.split())

    def _get_fields(self):
        """Get a list of PDFFinders representing the fields to find.

        This is a function (instead of, say, just a class variable)
        that returns new PDFFinder objects each time to avoid
        contaminating future search results by reusing PDFFinder
        objects.
        """
        location = PDFFinder(
            "location",
            [AlignedWith(
                r'ROAD\s+ON\s+WHICH|ACCIDENT\s+OCCURRED|STREET/\s*HIGHWAY\s+NO',
                fuzz=6),
             RightOf(r'STREET/\s*HIGHWAY\s+NO'),
             LeftOf('ONE-WAY')],
            minpage=1, maxpage=1)
        date = PDFFinder(
            "date",
            [Below(r'of\s+Vehicles', fuzz=1),
             Above(r'^COUNTY$')],
            minpage=1, maxpage=1, type=_parse_date,
            serialize=lambda d: d.strftime("%Y-%m-%d"),
            short_circuit=True)
        time = PDFFinder(
            "time",
            [RightOf(r'TIME\s+OF'),
             AlignedWith(r'TIME\s+OF', fuzz=15),
             VAlignedWith(r'In Military Time', fuzz=12),
             Below(r'In Military Time')],
            minpage=1, maxpage=1, type=_parse_time,
            serialize=lambda t: t.strftime("%H:%M"))
        report = PDFFinder(
            "report",
            [Below(
                r'DESCRIPTION\s+OF\s+ACCIDENT\s+BASED|ROAD\s+ON\s+WHICH\s+ACCIDENT\s+OCCURRED'),
             Above(r'OBJECT\s+DAMAGED|OFFICER\s+NO')],
            minpage=2, type='longest', multiple=True,
            serialize=" ".join)
        complete_str = (
            r'Complete\s+this\s+section\s+for\s+all\s+injured\s+persons')
        cyclist_dob = PDFFinder(
            "cyclist_dob",
            [VAlignedWith(r'DATE\s+OF\s+BIRTH', fuzz=25),
             Below(complete_str),
             RightOf(complete_str),
             AlignedWith("^19$", fuzz=3)],
            minpage=1, maxpage=1, type=_parse_date,
            serialize=lambda d: d.strftime("%Y-%m-%d"))
        injury_sev = PDFFinder(
            "injury_severity",
            [Below(complete_str),
             VAlignedWith(r'Sev\.', fuzz=10),
             VAlignedWith('Injury', fuzz=10),
             AlignedWith("^19$", fuzz=20)],
            minpage=1, maxpage=1, type=int)
        injury_region = PDFFinder(
            "injury_region",
            [Below(complete_str),
             VAlignedWith(r'Region', fuzz=10),
             AlignedWith("^19$", fuzz=20)],
            minpage=1, maxpage=1, type=self.injury_regions.get)
        cyclist_initials = PDFFinder(
            "cyclist_initials",
            [Below(complete_str),
             Below(r"^\s*NAME\s*$", fuzz=2),
             VAlignedWith(complete_str, fuzz=75),
             AlignedWith("^19$", fuzz=20),
             Above(r"MEDICAL\s+FACILITY\s+NAME")],
            minpage=1, maxpage=1, type=self._munge_name)

        return [location,
                date,
                time,
                report,
                cyclist_dob,
                cyclist_initials,
                injury_sev,
                injury_region]

    def _parse_pdf(self, stream):
        """Parse a single PDF and return the date and description."""
        LOG.info("Parsing accident report data from %s" % stream.name)
        fields = self._get_fields()

        try:
            # so much pdfminer boilerplate....
            document = pdfdocument.PDFDocument(pdfparser.PDFParser(stream))
            rsrcmgr = pdfinterp.PDFResourceManager()
            device = pdfconverter.PDFPageAggregator(
                rsrcmgr, laparams=pdflayout.LAParams())
            interpreter = pdfinterp.PDFPageInterpreter(rsrcmgr, device)
        except psparser.PSException as err:
            LOG.warn("Parsing %s failed, skipping: %s" % (stream.name, err))
            return dict([(f.name, f.value) for f in fields])

        page_num = 1

        for page in pdfpage.PDFPage.create_pages(document):
            LOG.debug("Parsing page %s" % page_num)

            interpreter.process_page(page)
            layout = device.get_result()

            for field in fields:
                field.update(layout, page=page_num)
                if (not field.value and field.short_circuit and
                        page_num >= field.maxpage):
                    LOG.warn("No %s found in %s, aborting parsing" %
                             (field.name, stream.name))
                    return dict([(f.name, f.value) for f in fields])

            page_num += 1
        return dict([(f.name, f.value) for f in fields])

    def _get_data(self, stream):
        case_data = self._parse_pdf(stream)
        case_data.update({
            "case_number": _case_number_from_filename(stream.name),
            "filename": os.path.basename(stream.name),
        })
        return case_data

    def run(self):
        log.setup_logging(self.options.verbose, prefix=self.name)
        while not self._terminate.is_set():
            try:
                fpath = self._work_queue.get_nowait()
                LOG.debug("Got file path from work queue: %s" % fpath)
                data = self._get_data(open(fpath, 'rb'))
                LOG.debug("Returning data for %s to results queue" % fpath)
                self._result_queue.put(data)
            except queue.Empty:
                LOG.info("Work queue is empty, exiting")
                break
            except KeyboardInterrupt:
                LOG.info("Caught Ctrl-C, exiting")
                break
