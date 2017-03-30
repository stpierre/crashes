"""Base command object."""

import logging

import sqlalchemy
from sqlalchemy import orm

LOG = logging.getLogger(__name__)


class Argument(object):
    """Argparse argument object to add to Command classes."""

    def __init__(self, *args, **kwargs):
        self._args = args
        self._kwargs = kwargs

    def add_to_parser(self, parser):
        """Add this argument to an argparse.ArgumentParser."""
        parser.add_argument(*self._args, **self._kwargs)


class Command(object):
    """Superclass for classes that are exposed as a CLI command."""

    arguments = []

    def __init__(self, options):
        self.options = options
        self.db_engine = sqlalchemy.create_engine(
            self.options.database, echo=(self.options.verbose > 2))
        self.sessionmaker = orm.sessionmaker(bind=self.db_engine)
        self.db = self.sessionmaker()

    def __call__(self):
        raise NotImplementedError
