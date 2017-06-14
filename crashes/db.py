import collections
import datetime
import os

import tinydb
import tinydb_serialization
import yaml


class FixtureNotReady(Exception):
    """Database is not ready to load."""


class NoSuchDatabase(Exception):
    """No such database."""


class Fixture(collections.Mapping):
    def __init__(self, filename, key="id"):
        self.filename = filename
        self.key = key
        self._data = None

    @property
    def _filepath(self):
        if _base_path is None:
            raise FixtureNotReady(self.name)
        return os.path.join(_base_path, self.filename)

    def _load_data(self):
        if self._data is None:
            raw_data = yaml.load(open(self._filepath))
            self._data = {r[self.key]: r for r in raw_data}

    def __getitem__(self, key):
        self._load_data()
        return self._data[key]

    def __iter__(self):
        self._load_data()
        return iter(self._data)

    def __len__(self):
        self._load_data()
        return len(self._data())


class DateTimeSerializer(tinydb_serialization.Serializer):
    OBJ_CLASS = datetime.datetime
    fmt = "%Y-%m-%dT%H:%M:%S"

    def encode(self, obj):
        return obj.strftime(self.fmt)

    def decode(self, datestr):
        return datetime.datetime.strptime(datestr, self.fmt)


class TimeSerializer(DateTimeSerializer):
    OBJ_CLASS = datetime.time
    fmt = "%H:%M:%S"


class DateSerializer(DateTimeSerializer):
    OBJ_CLASS = datetime.date
    fmt = "%Y-%m-%d"


class Collisions(tinydb.TinyDB):
    def exists(self, case_no):
        collision = tinydb.Query()
        return bool(self.get(collision.case_no == case_no))

    def parsed(self, case_no):
        collision = tinydb.Query()
        return bool(self.get((collision.case_no == case_no) &
                             (collision.parsed == True)))


_base_path = None

# fixtures
injury_region = Fixture("injury_region.yml")
injury_severity = Fixture("injury_severity.yml")
location = Fixture("location.yml", key="name")
hit_and_run_status = Fixture("hit_and_run_status.yml", key="name")

# databases
tickets = None
collisions = None
traffic = None


def init(db_path, fixture_path):
    global _base_path, tickets, collisions, traffic
    _base_path = fixture_path

    serialization = tinydb_serialization.SerializationMiddleware()
    serialization.register_serializer(DateTimeSerializer(), 'TinyDateTime')
    serialization.register_serializer(DateSerializer(), 'TinyDate')
    serialization.register_serializer(TimeSerializer(), 'TinyTime')

    tickets = tinydb.TinyDB(os.path.join(db_path, "tickets.json"),
                            storage=serialization)
    collisions = Collisions(os.path.join(db_path, "collisions.json"),
                            storage=serialization)
    traffic = tinydb.TinyDB(os.path.join(db_path, "traffic.json"),
                            storage=serialization)
