"""Produce a monthly graph of when bike-related crashes happen."""

import datetime
import json
import os

import jinja2

from crashes.commands import base
from crashes.commands import xform
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

    prerequisites = [xform.Xform]

    def __init__(self, options):
        super(Results, self).__init__(options)
        self._template_data = json.load(
            open(os.path.join(self.options.datadir, "template_data.json")))

    def __call__(self):
        env = jinja2.Environment()
        env.filters['report_link'] = report_link
        env.filters['literal'] = literal

        LOG.debug("Using template variables: %r" % self._template_data)

        LOG.debug("Loading template from %s" % self.options.template)
        template = env.from_string(open(self.options.template).read())

        LOG.info("Writing output to %s" % self.options.results_output)
        open(self.options.results_output,
             "w").write(template.render(**self._template_data))

    def satisfied(self):
        return os.path.exists(self.options.crash_graph)
