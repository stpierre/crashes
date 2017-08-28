"""Extract the description from all downloaded reports."""

from __future__ import print_function

import collections
import copy
import datetime
import glob
import itertools
import logging
import multiprocessing
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
from six.moves import input
from six.moves import queue
import yaml

from crashes.commands import base
from crashes import db
from crashes import log
from crashes import utils

LOG = logging.getLogger(__name__)

ParsedPDFObjectData = collections.namedtuple("ParsedPDFObjectData", ("name",
                                                                     "data"))


def get_text(obj):
    """Get the text content of an object, whatever that means."""
    if hasattr(obj, "get_text"):
        return obj.get_text()
    else:
        try:
            return "".join(get_text(c) for c in obj)
        except TypeError:
            return ""


def pdfobj_repr(pdfobj):
    return "%s(%r at %s)" % (pdfobj.__class__.__name__, get_text(pdfobj),
                             pdfobj.bbox)


class Converter(object):
    def __init__(self, **kwargs):
        pass

    def convert(self, data):
        raise NotImplementedError

    @staticmethod
    def load_converter(record_type):
        try:
            cls_name = record_type["class"]
            kwargs = copy.copy(record_type)
            del kwargs["class"]
        except TypeError:
            cls_name = record_type
            kwargs = {}
        return globals()[cls_name](**kwargs)


class Integer(Converter):
    def convert(self, data):
        return int(data)


class Date(Converter):
    _date_split = re.compile(r'[-/]')

    def convert(self, data):
        """Try to parse a date in the accident report format.

        At least, it's *supposed* to be the accident report
        format. They're also supposed to use slashes, not dashes, but
        that isn't always the case.
        """
        month, day, year = self._date_split.split(data)
        return datetime.date(int(year), int(month), int(day))


class Time(Converter):
    def convert(self, data):
        """Try to parse a time in the accident report format."""
        if ":" in data:
            hours, minutes = data.split(":")
        else:
            hours = data[0:2]
            minutes = data[2:4]
            return datetime.time(int(hours), int(minutes))


class Boolean(Converter):
    def convert(self, data):
        return data.lower() == "x"


class BooleanChoice(Boolean):
    # NOTE(stpierre): for now, BooleanChoice and MultipleChoice are
    # just going to act as booleans; eventually it'd be nice to
    # abstract them so that they record a single datum checked for
    # consistency, but this is sufficient for now
    pass


class MultipleChoice(Boolean):
    pass


class IntegerMapping(Integer):
    def __init__(self, values):
        super(IntegerMapping, self).__init__()
        self._values = values

    def convert(self, data):
        return self._values[super(IntegerMapping, self).convert(data)]


class PDFDocument(collections.Iterable):
    def __init__(self, filename, layout):
        self.filename = filename
        self.stream = open(filename, 'rb')
        self.document = None
        self.rsrcmgr = None
        self.device = None
        self.interpreter = None
        self.layout = layout

    def _parse(self):
        if self.interpreter is None:
            # so much pdfminer boilerplate....
            self.document = pdfdocument.PDFDocument(
                pdfparser.PDFParser(self.stream))
            self.rsrcmgr = pdfinterp.PDFResourceManager()
            self.device = pdfconverter.PDFPageAggregator(
                self.rsrcmgr, laparams=pdflayout.LAParams())
            self.interpreter = pdfinterp.PDFPageInterpreter(
                self.rsrcmgr, self.device)

    def __iter__(self):
        self._parse()

        page_num = 0
        for raw_page in pdfpage.PDFPage.create_pages(self.document):
            page_num += 1
            self.interpreter.process_page(raw_page)
            layout = self.device.get_result()
            objects = list(layout)

            try:
                LOG.debug("Instantiating page object for page %s of %s",
                          page_num, self.filename)
                yield PDFPage.factory(objects, self.layout, number=page_num)
            except UnknownPageType:
                raise UnknownPageType("%s page %s" % (self.filename, page_num))


class UnknownPageType(Exception):
    pass


class PDFPage(collections.Iterable):
    name = None
    _subclasses = None

    def __init__(self, objects, layout, number=0):
        self.objects = objects
        self.layout = layout
        self.number = number
        self.start_index = layout["start_index"].get(self.name, 0)
        self.start_y = layout["start_y"].get(self.name)

    def __iter__(self):
        for obj in self.objects[self.start_index:]:
            coords = Coordinates(*obj.bbox)
            if self.start_y and coords.ymin > self.start_y:
                continue
            yield obj

    @classmethod
    def factory(cls, objects, layout, number=0):
        for subclass in cls._get_subclasses():
            if subclass.matches(objects):
                return subclass(objects, layout, number=number)
        raise UnknownPageType()

    @classmethod
    def _get_subclasses(cls):
        if cls._subclasses is None:
            cls._subclasses = []
            for obj_name, obj in globals().items():
                if (isinstance(obj, type) and issubclass(obj, cls)
                        and obj != cls and not obj_name.startswith("_")):
                    LOG.debug("Discovered %s subclass: %s", cls.__name__,
                              obj.__name__)
                    cls._subclasses.append(obj)
        return cls._subclasses

    @classmethod
    def matches(cls, objects):
        raise NotImplementedError()


