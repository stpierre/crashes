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

from crashes.cmd import base
from crashes.cmd import jsonify


LOG = logging.getLogger(__name__)

CurationStatus = collections.namedtuple("CurationStatus",
                                        ("name", "description"))


class Curate(base.Command):
    """Find accident reports that may have involved a bicycle."""

    search_re = re.compile(r'\b(bicycle|bike|(?:bi)?cyclist)\b', re.I)
    highlight_re = re.compile(
        r'((?:bi|tri|pedal)cycle|bike|(?:bi)?cyclist|crosswalk|sidewalk)',
        re.I)
    prerequisites = [jsonify.JSONify]

    statuses = collections.OrderedDict()
    statuses["C"] = CurationStatus("crosswalk",
                                   "Bicycle in crash in crosswalk")
    statuses["S"] = CurationStatus("sidewalk", "Bicycle in crash on sidewalk")
    statuses["R"] = CurationStatus("road",
                                   "Bicycle in crash riding on road")
    statuses["E"] = CurationStatus("elsewhere", "Bicycle in crash elsewhere")
    statuses["N"] = CurationStatus("not_involved", "Bicycle not in crash")
    statuses["Q"] = CurationStatus(None, "Quit")
    statuses["?"] = CurationStatus(None, "Help")

    def _get_answer(self):
        while True:
            ans = input("Status [%s]: " %
                        "/".join(self.statuses.keys())).upper()
            if ans == '?' or ans not in self.statuses:
                for status in self.statuses:
                    print("%s: %s" % (status.key, status.description))
            elif ans == "Q":
                raise SystemExit(0)
            else:
                return self.statuses[ans].name

    def __call__(self):
        data = json.load(open(self.options.all_reports))
        if os.path.exists(self.options.curation_results):
            curation_data = json.load(open(self.options.curation_results))
        else:
            curation_data = {}
        for status in self.statuses.values():
            if status.name and status.name not in curation_data:
                curation_data[status.name] = []
        complete = 0
        for case_no, report in data.items():
            complete += 1
            if any(case_no in c for c in curation_data.values()):
                continue
            if self.search_re.search(report['report']):
                split = self.highlight_re.split(report['report'])

                # manually curate crashes
                print(termcolor.colored("%-10s %50s" % (case_no,
                                                        report['date']),
                                        'red', attrs=['bold']))
                # colorize matches in the output to make it easier to curate
                for i in range(1, len(split), 2):
                    split[i] = termcolor.colored(split[i], 'green',
                                                 attrs=["bold"])
                print(textwrap.fill("".join(split)))
                ans = self._get_answer()
                curation_data[ans].append(case_no)
                print()
                LOG.debug("Dumping curation data to %s" %
                          self.options.curation_results)
                json.dump(curation_data,
                          open(self.options.curation_results, "w"))
                LOG.info("%s/%s curated (%.02f%%)" %
                         (complete, len(data),
                          100 * complete / float(len(data))))
                LOG.debug(", ".join("%s %s" % (n, len(d))
                                    for n, d in curation_data.items()))

    def satisfied(self):
        return os.path.exists(self.options.curation_results)
