"""Collision database operations."""

import logging
import os

from six.moves import cPickle as pickle

from crashes.commands import base
from crashes import models

LOG = logging.getLogger(__name__)


def _result_as_dict(result):
    return {f: getattr(result, f)
            for f in result._fields}


class Database(base.Command):
    """Collision database operations."""

    arguments = [base.Argument("operation",
                               choices=("init", "dump", "restore"))]

    def init(self):
        models.Base.metadata.create_all(self.db_engine)

        for table in models.Base.metadata.sorted_tables:
            cls = self._get_class_by_table(table)
            if getattr(cls, "fixture", None) is not None:
                LOG.info("Creating fixture data for %s", table.name)
                self.db.query(cls).delete()
                self.db.add_all(cls(**f) for f in cls.fixture)
                self.db.commit()

    def dump(self):
        if not os.path.exists(self.options.dumpdir):
            LOG.debug("Creating %s", self.options.dumpdir)
            os.makedirs(self.options.dumpdir)
        for table in models.Base.metadata.sorted_tables:
            cls = self._get_class_by_table(table)
            if getattr(cls, "fixture", None) is not None:
                continue

            outfile = os.path.join(self.options.dumpdir, table.name)
            LOG.info("Dumping data in table %r to %s", table.name, outfile)
            rows = []
            for row in self.db.query(table).all():
                rows.append(_result_as_dict(row))
            pickle.dump(rows, open(outfile, "w"))

    @staticmethod
    def _get_class_by_table(table):
        for cls in models.Base._decl_class_registry.values():
            if (hasattr(cls, "__tablename__") and
                    cls.__tablename__ == table.name):
                return cls

    def restore(self):
        self.init()

        for table in models.Base.metadata.sorted_tables:
            cls = self._get_class_by_table(table)
            if getattr(cls, "fixture", None) is not None:
                continue

            infile = os.path.join(self.options.dumpdir, table.name)
            LOG.info("Restoring data to table %r from %s", table.name, infile)
            rows = pickle.load(open(infile))
            self.db.add_all(cls(**r) for r in rows)
            self.db.commit()

    def __call__(self):
        getattr(self, self.options.operation)()
