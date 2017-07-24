"""Find accident reports that may have involved a bicycle."""

from __future__ import print_function

import collections
import logging
import re
import textwrap

from six.moves import input
import termcolor

from crashes.commands import base
from crashes import db


LOG = logging.getLogger(__name__)

CurationStatus = collections.namedtuple("CurationStatus",
                                        ("name", "description"))


class StatusDict(collections.MutableMapping):
    def __init__(self):
        self._order = []
        self._end = ["K", "Q", "?"]
        self._statuses = {"K": CurationStatus(None, "Skip"),
                          "Q": CurationStatus(None, "Quit"),
                          "?": CurationStatus(None, "Help")}

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
        rv = []
        for key, status in self.items():
            if status.name:
                rv.append("%s (%s): %s" % (key, status.name, status.description))
            else:
                rv.append("%s: %s" % (key, status.description))
        return "\n".join(rv)

    @property
    def choices(self):
        return "/".join(str(k) for k in self.keys())

    def input(self, default=None):
        if default:
            prompt = "Status [%s, default=%s] " % (self.choices, default)
        else:
            prompt = "Status [%s]: " % self.choices
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


class Curate(base.Command):
    """Find accident reports that may have involved a bicycle."""

    search_re = re.compile(r'\b(bicycle|bike|(?:bi)?cyclist)\b', re.I)
    highlight_re = re.compile(
        r'((?:bi|tri|pedal)cycle|bike|(?:bi)?cyclist|'
        r'crosswalk|sidewalk|intersection)',
        re.I)

    results_column = "road_location"
    status_fixture = db.location

    def __init__(self, options):
        super(Curate, self).__init__(options)
        # NOTE(stpierre): we have to defer the population of
        # self._statuses until after the constructor is called, since
        # it depends on database initialization to read the fixture
        # data. But db init is called after option parsing, which is
        # when the constructor is called.
        self._statuses = None

    @property
    def statuses(self):
        if self._statuses is None:
            self._statuses = StatusDict()
            for name, status in self.status_fixture.items():
                self._statuses[status["shortcut"]] = CurationStatus(
                    name, status["desc"])
        return self._statuses

    def _get_default(self, report):
        return None

    def _print_additional_info(self, report):
        pass

    def _get_answer(self, report):
        return self.statuses.input(default=self._get_default(report))

    def curate_case(self, report):
        return True

    def __call__(self):
        complete = 0
        to_curate = []
        for report in db.collisions:
            if report.get(self.results_column) is None:
                if report["report"] is None:
                    LOG.debug("%s has no report, skipping", report["case_no"])
                elif not self.search_re.search(report["report"]):
                    LOG.debug("%s doesn't match the search regex, skipping",
                              report["case_no"])
                elif self.curate_case(report):
                    to_curate.append(report)
                else:
                    LOG.debug("Skipping curation on %s", report["case_no"])

        for report in to_curate:
            split = self.highlight_re.split(report["report"])

            # manually curate collisions
            print(termcolor.colored("%-10s %50s" % (report["case_no"],
                                                    report["date"]),
                                    'red', attrs=['bold']))
            # colorize matches in the output to make it easier to curate
            for i in range(1, len(split), 2):
                split[i] = termcolor.colored(split[i], 'green', attrs=["bold"])
            print(textwrap.fill("".join(split)))
            self._print_additional_info(report)
            ans = self._get_answer(report)
            if ans:
                complete += 1
                report[self.results_column] = ans
                db.collisions.update_one(report)
            LOG.info("%s/%s curated (%.02f%%)" %
                     (complete, len(to_curate),
                      100 * complete / float(len(to_curate))))
