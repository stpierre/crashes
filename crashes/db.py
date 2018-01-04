"""Databases and fixtures.

Databases are mutable JSON; fixtures are immutable YAML.

We get a lot of the functionality below from tinydb, but tinydb is
*really* *slow*, so we have to NIH this. The two main features we add
are delayed database loading (until we need data from it) and delayed
serialization (until we actually request data from a record).
"""

import abc
import collections
import contextlib
import copy
import datetime
import logging
import json
import os

import six
import yaml

from crashes import utils

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
        raise SerializationNotSupported("%r is not of type %s" % (value,
                                                                  self.cls))

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

    def converter(self, obj):  # pylint: disable=no-self-use
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
    def __init__(  # pylint: disable=super-init-not-called
            self, filename, key="id"):
        self.filename = filename
        self.key = key
        self._data = None

    @property
    def _filepath(self):
        if _FIXTURE_PATH is None:
            raise DatabaseNotReady(self.filename)
        return os.path.join(_FIXTURE_PATH, self.filename)

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
    serializers = [DatetimeSerializer(), DateSerializer(), TimeSerializer()]

    def __init__(self, filename):  # pylint: disable=super-init-not-called
        self.filename = filename
        self._data = None
        self._by_key = None
        self._sync = True
        self._needs_write = set()

    @contextlib.contextmanager
    def delay_write(self):
        self._sync = False
        yield
        self._sync = True
        self._save()

    def get_shard(self, record):
        return None

    def _get_filepath(self, suffix=None):
        if _DB_PATH is None:
            raise DatabaseNotReady(self.filename)
        if suffix is None:
            filename = self.filename
        else:
            name, ext = os.path.splitext(self.filename)
            filename = "%s-%s%s" % (name, suffix, ext)
        return os.path.join(_DB_PATH, filename)

    def _load(self):
        if self._data is None:
            self._data = []
            shards = [None]
            shard_filepath = self._get_filepath(suffix="shards")
            if os.path.exists(shard_filepath):
                LOG.debug("Loading list of shards from %s", shard_filepath)
                shards = json.load(open(shard_filepath))

            for shard in shards:
                filepath = self._get_filepath(suffix=shard)
                LOG.debug("Loading data from %s", filepath)
                shard_data = json.load(open(filepath))
                self._data.extend(shard_data)

    def _shard_data(self):
        shards = collections.defaultdict(list)
        for record in self._data:
            shards[self.get_shard(record)].append(record)
        return shards

    def _save(self, force=False):
        if not self._sync:
            return

        sharded_data = self._shard_data()
        abort = False
        wrote_any_shard = False
        for suffix, records in sharded_data.items():
            if not force and suffix not in self._needs_write:
                LOG.debug("Shard %s has no new data, skipping write", suffix)
                continue
            self._needs_write.remove(suffix)

            write_success = False
            while not write_success:
                try:
                    filepath = self._get_filepath(suffix=suffix)
                    LOG.debug("Saving %s records to %s", len(records),
                              filepath)
                    json.dump(
                        records, open(filepath, "w"), separators=(',', ':'))
                    write_success = True
                    wrote_any_shard = True
                except (SystemExit, KeyboardInterrupt):
                    LOG.info("Caught Ctrl-C, "
                             "aborting after database writes are complete")
                    abort = True

        if wrote_any_shard:
            write_success = False
            while not write_success:
                try:
                    shard_filepath = self._get_filepath(suffix="shards")
                    LOG.debug("Saving list of shards to %s", shard_filepath)
                    json.dump(
                        sharded_data.keys(),
                        open(shard_filepath, "w"),
                        separators=(',', ':'))
                    write_success = True
                except (SystemExit, KeyboardInterrupt):
                    LOG.info("Caught Ctrl-C, "
                             "aborting after database writes are complete")
                    abort = True

        if abort:
            raise SystemExit("Caught Ctrl-C during database write")

    def sync(self):
        self._save(force=True)

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
        self._needs_write.add(self.get_shard(self._data[key]))
        self._save()

    def __delitem__(self, key):
        self._load()
        record = self._data.pop(key)
        self._needs_write.add(self.get_shard(record[key]))
        self._save()

    def __len__(self):
        self._load()
        return len(self._data)

    def insert(self, index, value):
        self._load()
        self._data.insert(index, self._serialize(value))
        self._needs_write.add(self.get_shard(self._data[index]))
        self._save()

    def __str__(self):
        if self._data is None:
            return "%s(%s, not loaded)" % (self.__class__.__name__,
                                           self.filename)
        return "%s(%s=%s)" % (self.__class__.__name__, self.filename,
                              dict(self))

    def __repr__(self):
        if self._data is None:
            return "%s(%s, not loaded)" % (self.__class__.__name__,
                                           self.filename)
        return "%s(%s=%r)" % (self.__class__.__name__, self.filename,
                              dict(self))


class KeyedDatabase(Database):
    def __init__(self, filename, key):
        super(KeyedDatabase, self).__init__(filename)
        self.key = key

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

    def record_exists(self, record):
        return self.exists(record[self.key])

    def exists(self, key):
        self._load()
        return key in self._by_key

    def update_one(self, record):
        self._load()
        idx = self._by_key[record[self.key]]
        self[idx] = record

    def merge(self, record):
        self._load()
        idx = self._by_key[record[self.key]]
        new_record = copy.deepcopy(self[idx])
        new_record.update(record)
        # we replace the old record, even though it's slower, in order
        # to ensure that __setitem__() is called, with all of its
        # attendant magic -- updating the key data, saving, etc.
        self[idx] = new_record
        return self[idx]

    update = update_one

    def update_many(self, records):
        for record in records:
            self.update(record)

    def upsert(self, record):
        if self.exists(record[self.key]):
            self.update_one(record)
        else:
            return self.append(record)


class CollisionDatabase(KeyedDatabase):
    def get_shard(self, record):
        if record[self.key].startswith("NDOR"):
            return "NDOR"
        else:
            return record[self.key].strip()[0:2].upper()


_DB_PATH = None
_FIXTURE_PATH = None

# pylint: disable=invalid-name

# fixtures
injury_region = Fixture("injury_region.yml")
injury_severity = Fixture("injury_severity.yml")
location = Fixture("location.yml", key="name")
hit_and_run_status = Fixture("hit_and_run_status.yml", key="name")

# databases
tickets = Database("tickets.json")
collisions = CollisionDatabase("collisions.json", key="case_no")
traffic = Database("traffic.json")


def init(db_path, fixture_path):
    global _DB_PATH, _FIXTURE_PATH  # pylint: disable=global-statement

    _DB_PATH = db_path
    _FIXTURE_PATH = fixture_path
