"""Produce a monthly graph of when bike-related crashes happen."""

import datetime
import json
import os

import jinja2

from crashes.cmd import base
from crashes.cmd import curate
from crashes import log

LOG = log.getLogger(__name__)


def report_link(case_no, text=None):
    if text is None:
        text = case_no
    fname = case_no.upper().replace("-", "")
    prefix = fname[0:4]
    return ('<a href="http://cjis.lincoln.ne.gov/~ACC/%s/%s.PDF" '
            'class="reference external">%s</a>' % (prefix, fname, text))


def literal(text):
    return '<tt class="docutils literal">%s</tt>' % text


class Results(base.Command):
    """Render the results template."""

    prerequisites = [curate.Curate]

    def __init__(self, options):
        super(Results, self).__init__(options)
        self._reports = json.load(open(self.options.all_reports))
        self._curation = json.load(open(self.options.curation_results))
        self.lb716_results = json.load(open(self.options.lb716_results))

    def _relpath(self, path):
        prefix = os.path.commonprefix([path, os.getcwd()])
        return os.path.relpath(path, prefix)

    def _get_vars(self):
        rv = {}

        rv['now'] = datetime.datetime.now()

        rv['report_count'] = len(self._reports)
        rv['first_report'] = None
        rv['last_report'] = None
        rv['unparseable_count'] = 0

        for report in self._reports.values():
            if report['date'] is None:
                rv['unparseable_count'] += 1
                continue
            date = datetime.datetime.strptime(report['date'], "%Y-%m-%d")
            if rv['first_report'] is None or date < rv['first_report']:
                rv['first_report'] = date
            if rv['last_report'] is None or date > rv['last_report']:
                rv['last_report'] = date

        rv['bike_reports'] = sum(len(d) for n, d in self._curation.items()
                                 if n != "not_involved")
        rv['statuses'] = {n: len(d) for n, d in self._curation.items()}
        rv['total_road'] = (len(self._curation['road']) +
                            len(self._curation['intersection']))
        rv['total_sidewalk'] = (len(self._curation['sidewalk']) +
                                len(self._curation['crosswalk']))

        rv['imagedir'] = self._relpath(self.options.imagedir)
        rv['all_reports'] = self._relpath(self.options.all_reports)

        rv['lb716_total'] = len(self.lb716_results["row"] +
                                self.lb716_results["non-row"])
        rv['lb716_row'] = len(self.lb716_results["row"])

        return rv

    def __call__(self):
        env = jinja2.Environment()
        env.filters['report_link'] = report_link
        env.filters['literal'] = literal

        LOG.debug("Loading template from %s" % self.options.template)
        template = env.from_string(open(self.options.template).read())

        LOG.info("Writing output to %s" % self.options.results_output)
        open(self.options.results_output,
             "w").write(template.render(**self._get_vars()))

    def satisfied(self):
        return os.path.exists(self.options.crash_graph)
