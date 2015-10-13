"""Geocode accident locations."""

from __future__ import print_function

import copy
import json
import logging
import operator
import os
import re
import textwrap

import geocoder
import termcolor
from six.moves import input

from crashes.cmd import base
from crashes.cmd import curate


LOG = logging.getLogger(__name__)


def _new_geojson():
    return {"type": "FeatureCollection",
            "features": []}


class Geocode(base.Command):
    """Geocode accident locations."""

    prerequisites = [curate.Curate]

    location_separator = re.compile(r'\s*(?:[/&,;]|\b(?:and|at|on)\b)\s*',
                                    re.I)
    dash_split = re.compile(r'\s*-+\s*')
    direction_re = re.compile(r'.*?\s*(?:-|\bto\b)\s*(.*)', re.I)
    address_re = re.compile(r'^\d+ \w+')
    o_re = re.compile(r'\bO\b')
    quote_re = re.compile(r'[\'"]([A-Z])[\'"]')
    no_space_re = re.compile(r'([NS])(\d+)')

    def _fan_out_duplicates(self, features):
        retval = []
        shift = 0.0001
        adj = [-shift, -shift]
        for feature in features:
            new = copy.copy(feature)
            LOG.debug("Adjusting coordinates for %s by %s" %
                      (new['properties']['case_no'], adj))
            new['geometry']['coordinates'] = map(
                lambda c: operator.add(*c),
                zip(new['geometry']['coordinates'], adj))
            retval.append(new)

            adj[0] += shift
            if adj[0] > shift:
                adj[0] = -shift
                adj[1] += shift
                if adj[1] > shift:
                    shift += shift
                    adj = [-shift, -shift]
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
            LOG.debug("Location %s seems to be an intersection" % location)
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
            retval = self.no_space_re.sub(
                r'\1 \2',
                self.o_re.sub(
                    'East O',
                    self.quote_re.sub(r'\1 ', retval)))

            LOG.debug("Transformed address from %s to %s" % (location, retval))
            return retval, True
        elif self.address_re.search(location):
            # not an intersection, but an address, so use as-is
            LOG.debug("Location %s seems to be an address" % location)
            return location, True
        else:
            # only one street found, so this is useless
            LOG.debug("Location %s is not automatically parseable" % location)
            return location, False

    def _get_coordinates(self, case_no, report):
        retval = None
        ans = None
        while True:
            default, usable = self._parse_location(report['location'])
            if not usable or retval:
                # either the default location isn't immediately
                # searchable; or this is our second time through the
                # loop, so we have to prompt for user interactionn
                print("Original: %s" %
                      termcolor.colored(report['location'], "green"))
                print("Default: %s" % termcolor.colored(default, "green"))
                ans = input("Enter to %s, 's' to skip, or enter address: " %
                            ("accept" if retval else "search"))
                if ans in ['s', 'S']:
                    return None
                if retval and not ans:
                    return retval
            else:
                LOG.debug("Transformed address %s is immediately usable in "
                          "search" % default)
            address = (ans or default) + ", Lincoln, NE"
            loc = geocoder.google(address)
            retval = loc.geojson
            if not retval['properties']['ok']:
                print("Error finding %s: %s" %
                      (address, retval['properties']['status']))
            else:
                retval['properties']['case_no'] = case_no
                # remove some of the extraneous junk from the geojson
                # properties
                for key in ('status', 'confidence', 'ok', 'encoding',
                            'geometry', 'provider', 'bbox', 'location', 'lat',
                            'lng', 'accuracy', 'quality', 'method'):
                    del retval['properties'][key]
                print("Address: %s" %
                      termcolor.colored(retval['properties']['address'],
                                        "green", attrs=["bold"]))

    def _load_geojson(self, filename):
        fpath = os.path.join(self.options.geocoding, filename)
        if os.path.exists(fpath):
            retval = json.load(open(fpath))
            LOG.debug("Loaded geocoding data (%s features) from %s" %
                      (len(retval['features']), fpath))
        else:
            retval = _new_geojson()
            LOG.debug("Created new GeoJSON dataset for %s" % fpath)
        return retval

    def _save_geojson(self, data, filename):
        fpath = os.path.join(self.options.geocoding, filename)
        LOG.debug("Saving geocoding data (%s features) to %s" %
                  (len(data['features']), fpath))
        return json.dump(data, open(fpath, 'w'))

    def __call__(self):
        data = json.load(open(self.options.all_reports))
        curation_data = json.load(open(self.options.curation_results))
        del curation_data['not_involved']

        all_geojson = self._load_geojson("all.json")

        skipfile = os.path.join(self.options.geocoding, "skip.json")
        if os.path.exists(skipfile):
            skips = json.load(open(skipfile))
        else:
            skips = []

        coded = [f['properties']['case_no']
                 for f in all_geojson['features']]

        all_curated = reduce(operator.add, curation_data.values())
        for case_no in all_curated:
            if case_no in coded + skips:
                continue
            report = data[case_no]
            print(termcolor.colored("%-10s %50s" % (case_no, report['date']),
                                    'red', attrs=['bold']))
            print(textwrap.fill(report['report']))
            geojson = self._get_coordinates(case_no, report)
            if geojson is None:
                skips.append(case_no)
            else:
                all_geojson['features'].append(geojson)
            print()
            coded.append(case_no)

            self._save_geojson(all_geojson, "all.json")
            json.dump(skips, open(skipfile, "w"))
            LOG.info("%s/%s coded (%.02f%%)" %
                     (len(coded), len(all_curated),
                      100.0 * len(coded) / len(all_curated)))

        # introduce very small variations in cases with identical
        # coordinates.
        duplicates = {}
        for feature in all_geojson['features']:
            key = (round(feature['geometry']['coordinates'][0], 6),
                   round(feature['geometry']['coordinates'][1], 6))
            duplicates.setdefault(key, []).append(feature)

        for features in duplicates.values():
            if len(features) > 1:
                for feature in features:
                    all_geojson['features'].remove(feature)
                all_geojson['features'].extend(
                    self._fan_out_duplicates(features))

        # create categorized GeoJSON files
        by_loc = {k: _new_geojson() for k in curation_data.keys()}
        for feature in all_geojson['features']:
            for loc, cases in curation_data.items():
                if feature['properties']['case_no'] in cases:
                    by_loc[loc]['features'].append(feature)
                    break
            else:
                LOG.warning("Unable to determine crash location for %s" %
                            feature['properties']['case_no'])
        for loc, data in by_loc.items():
            self._save_geojson(data, "%s.json" % loc)

    def satisfied(self):
        return os.path.exists(self.options.geocoding)
