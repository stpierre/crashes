"""Crashes CLI."""

import argparse
import inspect
import os
import sys

from six.moves import configparser

from crashes import cmd
from crashes.cmd import base
from crashes import log

LOG = log.getLogger(__name__)

# config defaults
DEFAULTS = {
    "url": "HTTP://CJIS.LINCOLN.NE.GOV/HTBIN/CGI.COM",
    "token": "DISK0:[020020.WWW]ACCDESK.COM",
    "sleep_min": "5",
    "sleep_max": "30",
    "days": "365",
    "start": "",
    "retries": "3",
    "datadir": "data",
    "pdfdir": "pdfs",
    "all_reports": "reports.json",
    "curation_results": "curation.json",
    "imagedir": "images",
    "template": "results.rst",
    "content": "content"
}


def _canonicalize(path, datadir):
    if path.startswith(("~", "/")):
        return os.path.abspath(os.path.expanduser(path))
    else:
        return os.path.abspath(os.path.join(datadir, path))


def parse_args():
    """Parse arguments and config file."""
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", type=argparse.FileType("r"),
                        default="crashes.conf", help="Path to config file")
    parser.add_argument("-v", "--verbose", action="count",
                        default=0, help="Verbosity level")

    # collect commands
    subparsers = parser.add_subparsers()
    for name, cls in inspect.getmembers(cmd):
        if isinstance(cls, type) and issubclass(cls, base.Command):
            cmd_parser = subparsers.add_parser(name.lower(),
                                               help=cls.__doc__)
            cmd_parser.set_defaults(command=cls)
            for arg in cls.arguments:
                arg.add_to_parser(cmd_parser)

    options = parser.parse_args()

    # parse config file
    cfp = configparser.ConfigParser(DEFAULTS)
    cfp.readfp(options.config)
    options.form_url = cfp.get("form", "url")
    options.form_token = cfp.get("form", "token")
    options.sleep_min = int(cfp.get("form", "sleep_min"))
    options.sleep_max = int(cfp.get("form", "sleep_max"))
    options.fetch_days = int(cfp.get("fetch", "days"))
    options.fetch_start = cfp.get("fetch", "start")
    options.fetch_retries = int(cfp.get("fetch", "retries"))
    options.datadir = _canonicalize(cfp.get("files", "datadir"), os.getcwd())
    options.pdfdir = _canonicalize(cfp.get("files", "pdfdir"),
                                   options.datadir)
    options.all_reports = _canonicalize(cfp.get("files", "all_reports"),
                                        options.datadir)
    options.curation_results = _canonicalize(cfp.get("files",
                                                     "curation_results"),
                                             options.datadir)
    options.imagedir = _canonicalize(cfp.get("files", "imagedir"),
                                     options.datadir)
    options.template = _canonicalize(cfp.get("files", "template"),
                                     os.getcwd())
    options.content = _canonicalize(cfp.get("files", "content"), os.getcwd())

    options.func = options.command(options)
    return options


def main():
    options = parse_args()
    log.setup_logging(options.verbose)

    if not os.path.exists(options.datadir):
        LOG.info("Creating datadir %s" % options.datadir)
        os.makedirs(options.datadir)
    if not os.path.exists(options.pdfdir):
        LOG.info("Creating pdfdir %s" % options.pdfdir)
        os.makedirs(options.pdfdir)
    if not os.path.exists(options.imagedir):
        LOG.info("Creating imagedir %s" % options.imagedir)
        os.makedirs(options.imagedir)
    if not os.path.exists(options.content):
        LOG.info("Creating content path %s" % options.content)
        os.makedirs(options.content)

    return options.func()


if __name__ == "__main__":
    sys.exit(main())
