"""Geocode accident locations."""

from __future__ import print_function

import copy
import json
import logging
import operator
import os
import random
import re
import textwrap

import geocoder
from six.moves import input
import termcolor

from crashes.commands import base
from crashes import db

LOG = logging.getLogger(__name__)


def new_geojson():
    return {"type": "FeatureCollection", "features": []}


def cleanup_geojson(geojson, case_no):
    retval = copy.deepcopy(geojson)
    retval['properties']['case_no'] = case_no
    # remove some of the extraneous junk from the geojson properties
    for key in ('status', 'confidence', 'ok', 'encoding', 'geometry',
                'provider', 'bbox', 'location', 'lat', 'lng', 'accuracy',
                'quality', 'method'):
        if key in retval["properties"]:
            del retval['properties'][key]
    return retval


def _save_geojson(data, filepath):
    LOG.debug("Saving geocoding data (%s features) to %s",
              len(data['features']), filepath)
    return json.dump(data, open(filepath, 'w'))


def save_categorized_geojson(reports, geocoding_dir):
    """create categorized GeoJSON files."""
    categories = set(r["road_location"] for r in reports)
    by_loc = {c: new_geojson() for c in categories}
    all_collisions = new_geojson()
    for report in reports:
        by_loc[report["road_location"]]["features"].append(report["geojson"])
        all_collisions["features"].append(report["geojson"])
    for loc, data in by_loc.items():
        fpath = os.path.join(geocoding_dir, "%s.json" % loc.replace(" ", "_"))
        _save_geojson(data, fpath)
    _save_geojson(all_collisions, os.path.join(geocoding_dir, "all.json"))


