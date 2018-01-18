"""Find accident reports that may have involved a bicycle."""

from __future__ import print_function

import collections
import logging
import operator
import re
import textwrap

from backports.shutil_get_terminal_size import get_terminal_size
from six.moves import input
import termcolor
from textblob import classifiers

from crashes.commands import base
from crashes import db
from crashes import utils

LOG = logging.getLogger(__name__)
ROWS = get_terminal_size()[0]

CurationStatus = collections.namedtuple("CurationStatus", ("name",
                                                           "description"))


class StatusDict(collections.MutableMapping):
    def __init__(self, prompt="Status", display_choices=True):
        self._prompt = prompt
        self._order = []
        self._end = ["K", "Q", "?"]
        self._statuses = {
            "K": CurationStatus(None, "Skip"),
            "Q": CurationStatus(None, "Quit"),
            "?": CurationStatus(None, "Help")
        }
        self._display_choices = display_choices

    def __getitem__(self, key):
        return self._statuses[key]

    def __setitem__(self, key, value):
        if key in self._statuses:
            raise KeyError("%s is already present in %s" % (key, self))
        self._statuses[key] = value
        self._order.append(key)

    def __delitem__(self, key):
        del self._statuses[key]
        self._order.remove(key)

    def __iter__(self):
        return iter(self._order + self._end)

    def __len__(self):
        return len(self._statuses)

    @property
    def help(self):
        longest_key = min(1,
                          max(len(str(key)) for key in self._statuses.keys()))
        indent = " " * (longest_key + 2)
        rv = []
        for key in self:
            status = self._statuses[key]
            if status.name != key:
                line = "%s (%s): %s" % (key, status.name, status.description)
            else:
                line = "%s: %s" % (key, status.description)
            rv.append(
                textwrap.fill(line, width=ROWS, subsequent_indent=indent))
        return "\n".join(rv)

    @property
    def choices(self):
        return "/".join(str(k) for k in self)

    def input(self, default=None):
        if self._display_choices and default:
            prompt = "%s [%s, default=%s] " % (self._prompt, self.choices,
                                               default)
        elif self._display_choices:
            prompt = "%s [%s]: " % (self._prompt, self.choices)
        elif default:
            prompt = "%s [default=%s] " % (self._prompt, default)
        else:
            prompt = "%s: " % self._prompt

        while True:
            ans = input(prompt).upper()
            if not ans and default:
                ans = default
            if ans == '?' or ans not in self:
                print(self.help)
            elif ans == "K":
                return None
            elif ans == "Q":
                raise SystemExit(0)
            else:
                return self[ans].name

    def get_shortcut(self, name):
        for key, status in self.items():
            if name == status.name:
                return key
        raise ValueError("%s is not a valid choice (%s)" %
                         (name, [s.name for s in self.values()]))


# pylint: disable=unused-argument,no-self-use
class CurationStep(object):
    results_column = None
    status_fixture = None
    order = None
    prompt = "Status"
    use_bayes = True
    display_choices = True

    def __init__(self):
        self._curated = 0
        self._predicted = 0
        # NOTE(stpierre): we have to defer the population of the
        # status dict and bayesian classifier until after the
        # constructor is called, since they depends on database
        # initialization to read the fixture data/report data. But db
        # init is called after option parsing, which is when the
        # constructor is called.
        self._statuses = None
        self._classifier = None

    @staticmethod
    def _get_report_bayes_data(report):
        return "\n".join([
            utils.get_report_text(report),
            "Road location: %s" % report.get("road_location"),
            "DOT code: %s" % report.get("dotcode")
        ])

    def _get_training_data(self):
        return [(self._get_report_bayes_data(r), r[self.results_column])
                for r in db.collisions
                if r.get(self.results_column) and utils.get_report_text(r)]

    def classify(self, report):
        if not self.use_bayes:
            raise NotImplementedError(
                "Bayesian classification is disabled for %s objects" %
                self.__class__.__name__)
        if self._classifier is None:
            LOG.debug(
                "Collecting training data for Bayesian classifier for %s",
                self.__class__.__name__)
            train = self._get_training_data()
            if train:
                LOG.debug(
                    "Training Bayesian classifier for %s with %s records",
                    self.__class__.__name__, len(train))
                self._classifier = classifiers.NaiveBayesClassifier(train)
            else:
                LOG.debug("No training data for %s, skipping classification",
                          self.__class__.__name__)
                return None
        return self._classifier.classify(utils.get_report_text(report))

    def get_sorted_choices(self):
        return self.status_fixture.items()

    @property
    def statuses(self):
        if self._statuses is None:
            self._statuses = StatusDict(
                self.prompt, display_choices=self.display_choices)
            for name, status in self.get_sorted_choices():
                self._statuses[status["shortcut"]] = CurationStatus(
                    name, status["desc"])
        return self._statuses

    def _get_default(self, report):
        if self.use_bayes:
            default = self.classify(report)
            if default:
                if default in self.statuses:
                    # DOT coding is stored as the shortcut, so we can
                    # return it directly
                    return default
                else:
                    # assume that we've gotten the name, not the
                    # shortcut, and return the shortcut. This is how
                    # the road location/hit and run coding works.
                    return self.statuses.get_shortcut(default)
        return None

    def print_additional_info(self, report):
        pass

    def get_answer(self, report):
        default = self._get_default(report)
        answer = self.statuses.input(default=default)
        self._curated += 1
        if self.use_bayes:
            if (answer is not None and default is not None
                    and self.statuses[default].name == answer):
                # predicted default was correct
                self._predicted += 1
            LOG.debug("Bayesian accuracy: %0.2f%% (%s/%s)",
                      self.bayes_accuracy, self._predicted, self._curated)
        return answer

    @property
    def bayes_accuracy(self):
        if self._curated:
            return 100.0 * self._predicted / self._curated
        else:
            return 0.0

    def curate_case(self, report):
        return True


