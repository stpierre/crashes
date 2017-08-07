"""Crashes CLI."""

import argparse
import inspect
import os
import pkgutil
import sys

import yaml

from crashes import commands
from crashes.commands import base
from crashes import db
from crashes import log

LOG = log.getLogger(__name__)

# config defaults
DEFAULTS = {
    "form": {
        "url": "HTTP://CJIS.LINCOLN.NE.GOV/HTBIN/CGI.COM",
        "token": "DISK0:[020020.WWW]ACCDESK.COM",
        "sleep_min": "5",
        "sleep_max": "30",
    },
    "fetch": {
        "days": "365",
        "start": "",
        "retries": "3",
        "direct_base_url": "http://cjis.lincoln.ne.gov/~ACC",
    },
    "database": {
        "uri": "sqlite:///crashes.sqlite",
        "dumpdir": "db_dump",
    },
    "files": {
        "datadir": "data",
        "pdfdir": "pdfs",
        "geocoding": "geojson",
        "imagedir": "images",
        "graph_data": "graph",
        "bike_route_geojson": "bike-paths.geojson",
        "csvdir": "csv",
        "layout": "layout.yml",
        "fixtures": "fixtures",
        "db": "db",
    },
    "templates": {
        "sourcedir": "templates",
        "destdir": "."
    }
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
    parser.add_argument(
        "-c",
        "--config",
        type=argparse.FileType("r"),
        default="crashes.yml",
        help="Path to config file")
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="Verbosity level")

    # collect commands
    subparsers = parser.add_subparsers()
    for loader, name, _ in pkgutil.walk_packages(commands.__path__):
        module = loader.find_module(name).load_module(name)

        for name, cls in inspect.getmembers(module):
            if (not isinstance(cls, type) or not issubclass(cls, base.Command)
                    or name.startswith('__')):
                continue

            cmd_parser = subparsers.add_parser(name.lower(), help=cls.__doc__)
            cmd_parser.set_defaults(command=cls)
            for arg in cls.arguments:
                arg.add_to_parser(cmd_parser)

    options = parser.parse_args()

    # parse config file
    config = yaml.load(options.config)

    def _get_config(key, val):
        return config.get(key, {}).get(val, DEFAULTS[key][val])

    options.form_url = _get_config("form", "url")
    options.form_token = _get_config("form", "token")
    options.sleep_min = int(_get_config("form", "sleep_min"))
    options.sleep_max = int(_get_config("form", "sleep_max"))

    options.fetch_days = int(_get_config("fetch", "days"))
    options.fetch_start = _get_config("fetch", "start")
    options.fetch_retries = int(_get_config("fetch", "retries"))
    options.fetch_direct_base_url = _get_config("fetch", "direct_base_url")

    options.datadir = _canonicalize(
        _get_config("files", "datadir"), os.getcwd())
    options.pdfdir = _canonicalize(
        _get_config("files", "pdfdir"), options.datadir)
    options.geocoding = _canonicalize(
        _get_config("files", "geocoding"), options.datadir)
    options.imagedir = _canonicalize(
        _get_config("files", "imagedir"), options.datadir)
    options.bike_route_geojson = _canonicalize(
        _get_config("files", "bike_route_geojson"))
    options.graph_data = _canonicalize(
        _get_config("files", "graph_data"), options.datadir)
    options.csvdir = _canonicalize(_get_config("files", "csvdir"), os.getcwd())
    options.layout = _canonicalize(_get_config("files", "layout"), os.getcwd())
    options.fixtures = _canonicalize(
        _get_config("files", "fixtures"), options.datadir)
    options.dbdir = _canonicalize(_get_config("files", "db"), options.datadir)

    options.template_source_dir = _canonicalize(
        _get_config("templates", "sourcedir"), os.getcwd())
    options.template_dest_dir = _canonicalize(
        _get_config("templates", "destdir"), os.getcwd())

    options.database = _get_config("database", "uri")
    options.dumpdir = _canonicalize(
        _get_config("database", "dumpdir"), options.datadir)

    options.func = options.command(options)
    return options


def main():
    options = parse_args()
    log.setup_logging(options.verbose)
    db.init(options.dbdir, options.fixtures)

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
