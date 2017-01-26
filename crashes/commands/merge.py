"""Merge data from Matney 2014 study.

http://www.arcgis.com/home/webmap/viewer.html?webmap=76d544b5646645dcaa8e9ba5c5543d0a
"""

import argparse
import copy
import csv
import datetime
import json
import operator
import os

import geocoder
from six.moves import input

from crashes.commands import base
from crashes.commands import curate
from crashes.commands import geocode
from crashes.commands import jsonify
from crashes import log

LOG = log.getLogger(__name__)

# How close an LPD collision must be to an NDOR collision to be
# considered as a possible duplicate. This is about a 4- to 5-block
# radius
LOCATION_FUZZ = 0.006
# How close in seconds an LPD collision must be to an NDOR
# collision. luckily, this appears to always be an exact match.
TIME_FUZZ = 60


class Merge(base.Command):
    """Merge data from Matney 2014 study."""

    prerequisites = [geocode.Geocode]

    arguments = [base.Argument("filename", type=argparse.FileType("r"))]

    def __init__(self, options):
        super(Merge, self).__init__(options)
        self._metadata = json.load(open(self.options.metadata))
        self._curation_data = json.load(open(self.options.curation_results))
        relevant = reduce(operator.add, self._curation_data.values())
        self._all_reports = json.load(open(self.options.all_reports))

        self._all_geojson = json.load(open(os.path.join(self.options.geocoding,
                                                        "all.json")))
        for feature in self._all_geojson["features"]:
            collision = self._all_reports[feature["properties"]["case_no"]]
            (collision["longitude"],
             collision["latitude"]) = feature["geometry"]["coordinates"]

        self._by_date = {}
        for case_no in relevant:
            collision = self._all_reports[case_no]
            self._by_date.setdefault(collision["date"], []).append(collision)

        self.filename = options.filename

    def _save_data(self):
        json.dump(self._all_reports, open(self.options.all_reports, "w"))
        json.dump(self._curation_data, open(self.options.curation_results, "w"))
        json.dump(self._all_geojson, open(os.path.join(self.options.geocoding,
                                                       "all.json"), "w"))

    def _get_duplicates(self, row):
        date = datetime.datetime.strptime(row["AccidentDate"], "%m/%d/%Y")
        candidates = []
        for collision in self._by_date.get(date.strftime("%Y-%m-%d"), []):

            LOG.debug("Comparing %r and %r" % (row["Time"], collision["time"]))
            lpd_time = None
            ndor_time = None
            try:
                lpd_time = datetime.datetime.strptime(collision["time"],
                                                      "%H:%M")
                ndor_time = datetime.datetime.strptime(row["Time"], "%H%M")
            except (TypeError, ValueError):
                # can't do time comparison, just assume that it's a
                # possible duplicate
                pass

            # amazingly, abs() works on timedelta objects :D
            if (lpd_time is None or ndor_time is None or
                    abs(lpd_time - ndor_time).seconds < TIME_FUZZ):
                # sometimes we can't geocode a collision because we
                # don't know where it happened -- e.g., a hit-and-run
                # on a child who doesn't know street names. If times
                # match, just assume that it's a matching collision
                if "latitude" in collision:
                    lat_diff = abs(collision["latitude"] -
                                   float(row["Latitude"]))
                    long_diff = abs(collision["longitude"] -
                                    float(row["Longitude"]))
                    LOG.debug("Comparing %s, %s to %s, %s",
                              collision["latitude"], collision["longitude"],
                              row["Latitude"], row["Longitude"])
                    LOG.debug("Coordinates difference: %s, %s",
                              lat_diff, long_diff)
                else:
                    LOG.debug("No coordinates for possible duplicates")
                    lat_diff = long_diff = 0
                if lat_diff < LOCATION_FUZZ and long_diff < LOCATION_FUZZ:
                    LOG.debug("Found possible duplicate: %s",
                              collision["case_number"])
                    candidates.append(collision)
        if len(candidates) > 1:
            # this shouldn't happen; our candidate search is
            # sufficiently restrictive that we only find at
            # most one candidate per NDOR collision record.
            raise Exception("%s: %s" % (row["AccidentKey_FromNDOR"],
                                        candidates))
        return candidates

    def _get_report_record(self, row, loc):
        record = {
            "location": loc.address,
            "date": datetime.datetime.strptime(
                row["AccidentDate"], "%m/%d/%Y").strftime("%Y-%m-%d"),
            "report": "From NDOR %s" % row["AccidentKey_FromNDOR"],
            "cyclist_dob": None,
            "injury_severity": int(row["AccidentSeverity_CodeFromNDOR"]),
            "injury_region": None,
            "cyclist_initials": None,
        }
        record["cyclist_injured"] = record["injury_sev"] != 5

        try:
            record["time"] = datetime.datetime.strptime(
                row["Time"], "%H%M").strftime("%H:%M")
        except (TypeError, ValueError):
            record["time"] = None

        print("Collision on %(date)s, %(time)s, at %(location)s" % record)
        case_no = input("LPD case number: ")
        record["case_number"] = case_no
        record["filename"] = "%s.PDF" % case_no.replace("-", "").upper()
        if record["time"] is None:
            collision_time = input("Collision time: ")
            if collision_time:
                record["time"] = collision_time

        dob = input("Cyclist DOB: ")
        if dob:
            record["cyclist_dob"] = dob
        try:
            record["injury_region"] = jsonify.JSONifyChildProcess.injury_regions[
                input("Injury region: ").zfill(2)]
        except KeyError:
            pass

        record["cyclist_initials"] = self._get_initials(case_no)
        return record

    def _curate(self, record):
        for status, cases in self._curation_data.items():
            if record["case_number"] in cases:
                LOG.debug("Found case %s in cases, location=%s",
                          record["case_number"], status)
                return status

        status = curate.Curate.statuses.input()
        self._curation_data.setdefault(status, []).append(
            record["case_number"])
        return status

    def __call__(self):
        added_count = 0
        updated_count = 0

        reader = csv.DictReader(self.filename)
        for row in reader:
            # we're only concerned with bike collisions in Lincoln
            # from 2012 onward
            if (int(row["AccidentYear"]) > 2011 and
                    row["PedestrianOrPedalcyclist"] == "Cyclists" and
                    row["CityName"] == "Lincoln"):
                LOG.debug("Parsing collision %(AccidentKey_FromNDOR)s", row)

                # we have to pad the time with zeros in order for it
                # to be parsed correctly
                row["Time"] = row["Time"].zfill(4)

                candidates = self._get_duplicates(row)
                if len(candidates) == 0:
                    LOG.info(
                        "No possible duplicates found for %s, adding to data",
                        row["AccidentKey_FromNDOR"])

                    loc = geocoder.google([row["Latitude"], row["Longitude"]],
                                          method="reverse")

                    report_record = self._get_report_record(row, loc)
                    case_no = report_record["case_number"]
                    self._all_reports[case_no] = report_record

                    status = self._curate(report_record)

                    if status != "not_involved":
                        geojson = geocode.cleanup_geojson(loc.geojson, case_no)
                        self._all_geojson["features"].append(geojson)

                    added_count += 1
                elif len(candidates) == 1:
                    duplicate = copy.deepcopy(candidates[0])
                    LOG.info(
                        "One possible duplicate found for %s, updating %s",
                        row["AccidentKey_FromNDOR"], duplicate["case_number"])

                    if "latitude" in duplicate:
                        del duplicate["latitude"]
                    if "longitude" in duplicate:
                        del duplicate["longitude"]

                    for feature in self._all_geojson["features"]:
                        if (feature["properties"]["case_no"] ==
                                duplicate["case_number"]):
                            feature["geometry"]["coordinates"] = [
                                float(row["Longitude"]), float(row["Latitude"])]
                    updated_count += 1

                self._save_data()

        geocode.save_categorized_geojson(self._all_geojson, self._curation_data,
                                         self.options.geocoding)
        LOG.info("%s records added, %s records updated",
                 added_count, updated_count)

    def _get_initials(self, case_no):
        retval = None
        if case_no in self._metadata and "tickets" in self._metadata[case_no]:
            initials_list = self._metadata[case_no]["tickets"].keys()
            print("Cyclist initials:")
            for i, initials in enumerate(initials_list):
                print("%s. %s" % (i + 1, initials))
            print("0. None of the above")
            done = False
            while not done:
                try:
                    choice = int(input("Choice: "))
                except ValueError:
                    LOG.debug("Input is not a valid integer")
                    continue
                if choice == 0:
                    done = True
                else:
                    try:
                        retval = initials_list[choice - 1]
                        done = True
                    except IndexError:
                        continue
        return retval

    def satisfied(self):
        """This should never be a prereq, but also should only be run once."""
        return True
