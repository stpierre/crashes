"""Crashes CLI."""

import argparse
import inspect
import os
import pkgutil
import sys

from six.moves import configparser

from crashes import commands
from crashes.commands import base
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
    "metadata": "metadata.json",
    "geocoding": "geojson",
    "imagedir": "images",
    "template": "results.html",
    "results_output": "index.html",
    "lb716_results": "lb716.json",
    "graph_data": "graph",
    "hitnrun_data": "hit-and-run.json"
}


def _canonicalize(path, datadir=None):
    if path.startswith(("~", "/")):
        path = os.path.expanduser(path)
    elif datadir:
        path = os.path.join(datadir, path)
    return os.path.abspath(path)


def parse_args():
    """Parse arguments and config file."""
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", type=argparse.FileType("r"),
                        default="crashes.conf", help="Path to config file")
    parser.add_argument("-v", "--verbose", action="count",
                        default=0, help="Verbosity level")

    # collect commands
    subparsers = parser.add_subparsers()
    for loader, name, _ in pkgutil.walk_packages(commands.__path__):
        module = loader.find_module(name).load_module(name)

        for name, cls in inspect.getmembers(module):
            if (not isinstance(cls, type) or
                    not issubclass(cls, base.Command) or
                    name.startswith('__')):
                continue

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
    options.geocoding = _canonicalize(cfp.get("files", "geocoding"),
                                      options.datadir)
    options.imagedir = _canonicalize(cfp.get("files", "imagedir"),
                                     options.datadir)
    options.template = _canonicalize(cfp.get("files", "template"),
                                     os.getcwd())
    options.results_output = _canonicalize(cfp.get("files", "results_output"),
                                           os.getcwd())
    options.bike_route_geojson = _canonicalize(cfp.get("files",
                                                       "bike_route_geojson"))
    options.lb716_results = _canonicalize(cfp.get("files", "lb716_results"),
                                          options.datadir)
    options.graph_data = _canonicalize(cfp.get("files", "graph_data"),
                                       options.datadir)
    options.metadata = _canonicalize(cfp.get("files", "metadata"),
                                     options.datadir)
    options.hitnrun_data = _canonicalize(cfp.get("files", "hitnrun_data"),
                                     options.datadir)

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
    if not os.path.exists(options.geocoding):
        LOG.info("Creating geocoding directory %s" % options.geocoding)
        os.makedirs(options.geocoding)

    return options.func()


if __name__ == "__main__":
    sys.exit(main())