class ReportPage(PDFPage):
    name = "report"

    @classmethod
    def matches(cls, objects):
        return "Motor Vehicle  Accident  Report" in get_text(objects[0])


class DiagramPage(PDFPage):
    name = "diagram"

    @classmethod
    def matches(cls, objects):
        return get_text(
            objects[0]).startswith("THE  FOLLOWING INFORMATION  IS REQUIRED")


class AdditionalDiagramPage(PDFPage):
    name = "addl_diagram"

    @classmethod
    def matches(cls, objects):
        return get_text(objects[0]).startswith("ADDITIONAL  -  DIAGRAM")


class ContinuationPage40a(PDFPage):
    name = "40a"

    @classmethod
    def matches(cls, objects):
        return "40a" in get_text(objects[241])


class ContinuationPage40b(PDFPage):
    name = "40b"

    @classmethod
    def matches(cls, objects):
        return "40b" in get_text(objects[368])


class Coordinates(collections.Iterable):
    """A set of coordinate pairs representing an area in a PDF."""

    def __init__(self, x0, y0, x1, y1):
        self.xmin = min(x0, x1)
        self.xmax = max(x0, x1)
        self.ymin = min(y0, y1)
        self.ymax = max(y0, y1)

    def __repr__(self):
        return "%s(xmin=%s, xmax=%s, ymin=%s, ymax=%s)" % (
            self.__class__.__name__, self.xmin, self.xmax, self.ymin,
            self.ymax)

    def __eq__(self, other):
        return (abs(self.xmin - other.xmin) < 1e-6
                and abs(self.xmax - other.xmax) < 1e-6
                and abs(self.ymin - other.ymin) < 1e-6
                and abs(self.ymax - other.ymax) < 1e-6)

    def to_list(self):
        return [self.xmin, self.xmax, self.ymin, self.ymax]

    def contains(self, other, fuzz=0):
        """Whether or not an object is contained within the bounds."""
        return (other.ymax - fuzz <= self.ymax
                and other.ymin + fuzz >= self.ymin
                and other.xmax - fuzz <= self.xmax
                and other.xmin + fuzz >= self.xmin)

    def overlaps(self, other):
        """Whether or not another object overlaps this one at all."""
        return (other.xmin < self.xmax and other.xmax > self.xmin
                and other.ymin < self.ymax and other.ymax > self.ymin)

    def merge(self, other):
        if hasattr(other, "xmin"):
            return self.__class__(
                min(self.xmin, other.xmin),
                max(self.xmax, other.xmax),
                min(self.ymin, other.ymin), max(self.ymax, other.ymax))
        else:
            return self.__class__(
                min(self.xmin, other[0]),
                max(self.xmax, other[1]),
                min(self.ymin, other[2]), max(self.ymax, other[3]))

    def __iter__(self):
        for item in (self.xmin, self.xmax, self.ymin, self.ymax):
            yield item


