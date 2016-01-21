"""Find crashes near certain features."""

import collections
import json
import math
import os
import re

from crashes.cmd import curate
from crashes.cmd import geocode
from crashes import log

LOG = log.getLogger(__name__)

# estimates of the length of degress of latitude/longitude in
# meters. this is a reasonable estimate because the area we're dealing
# with is so small.
LATITUDE_SIZE = 111051.65
LONGITUDE_SIZE = 84281.54

Point = collections.namedtuple("Point", ["longitude", "latitude"])


def _rectilinear_segment_distance(point, start_point, end_point):
    """Calculate the rectilinear distance between a point and a line segment.

    There are lots of formulas online to calculate the distance
    between a point and a (infinite) line, but we need one for a
    segment. I could only find a rectilinear formula for that, and my
    trig isn't nearly strong enough to figure out the great-circle
    variant. Cross-track distance (XTD) does *not* work,
    unfortunately, since it presumes an infinite-ish track.

    Since we're dealing with fairly small distances, the error
    introduced by doing these calculations rectilinearly should be
    pretty small. In most cases, we only care about distances of a few
    meters.

    This code was found at
    http://stackoverflow.com/questions/849211/shortest-distance-between-a-point-and-a-line-segment
    """
    long_delta = LONGITUDE_SIZE * (end_point.longitude - start_point.longitude)
    lat_delta = LATITUDE_SIZE * (end_point.latitude - start_point.latitude)

    u = min(max(
        ((point.latitude * LATITUDE_SIZE -
          start_point.latitude * LATITUDE_SIZE) * lat_delta +
         (point.longitude * LONGITUDE_SIZE -
          start_point.longitude * LONGITUDE_SIZE) * long_delta) /
        (pow(long_delta, 2) + pow(lat_delta, 2)),
        0), 1)

    return math.sqrt(
        pow((point.latitude * LATITUDE_SIZE + u * lat_delta) -
            end_point.latitude * LATITUDE_SIZE, 2) +
        pow((point.longitude * LONGITUDE_SIZE + u * long_delta) -
            end_point.longitude * LONGITUDE_SIZE, 2))


def feature_distance(feature1, feature2):
    if feature1["geometry"]["type"] == "Point":
        point = Point(*feature1["geometry"]["coordinates"])
        line = feature2
    elif feature2["geometry"]["type"] == "Point":
        point = Point(*feature2["geometry"]["coordinates"])
        line = feature1
    else:
        raise Exception("Neither feature was a point")

    if line["geometry"]["type"] == "LineString":
        lines = [line["geometry"]["coordinates"]]
    elif line["geometry"]["type"] == "MultiLineString":
        lines = line["geometry"]["coordinates"]
    else:
        raise Exception("Cannot calculate distance from point to %s" %
                        line["geometry"]["type"])

    min_dist = None
    for line in lines:
        for i, coords in enumerate(line):
            if i == 0:
                continue
            start_point = Point(*coords)
            end_point = Point(*line[i - 1])

            distance = _rectilinear_segment_distance(point, start_point, end_point)
            if min_dist is None or distance < min_dist:
                min_dist = distance
    return min_dist


class Locate(curate.Curate):
    """Find collisions near certain features."""

    highlight_re = re.compile(
        r'((?:bi|tri|pedal)cycle|bike|(?:bi)?cyclist|'
        r'crosswalk|sidewalk|intersection|'
        r'(?:bike)?path)',
        re.I)

    prerequisites = [geocode.Geocode]

    statuses = curate.StatusDict()
    statuses["Y"] = curate.CurationStatus(
        "row", "Collision related to right-of-way in a bike path")
    statuses["N"] = curate.CurationStatus(
        "non-path", "Collision unrelated to bike path")
    statuses["X"] = curate.CurationStatus(
        "non-row", "Collision in bike path, but unrelated to right-of-way")
    statuses["S"] = curate.CurationStatus(
        "sidewalk", "ROW-related collision in a private drive on a bike path")

    results_file = "lb716_results"

    threshold = 150

    def _load_geojson(self, filename):
        return json.load(open(os.path.join(self.options.geocoding, filename)))

    def _find_collisions(self, collision_types, feature_selector,
                         max_distance):
        for ctype in collision_types:
            cdata = self._load_geojson("%s.json" % ctype)
            for bike_route in self.bike_routes["features"]:
                if feature_selector(bike_route):
                    for collision in cdata["features"]:
                        dist = feature_distance(collision,
                                                bike_route)
                        if dist <= max_distance:
                            LOG.debug("%s was %s meters from %s" %
                                      (collision["properties"]["case_no"],
                                       dist, bike_route["properties"]["name"]))
                            self.collisions[
                                collision["properties"]["case_no"]] = (
                                    bike_route["properties"]["name"])

    def _print_additional_info(self, case_no):
        for location, cases in self.curation_data.items():
            if case_no in cases:
                print("Location: %s" % location.title())
                break
        print("Bike path: %s" % self.collisions[case_no])

    def _get_default(self, case_no):
        if case_no in self.curation_data["sidewalk"]:
            return "S"
        return "N"

    def _load_data(self):
        super(Locate, self)._load_data()
        self.collisions = {}
        self.bike_routes = json.load(open(self.options.bike_route_geojson))
        self.curation_data = json.load(open(self.options.curation_results))

        self._find_collisions(
            ["sidewalk", "crosswalk"],
            lambda f: f["properties"]["type"] == "Street-adjacent",
            self.threshold)
        self._find_collisions(
            ["crosswalk"],
            lambda f: f["properties"]["type"] == "Off-street",
            self.threshold)

        total_cases = len(self.data)
        self.data = collections.OrderedDict(
            sorted([(case_no, report) for case_no, report in self.data.items()
                    if case_no in self.collisions],
                   key=lambda d: self.collisions[d[0]]))
        LOG.debug(self.data)
        LOG.debug("Curating %s cases (out of %s total)" % (len(self.data),
                                                           total_cases))
