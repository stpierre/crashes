"""Base command object."""

import logging

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
    prerequisites = []
    arguments = []

    def __init__(self, options):
        self.options = options

    def __call__(self):
        raise NotImplementedError

    def satisfied(self):
        """Determine if this command has been run when checking prereqs."""
        raise NotImplementedError

    def satisfy_prereqs(self):
        """Follow prerequisite commands recursively."""
        for prereq in self.prerequisites:
            cmd = prereq(self.options)
            if not cmd.satisfied:
                LOG.info("Found unsatisfied prerequisite: %s" %
                         prereq.__name__.lower())
                cmd.satisfy_prereqs()
                LOG.info("Calling unsatisfied prerequisite: %s" %
                         prereq.__name__.lower())
                cmd()