class Parse(base.Command):
    """Extract data from all downloaded reports."""

    arguments = [
        base.Argument("files", nargs='*'),
        base.Argument(
            "--processes", type=int, default=multiprocessing.cpu_count()),
        base.Argument("--interactive", action="store_true"),
        base.Argument("--reparse-curated", action="store_true")
    ]

    def __init__(self, options):
        super(Parse, self).__init__(options)
        self._work_queue = multiprocessing.Queue()
        self._result_queue = multiprocessing.Queue()
        self._terminate = multiprocessing.Event()

    def _handle_results(self, timeout=1):
        while True:
            try:
                result = self._result_queue.get(True, timeout)
                if result:
                    LOG.debug("Got result for %(case_no)s from result queue",
                              result)
                    LOG.debug("%s items still in result queue",
                              self._result_queue.qsize())
                    self._store_one_result(result)
            except queue.Empty:
                break

    def _store_one_result(self, result):
        if self.options.files:
            print(repr(result))
        else:
            db.collisions.upsert(result)

    def _build_filelist(self):
        LOG.debug("Building list of files to parse...")
        if self.options.files:
            return self.options.files
        elif self.options.reparse_curated:
            reports = [
                r for r in db.collisions
                if r["road_location"] is not None
                and not r["case_no"].startswith("NDOR")
            ]
            return [
                os.path.join(self.options.pdfdir,
                             utils.case_no_to_filename(report.case_no))
                for report in reports
            ]
        else:
            case_numbers = [
                r["case_no"] for r in db.collisions
                if r.get("parsed") and not r["case_no"].startswith("NDOR")
            ]
            return [
                fpath
                for fpath in glob.glob(os.path.join(self.options.pdfdir, "*"))
                if utils.filename_to_case_no(fpath) not in case_numbers
            ]

    def __call__(self):
        filelist = self._build_filelist()
        LOG.debug("Parsing %s files", len(filelist))

        if self.options.interactive:
            return self.run_foreground(filelist)
        elif len(filelist) < self.options.processes:
            LOG.debug("Fewer files than processes (%s files, %s processes)" %
                      (len(filelist), self.options.processes))
        nprocs = min(len(filelist), self.options.processes)

        if nprocs < 2:
            return self.run_foreground(filelist)
        else:
            return self.run_multiprocess(filelist, nprocs)

    def run_foreground(self, filelist):
        parser = Parser(self.options)
        for fpath in filelist:
            self._store_one_result(parser.parse(fpath))

    def run_multiprocess(self, filelist, nprocs):
        LOG.debug("Building %s worker processes" % nprocs)
        processes = [
            ParseChildProcess(
                self._terminate,
                self._work_queue,
                self._result_queue,
                self.options,
                name="parse-child-%s" % i) for i in range(nprocs)
        ]

        for fpath in filelist:
            self._work_queue.put(fpath)
        LOG.debug("Added %s file paths to work queue",
                  self._work_queue.qsize())

        LOG.debug("Starting %s worker processes", len(processes))
        for process in processes:
            process.start()

        LOG.debug("Collecting results from result queue")
        while processes:
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
                            LOG.debug("Process %s completed", process.name)
                    elif self._terminate:
                        LOG.debug("Process %s exited", process.name)
                    else:
                        LOG.warn("Process %s exited unexpectedly",
                                 process.name)
                    if not running:
                        processes.remove(process)
                LOG.debug("%s processes still running", len(processes))
                LOG.debug("%s items still in work queue",
                          self._work_queue.qsize())
            except (SystemExit, KeyboardInterrupt):
                LOG.info("Stopping %s processes", len(processes))
                self._terminate.set()
            except Exception:  # pylint: disable=broad-except
                self._terminate.set()
                LOG.error("Uncaught exception: %s", traceback.format_exc())

        # handle any more results that have arrived between the time
        # that results were handled and all processes stopped.
        self._handle_results()

        self._work_queue.close()
        self._result_queue.close()