# pylint: enable=unused-argument,no-self-use


class LocationCuration(CurationStep):
    """Determine where a collision happened."""

    results_column = "road_location"
    status_fixture = db.location
    prompt = "Road location"
    order = 0

    def _get_training_data(self):
        return [(utils.get_report_text(r), r[self.results_column])
                for r in db.collisions
                if r.get(self.results_column) not in (
                    None, "unknown") and utils.get_report_text(r)]


class DOTCoding(CurationStep):
    """Determine the DOT collision code."""

    results_column = "dotcode"
    status_fixture = db.dotcode
    prompt = "DOT code"
    order = 5
    display_choices = False

    def print_additional_info(self, report):
        print("Road location: %(road_location)s" % report)

    def get_sorted_choices(self):
        return sorted(
            self.status_fixture.items(), key=lambda v: v[1]["shortcut"])

    def curate_case(self, report):
        if report.get("road_location") in (None, 'not involved'):
            LOG.debug("Cyclist was not involved in %s, skipping DOT coding",
                      report["case_no"])
            return False
        return True


class HitnrunCuration(CurationStep):
    """Determine who hit-and-ran."""

    results_column = "hit_and_run_status"
    status_fixture = db.hit_and_run_status
    prompt = "Hit and run status"
    order = 10
    use_bayes = False

    def _get_default(self, _):
        # not trying to be biased here, this is just a sensible default :(
        return "D"

    def curate_case(self, report):
        if report.get("road_location") in (None, 'not involved'):
            LOG.debug("Cyclist was not involved in %s, skipping hit-and-run",
                      report["case_no"])
            return False
        if not report.get("hit_and_run", False):
            LOG.debug("%s was not a hit-and-run, skipping", report["case_no"])
            return False
        return True


class BlindRightCuration(CurationStep):
    """Find collisions that are look-left-turn-right scenarios."""

    results_column = "look_left_turn_right"
    status_fixture = db.boolean
    prompt = "Look-left-turn-right collision"
    order = 20

    def curate_case(self, report):
        if report.get("road_location") not in ("sidewalk", "crosswalk",
                                               "bike trail",
                                               "bike trail crossing",
                                               "bike lane"):
            LOG.debug(
                "%s was not at a road crossing (%s), skipping blind right",
                report["case_no"], report.get("road_location"))
            return False
        dotcode = int(report.get("dotcode", 0))
        if (120 <= dotcode < 140 or  # cyclist or motorist lost control
                220 <= dotcode < 230 or  # cyclist ride out
                230 <= dotcode < 250 or  # cyclist or motorst overtaking
                250 <= dotcode < 260 or  # head-on
                310 <= dotcode < 320 or  # cyclist ride out
                dotcode >= 400 or  # non-roadway, other oddities
                dotcode in (144, 156, 215, 216, 280)):
            LOG.debug("DOT code for %s indicates non-right turn crash, "
                      "skipping blind right (%s)", report["case_no"],
                      report["dotcode"])
            return False
        return True

    def print_additional_info(self, report):
        print("Road location: %(road_location)s" % report)
        print("DOT code: %(dotcode)s" % report)


class Curate(base.Command):
    """Do manual curation of accident reports."""

    fmt = "%%-10s %%%ds" % (ROWS - 12)
    search_re = re.compile(r'\b(bicycle|bike|(?:bi)?cyclist)\b', re.I)
    highlight_re = re.compile(r'((?:bi|tri|pedal)cycle|bike|(?:bi)?cyclist|'
                              r'crosswalk|sidewalk|intersection)', re.I)

    def __init__(self, options):
        super(Curate, self).__init__(options)
        self.steps = []
        for name, obj in globals().items():
            if (not name.startswith("_") and isinstance(obj, type)
                    and issubclass(obj, CurationStep) and obj != CurationStep):
                self.steps.append(obj())
        self.steps.sort(key=operator.attrgetter("order"))

    def _print_report(self, report):
        split = self.highlight_re.split(utils.get_report_text(report))

        print(termcolor.colored(
            self.fmt % (report["case_no"], report["date"]),
            'red',
            attrs=['bold']))
        # colorize matches in the output to make it easier to curate
        for i in range(1, len(split), 2):
            split[i] = termcolor.colored(split[i], 'green', attrs=["bold"])
        print(textwrap.fill("".join(split).replace("\n", ""), width=ROWS))

    def _curate_one(self, report):
        report_printed = False
        for step in self.steps:
            if report.get(step.results_column) is not None:
                LOG.debug("%s has already been curated by %s, skipping",
                          report["case_no"], step.__class__.__name__)
                continue
            elif not step.curate_case(report):
                LOG.debug("%s is not flagged for curation by %s, skipping",
                          report["case_no"], step.__class__.__name__)
                continue

            if not report_printed:
                self._print_report(report)
                report_printed = True
            step.print_additional_info(report)
            ans = step.get_answer(report)
            if ans is not None:
                report[step.results_column] = ans
                db.collisions.replace(report)

    def __call__(self):
        complete = 0

        total = len(db.collisions)

        for report in db.collisions:
            if report.get("report") is None:
                LOG.debug("%s has no report, skipping", report["case_no"])
            else:
                if not self.search_re.search(utils.get_report_text(report)):
                    LOG.debug("%s doesn't match the search regex, skipping",
                              report["case_no"])
                else:
                    with db.collisions.delay_write():
                        self._curate_one(report)
                    LOG.info("%s/%s curated (%.02f%%)", complete, total,
                             100.0 * complete / total)
            complete += 1
