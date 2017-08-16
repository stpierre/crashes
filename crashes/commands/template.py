"""Produce a monthly graph of when bike-related crashes happen."""

import json
import logging
import os

import jinja2

from crashes.commands import base

LOG = logging.getLogger(__name__)


def report_link(case_no, text=None):
    if text is None:
        text = case_no
    fname = case_no.upper().replace("-", "")
    prefix = fname[0:4]
    return ('<a href="http://cjis.lincoln.ne.gov/~ACC/%s/%s.PDF" '
            'class="reference external">%s</a>' % (prefix, fname, text))


def literal(text):
    return '<tt class="docutils literal">%s</tt>' % text


class Template(base.Command):
    """Render the templates."""

    def __init__(self, options):
        super(Template, self).__init__(options)
        self._template_data = json.load(
            open(os.path.join(self.options.datadir, "template_data.json")))

    def __call__(self):
        env = jinja2.Environment()
        env.filters['report_link'] = report_link
        env.filters['literal'] = literal

        LOG.debug("Using template variables: %r", self._template_data)

        for tmpl_name in os.listdir(self.options.template_source_dir):
            tmpl_file = os.path.join(self.options.template_source_dir,
                                     tmpl_name)
            LOG.debug("Loading template from %s", tmpl_file)
            template = env.from_string(open(tmpl_file).read())

            dest_file = os.path.join(self.options.template_dest_dir, tmpl_name)
            LOG.info("Writing output to %s", dest_file)
            open(dest_file, "w").write(template.render(**self._template_data))
