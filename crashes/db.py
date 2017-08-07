"""Databases and fixtures.

Databases are mutable JSON; fixtures are immutable YAML.

We get a lot of the functionality below from tinydb, but tinydb is
*really* *slow*, so we have to NIH this. The two main features we add
are delayed database loading (until we need data from it) and delayed
serialization (until we actually request data from a record).
"""

import abc
import collections
import datetime
import logging
import json
import os

import six
import yaml

LOG = logging.getLogger(__name__)


class DatabaseNotReady(Exception):
    """Database is not ready to load."""


class NoSuchDatabase(Exception):
    """No such database."""


class SerializationNotSupported(Exception):
    """Can't serialize objects of this type."""


class DeserializationNotSupported(Exception):
    """Can't deserialize objects of this type."""


@six.add_metaclass(abc.ABCMeta)
class Serializer(object):
    cls = None

    @property
    def _magic(self):
        return "{%s}" % self.__class__.__name__

    def serialize(self, value):
        """Serialize a value, including the magic to flag it as serialized."""
        if isinstance(value, self.cls):
            return "%s%s" % (self._magic, self.encode(value))
        raise SerializationNotSupported("%r is not of type %s" %
                                        (value, self.cls))

    def deserialize(self, value):
        """Deserialize a value, stripping the magic flag."""
        try:
            if value.startswith(self._magic):
                raw_value = value[len(self._magic):]
                return self.decode(raw_value)
            raise DeserializationNotSupported("%r doesn't start with %s" %
                                              (value, self._magic))
        except AttributeError:
            return value

    @abc.abstractmethod
    def encode(self, value):
        """Encode a value received from the user."""
        raise NotImplementedError

    @abc.abstractmethod
    def decode(self, value):
        """Decode a value from the database."""
        raise NotImplementedError


class DatetimeSerializer(Serializer):
    cls = datetime.datetime
    fmt = "%Y-%m-%dT%H:%M:%S"

    def converter(self, obj):
        return obj

    def encode(self, value):
        return value.strftime(self.fmt)

    def decode(self, value):
        return self.converter(datetime.datetime.strptime(value, self.fmt))


class TimeSerializer(DatetimeSerializer):
    cls = datetime.time
    fmt = "%H:%M:%S"

    def converter(self, obj):
        return obj.time()


class DateSerializer(DatetimeSerializer):
    cls = datetime.date
    fmt = "%Y-%m-%d"

    def converter(self, obj):
        return obj.date()


class Fixture(collections.Mapping):
    def __init__(self, filename, key="id"):
        self.filename = filename
        self.key = key
        self._data = None

    @property
    def _filepath(self):
        if _fixture_path is None:
            raise DatabaseNotReady(self.filename)
        return os.path.join(_fixture_path, self.filename)

    def _load_data(self):
        if self._data is None:
            LOG.debug("Loading fixture data from %s", self._filepath)
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
        return len(self._data)

    def __str__(self):
        return str(dict(self))

    def __repr__(self):
        return repr(dict(self))


class Database(collections.MutableSequence):
    serializers = [DatetimeSerializer(),
                   DateSerializer(),
                   TimeSerializer()]

    def __init__(self, filename):
        self.filename = filename
        self._data = None
        self._by_key = None

    @property
    def _filepath(self):
        if _db_path is None:
            raise DatabaseNotReady(self.filename)
        return os.path.join(_db_path, self.filename)

    def _load(self):
        if self._data is None:
            LOG.debug("Loading data from %s", self._filepath)
            self._data = json.load(open(self._filepath))

    def _save(self):
        LOG.debug("Saving %s records to %s", len(self._data), self._filepath)
        json.dump(self._data, open(self._filepath, "w"), separators=(',', ':'))

    def _serialize(self, record):
        retval = {}
        for key, val in record.items():
            for serializer in self.serializers:
                try:
                    retval[key] = serializer.serialize(val)
                    break
                except SerializationNotSupported:
                    pass
            else:
                retval[key] = val
        return retval

    def _deserialize(self, record):
        retval = {}
        for key, val in record.items():
            for serializer in self.serializers:
                try:
                    retval[key] = serializer.deserialize(val)
                    break
                except DeserializationNotSupported:
                    pass
            else:
                retval[key] = val
        return retval

    def __getitem__(self, key):
        self._load()
        return self._deserialize(self._data[key])

    def __setitem__(self, key, value):
        self._load()
        self._data[key] = self._serialize(value)
        self._save()

    def __delitem__(self, key):
        self._load()
        self._data.pop(key)
        self._save()

    def __len__(self):
        self._load()
        return len(self._data)

    def insert(self, idx, value):
        self._load()
        self._data.insert(idx, self._serialize(value))
        self._save()

    def __str__(self):
        if self._data is None:
            return "%s(%s, not loaded)" % (self.__class__.__name__,
                                           self.filename)
        return "%s(%s=%s)" % (self.__class__.__name__, self.filename, dict(self))

    def __repr__(self):
        if self._data is None:
            return "%s(%s, not loaded)" % (self.__class__.__name__,
                                           self.filename)
        return "%s(%s=%r)" % (self.__class__.__name__, self.filename, dict(self))


class KeyedDatabase(Database):
    def __init__(self, filename, key):
        super(KeyedDatabase, self).__init__(filename)
        self.key = key

    def _save(self):
        super(KeyedDatabase, self)._save()

    def _load(self):
        super(KeyedDatabase, self)._load()
        if self._by_key is None:
            self._by_key = {d[self.key]: i for i, d in enumerate(self._data)}

    def __getitem__(self, idx):
        self._load()
        if idx in self._by_key:
            idx = self._by_key[idx]
        try:
            data = self._data[idx]
        except TypeError:
            raise KeyError(idx)
        return self._deserialize(data)

    def __setitem__(self, idx, value):
        self._load()
        if idx in self._by_key:
            idx = self._by_key[idx]
        super(KeyedDatabase, self).__setitem__(idx, value)
        self._by_key[value[self.key]] = idx

    def __delitem__(self, idx):
        self._load()
        if idx in self._by_key:
            idx = self._by_key[idx]
            del self._by_key[idx]
        super(KeyedDatabase, self).__delitem__(idx)

    def insert(self, idx, value):
        super(KeyedDatabase, self).insert(idx, value)
        self._by_key[value[self.key]] = idx

    def get(self, key, default=None):
        try:
            return self[key]
        except (KeyError, IndexError):
            return default

    def exists(self, key):
        self._load()
        return key in self._by_key

    def update_one(self, record):
        idx = self._by_key[record[self.key]]
        self[idx] = record

    def upsert(self, record):
        if self.exists(record[self.key]):
            self.update_one(record)
        else:
            return self.append(record)


_db_path = None
_fixture_path = None

# fixtures
injury_region = Fixture("injury_region.yml")
injury_severity = Fixture("injury_severity.yml")
location = Fixture("location.yml", key="name")
hit_and_run_status = Fixture("hit_and_run_status.yml", key="name")

# databases
tickets = Database("tickets.json")
collisions = KeyedDatabase("collisions.json", key="case_no")
traffic = Database("traffic.json")


def init(db_path, fixture_path):
    global _db_path, _fixture_path
    LOG.debug("Preloading databases")

    _db_path = db_path
    _fixture_path = fixture_path
