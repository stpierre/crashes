"""Find accident reports that may have involved a bicycle."""

from __future__ import print_function

import collections
import json
import logging
import os
import re
import textwrap

import termcolor
from six.moves import input

from crashes.commands import base
from crashes.commands import jsonify


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
            rv.append("%s: %s" % (key, status.description))
        return "\n".join(rv)

    @property
    def choices(self):
        return "/".join(self.keys())

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
    prerequisites = [jsonify.JSONify]

    results_file = "curation_results"

    statuses = StatusDict()
    statuses["C"] = CurationStatus("crosswalk",
                                   "Bicycle in collision in crosswalk")
    statuses["S"] = CurationStatus("sidewalk",
                                   "Bicycle in collision on sidewalk")
    statuses["R"] = CurationStatus("road",
                                   "Bicycle in collision riding on road")
    statuses["I"] = CurationStatus(
        "intersection",
        "Bicycle in collision riding through intersection")
    statuses["L"] = CurationStatus(
        "bike_lane",
        "Bicycle in collision while in bike lane")
    statuses["E"] = CurationStatus("elsewhere",
                                   "Bicycle in collision elsewhere")
    statuses["N"] = CurationStatus("not_involved", "Bicycle not in collision")

    def __init__(self, options):
        super(Curate, self).__init__(options)
        self.data = None

    def _get_default(self, case_no):
        return None

    def _print_additional_info(self, case_no):
        pass

    def _get_answer(self, case_no):
        return self.statuses.input(default=self._get_default(case_no))

    def _load_data(self):
        self.data = json.load(open(self.options.all_reports))

    def _save_data(self, results):
        LOG.debug("Dumping curation data to %s" %
                  getattr(self.options, self.results_file))
        json.dump(results, open(getattr(self.options, self.results_file), "w"))

    def __call__(self):
        self._load_data()
        if os.path.exists(getattr(self.options, self.results_file)):
            results = json.load(open(getattr(self.options, self.results_file)))
        else:
            results = {}
        for status in self.statuses.values():
            if status.name and status.name not in results:
                results[status.name] = []
        complete = sum(len(v) for v in results.values())
        for case_no, report in self.data.items():
            if any(case_no in c for c in results.values()):
                continue
            complete += 1
            if self.search_re.search(report['report']):
                split = self.highlight_re.split(report['report'])

                # manually curate collisions
                print(termcolor.colored("%-10s %50s" % (case_no,
                                                        report['date']),
                                        'red', attrs=['bold']))
                # colorize matches in the output to make it easier to curate
                for i in range(1, len(split), 2):
                    split[i] = termcolor.colored(split[i], 'green',
                                                 attrs=["bold"])
                print(textwrap.fill("".join(split)))
                self._print_additional_info(case_no)
                ans = self._get_answer(case_no)
                if ans:
                    results[ans].append(case_no)
                    print()
                    self._save_data(results)
                LOG.info("%s/%s curated (%.02f%%)" %
                         (complete, len(self.data),
                          100 * complete / float(len(self.data))))
                LOG.debug(", ".join("%s: %s" % (n, len(d))
                                    for n, d in results.items()))
        self._save_data(results)

    def satisfied(self):
        return os.path.exists(getattr(self.options, self.results_file))