class Parser(object):
    interactive = True

    _injured_name_re = re.compile(r'^\s*(?P<name>[^\d]*?)\s+\d')

    def __init__(self, options):
        self.options = options
        self.layout = yaml.load(open(self.options.layout))

        for objects in self.layout["objects"].values():
            for obj in objects.values():
                try:
                    obj["raw_coordinates"] = obj["coordinates"]
                except KeyError:
                    LOG.error("Malformed layout object: %s", obj)
                    LOG.error("Missing 'coordinates' key")
                    raise
                obj["coordinates"] = Coordinates(*obj["raw_coordinates"])

                if "type" in obj:
                    obj["converter"] = Converter.load_converter(obj["type"])

        for pg_type, coords_list in self.layout["skip"].items():
            self.layout["skip"][pg_type] = [
                Coordinates(*c) for c in coords_list
            ]

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

    def _handle_record_multiple_candidates(self, pdfobj, page, filename,
                                           candidates):
        coords = Coordinates(*pdfobj.bbox)
        if self.interactive:
            print(
                "Could not determine what %s on page %s of %s is. Candidates:"
                % (pdfobj_repr(pdfobj), page.name, filename))
            for obj_name, candidate in candidates.items():
                print("  %s: %s" % (obj_name, candidate))
            name = None
            while (name is None
                   or (name not in candidates and name.upper() != 'S')):
                name = input("Enter name, or 'S' to skip: ")
            if name.upper() == 'S':
                self.layout["skip"].setdefault(page.name, []).append(coords)
                print("Adding to skip list for %s:" % page.name)
                print("  - %s" % coords.to_list())
            else:
                layout_obj = candidates[name]
                new_coords = coords.merge(layout_obj["coordinates"])
                print("Updating coordinates for %s to %s" % (name, new_coords))
                obj = self.layout["objects"][page.name][name]
                obj["coordinates"] = new_coords
                obj["raw_coordinates"] = new_coords.to_list()
                return name, layout_obj
        else:
            msg = ("Could not determine what %s on page %s is: %s candidates" %
                   (pdfobj_repr(pdfobj), page.name, len(candidates)))
            LOG.error(msg)
            for name in candidates.keys():
                LOG.error("  Candidate: %s", name)
            raise Exception(msg)
        return None

    def _handle_record_without_candidates(self, pdfobj, page, filename):
        coords = Coordinates(*pdfobj.bbox)
        if self.interactive:
            print("Could not determine what %s on page %s of %s is. "
                  "No candidates." % (pdfobj_repr(pdfobj), page.name,
                                      filename))
            existing_names = itertools.chain(
                [o.keys() for o in self.layout["objects"].values()])
            name = None
            while name is None or name in existing_names:
                name = input("Enter name, or 'S' to skip: ")

            if name.upper() == 'S':
                self.layout["skip"].setdefault(page.name, []).append(coords)
                print("Adding to skip list for %s:" % page.name)
                print("  - %s" % coords.to_list())
            else:
                layout_record = {
                    "coordinates": coords,
                    "raw_coordinates": coords.to_list(),
                }

                record_type = input("Enter type: ")
                if record_type:
                    layout_record["type"] = record_type
                    layout_record["converter"] = Converter.load_converter(
                        record_type)

                self.layout["objects"][page.name][name] = layout_record

                print("Adding to layout object list:")
                print("%s:" % name)
                print("  coordinates: %r" % layout_record["raw_coordinates"])
                if "type" in layout_record:
                    print("  type: %s" % layout_record["type"])

                return name, layout_record
        else:
            msg = ("Could not determine what %s on page %s is: no candidates" %
                   (pdfobj_repr(pdfobj), page.name))
            LOG.error(msg)
            raise Exception(msg)
        return None

    def _parse_pdfobj(self, pdfobj, page, filename):
        record = get_text(pdfobj)
        if not record:
            return None
        coords = Coordinates(*pdfobj.bbox)

        skip_pdf_obj = False
        for skip_coords in self.layout["skip"].get(page.name, []):
            if skip_coords.contains(coords, fuzz=0.1):
                LOG.debug("Skipping PDF object %s: contained within %s",
                          pdfobj_repr(pdfobj), skip_coords)
                skip_pdf_obj = True
                break
        if skip_pdf_obj:
            return None

        candidates = {}
        for obj_name, obj in self.layout["objects"][page.name].items():
            if obj["coordinates"].contains(coords, fuzz=0.1):
                candidates[obj_name] = obj
        if len(candidates) > 1:
            obj_name, layout_obj = self._handle_record_multiple_candidates(
                pdfobj, page, filename, candidates)
        elif not candidates:
            obj_name, layout_obj = self._handle_record_without_candidates(
                pdfobj, page, filename)
        elif len(candidates) == 1:
            obj_name, layout_obj = candidates.items()[0]

        if layout_obj:
            if "converter" in layout_obj:
                try:
                    record = layout_obj["converter"].convert(record)
                except Exception as err:
                    LOG.error(
                        "Could not convert value %r for %s in %s to %s: %s",
                        record, obj_name, filename,
                        layout_obj["converter"].__class__.__name__, err)
                    raise
            LOG.debug("Found %s at %s in %s: %r", obj_name, coords, filename,
                      record)
            return ParsedPDFObjectData(obj_name, record)
        return None

    def _parse_pdf(self, filename):
        """Parse a single PDF and return the known data."""
        LOG.info("Parsing accident report data from %s" % filename)

        doc = PDFDocument(filename, self.layout)

        data = {
            "filename": filename,
            "case_no": utils.filename_to_case_no(filename)
        }

        page_types = []
        for page in doc:
            if page.name in page_types:
                LOG.warning("Already parsed %s page in %s; skipping page %s",
                            page.name, filename, page.number)
                continue

            LOG.debug("Parsing page %s (%s)", page.number, page.name)

            for pdfobj in page:
                obj_data = self._parse_pdfobj(pdfobj, page, filename)
                if obj_data is not None:
                    data[obj_data.name] = obj_data.data

        data["parsed"] = True
        return data

    def parse(self, filename):
        try:
            case_data = self._parse_pdf(filename)
        except psparser.PSException as err:
            LOG.warn("Parsing %s failed, skipping: %s", filename, err)
        return case_data


class ParseChildProcess(Parser, multiprocessing.Process):
    """Child process for Parse command."""
    interactive = False

    def __init__(self, terminate, work_queue, result_queue, options,
                 name=None):
        Parser.__init__(self, options)
        multiprocessing.Process.__init__(name=name)

        self._terminate = terminate
        self._work_queue = work_queue
        self._result_queue = result_queue

    def run(self):
        log.setup_logging(self.options.verbose, prefix=self.name)
        while not self._terminate.is_set():
            try:
                fpath = self._work_queue.get_nowait()
                LOG.debug("Got file path from work queue: %s", fpath)
                data = self.parse(fpath)
                LOG.debug("Returning data for %s to results queue", fpath)
                self._result_queue.put(data)
            except queue.Empty:
                LOG.info("Work queue is empty, exiting")
                break
            except KeyboardInterrupt:
                LOG.info("Caught Ctrl-C, exiting")
                break
