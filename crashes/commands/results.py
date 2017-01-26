"""Produce a monthly graph of when bike-related crashes happen."""

import datetime
import json
import os

import jinja2

from crashes.commands import base
from crashes.commands import curate
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
        self._metadata = json.load(open(self.options.metadata))
        self._hitnrun_data = json.load(open(self.options.hitnrun_data))

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
        rv['ndor_count'] = 0

        rv['num_children'] = 0
        rv['under_11'] = 0

        rv['injured_count'] = 0

        for report in self._reports.values():
            if report['date'] is None:
                rv['unparseable_count'] += 1
                continue
            date = datetime.datetime.strptime(report['date'], "%Y-%m-%d")
            if rv['first_report'] is None or date < rv['first_report']:
                rv['first_report'] = date
            if rv['last_report'] is None or date > rv['last_report']:
                rv['last_report'] = date
            if report.get('cyclist_dob') is None:
                continue
            if report['case_number'].startswith("NDOR"):
                rv['ndor_count'] += 1
                continue
            dob = datetime.datetime.strptime(report['cyclist_dob'], "%Y-%m-%d")
            diff = date - dob
            age_at_collision = diff.days / 365.25
            if age_at_collision < 20:
                rv['num_children'] += 1
                if age_at_collision < 11:
                    rv['under_11'] += 1
            if report.get('injury_severity', 5) < 5:
                rv['injured_count'] += 1

        rv['bike_reports'] = sum(len(d) for n, d in self._curation.items()
                                 if n != "not_involved")
        rv['statuses'] = {n: len(d) for n, d in self._curation.items()}
        rv['total_road'] = (len(self._curation['road']) +
                            len(self._curation['intersection']))
        rv['total_sidewalk'] = (len(self._curation['sidewalk']) +
                                len(self._curation['crosswalk']))

        rv['imagedir'] = self._relpath(self.options.imagedir)
        rv['all_reports'] = self._relpath(self.options.all_reports)

        rv['pct_children'] = (
            float(rv['num_children'] * 100) / rv['bike_reports'])

        rv['hit_and_run_counts'] = {t: len(c)
                                    for t, c in self._hitnrun_data.items()}
        rv['hit_and_run_total'] = sum(rv['hit_and_run_counts'].values())

        report_time_period = datetime.datetime.now() - rv['first_report']
        report_years = report_time_period.days / 365.25
        rv['under_11_per_year'] = rv['under_11'] / report_years

        LOG.debug("Using template variables: %r" % rv)

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