class Geocode(base.Command):
    """Geocode accident locations."""

    location_separator = re.compile(r'\s*(?:[/&,;]|\b(?:and|at|on)\b)\s*',
                                    re.I)
    dash_split = re.compile(r'\s*-+\s*')
    direction_re = re.compile(r'.*?\s*(?:-|\bto\b)\s*(.*)', re.I)
    address_re = re.compile(r'^\d+ \w+')
    o_re = re.compile(r'\bO\b')
    quote_re = re.compile(r'[\'"]([A-Z])[\'"]')
    no_space_re = re.compile(r'([NS])(\d+)')

    jitter_max = 0.00015
    jitter_min = 0.00001

    quit = object()

    def _random_jitter(self):
        val = (random.random() *
               (self.jitter_max - self.jitter_min) + self.jitter_min)
        if random.choice((True, False)):
            val *= -1
        return val

    def _jitter_duplicates(self, reports):
        retval = []
        for report in reports:
            adj = (self._random_jitter(), self._random_jitter())
            LOG.debug("Adjusting coordinates for %s by %s", report["case_no"],
                      adj)
            report["geojson"]['geometry']['coordinates'] = [
                operator.add(*c)
                for c in zip(report["geojson"]['geometry']['coordinates'], adj)
            ]
            report["latitude"] = report["geojson"]["geometry"]["coordinates"][
                1]
            report["longitude"] = report["geojson"]["geometry"]["coordinates"][
                0]
        db.collisions.update_many(reports)
        return retval

    def _parse_location(self, location):
        """Parse a location from an accident report.

        Returns a tuple of (address, searchable). ``address`` is a
        hopefully more correct address; ``searchable`` is a boolean
        indicating whether or not this new, better address should
        actually be used for geocoding, or if the user should be
        prompted first.
        """
        # hopefully two streets (an intersection!) are specified
        streets = self.location_separator.split(location)
        if len(streets) < 2:
            # splitting failed, try to split on dash
            streets = self.dash_split.split(location)
        if len(streets) == 2:
            LOG.debug("Location %s seems to be an intersection", location)
            # many locations are expressed as A/B-C, where A is the street
            # that the cyclist was proceeding along, from B to C. (Or
            # B-C/A.) Handle that.
            for i, street in enumerate(streets):
                match = self.direction_re.search(street)
                if match:
                    streets[i] = match.group(1)
            retval = " & ".join(streets)

            # Allow for some mistakes that google makes:
            #
            # * In intersections, assumes that "O" means "West O", not
            #   (East) O
            # * Has no idea what to do with quoted letter streets,
            #   e.g. "56th & 'A'"
            # * Gets confused if there's no space between the
            #   direction and street number, e.g., 'S40th' instead of
            #   'S 40th'.
            retval = self.no_space_re.sub(r'\1 \2',
                                          self.o_re.sub(
                                              'East O',
                                              self.quote_re.sub(
                                                  r'\1 ', retval)))

            LOG.debug("Transformed address from %s to %s", location, retval)
            return retval, True
        elif self.address_re.search(location):
            # not an intersection, but an address, so use as-is
            LOG.debug("Location %s seems to be an address", location)
            return location, True
        else:
            # only one street found, so this is useless
            LOG.debug("Location %s is not automatically parseable", location)
            return location, False

    def _get_coordinates(self, report):
        retval = None
        ans = None
        while True:
            default, usable = self._parse_location(report["location"])
            if not usable or retval:
                # either the default location isn't immediately
                # searchable; or this is our second time through the
                # loop, so we have to prompt for user interactionn
                print("Original: %s" % termcolor.colored(
                    report["location"], "green"))
                print("Default: %s" % termcolor.colored(default, "green"))
                ans = input("Enter to %s, 's' to skip, or enter address: " %
                            ("accept" if retval else "search"))
                if ans.upper() == 'S':
                    return None
                if ans.upper() == 'Q':
                    return self.quit
                if retval and not ans:
                    return retval
            else:
                LOG.debug("Transformed address %s is immediately usable in "
                          "search", default)
            address = (ans or default) + ", Lincoln, NE"
            loc = geocoder.google(address)
            retval = loc.geojson
            if not retval['properties']['ok']:
                LOG.error("Error finding %s: %s", address,
                          retval['properties']['status'])
            else:
                retval = cleanup_geojson(retval, report["case_no"])
                print("Address: %s" % termcolor.colored(
                    retval['properties']['address'], "green", attrs=["bold"]))

    def _load_geojson(self, filename, create=True):
        fpath = os.path.join(self.options.geocoding, filename)
        if not create or os.path.exists(fpath):
            retval = json.load(open(fpath))
            LOG.debug("Loaded geocoding data (%s features) from %s",
                      len(retval['features']), fpath)
        else:
            retval = new_geojson()
            LOG.debug("Created new GeoJSON dataset for %s", fpath)
        return retval

    def __call__(self):
        coded = 0
        for report in db.collisions:
            if (report.get("road_location") not in (None, "not involved")
                    and not report.get("skip_geojson")
                    and report.get("geojson") is None):
                print(termcolor.colored(
                    "%-10s %50s" % (report["case_no"], report["date"]),
                    'red',
                    attrs=['bold']))
                print(textwrap.fill(report["report"]))
                geojson = self._get_coordinates(report)
                if geojson is None:
                    report["skip_geojson"] = True
                elif geojson == self.quit:
                    break
                else:
                    report["geojson"] = geojson
                    report["latitude"] = geojson["geometry"]["coordinates"][1]
                    report["longitude"] = geojson["geometry"]["coordinates"][0]
                    report["skip_geojson"] = False
                db.collisions.update(report)
                coded += 1
                print()

        if coded == 0:
            # no new geocoding, so we don't need to muck with the
            # existing files
            return 0

        # introduce jitter in cases with identical coordinates.
        duplicates = {}
        geocoded = []
        for report in db.collisions:
            if report.get("geojson"):
                geocoded.append(report)
                key = (round(
                    report["geojson"]['geometry']['coordinates'][0], 6), round(
                        report["geojson"]['geometry']['coordinates'][1], 6))
                duplicates.setdefault(key, []).append(report)

        for reports in duplicates.values():
            if len(reports) > 1:
                self._jitter_duplicates(reports)

        save_categorized_geojson(geocoded, self.options.geocoding)
