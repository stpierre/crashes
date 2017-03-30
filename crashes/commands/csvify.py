"""Collision database operations."""

import csv
import json
import logging
import os

import unicodecsv

from crashes.commands import base
from crashes import models

LOG = logging.getLogger(__name__)


class CSVify(base.Command):
    """Collision database operations."""

    def dump_tickets(self):
        output_path = os.path.join(self.options.csvdir,
                                   "%s.csv" % models.Ticket.__tablename__)
        LOG.info("Dumping data from %r table to %s",
                 models.Ticket.__tablename__, output_path)
        rows = 0
        with open(output_path, "w") as outfile:
            writer = unicodecsv.writer(outfile, encoding="utf-8",
                                       dialect=csv.excel)
            writer.writerow(("Case #", "Initials", "Description"))
            for ticket in self.db.query(models.Ticket).all():
                writer.writerow((ticket.case_no, ticket.initials, ticket.desc))
                rows += 1
        LOG.info("Dumped %s rows to %s", rows, output_path)

    def dump_collisions(self):
        output_path = os.path.join(self.options.csvdir,
                                   "%s.csv" % models.Collision.__tablename__)
        LOG.info("Dumping data from %r table to %s",
                 models.Collision.__tablename__, output_path)
        rows = 0
        with open(output_path, "w") as outfile:
            writer = unicodecsv.writer(outfile, encoding="utf-8",
                                       dialect=csv.excel)
            writer.writerow(("Case #", "Cyclist DOB", "Cyclist gender",
                             "Cyclist initials", "Date", "Time",
                             "Injury region", "Injury severity",
                             "Location", "ZIP", "Latitude", "Longitude",
                             "Hit and run?", "Hit and runner",
                             "Road location", "Report"))
            for crash in self.db.query(models.Collision).all():
                if crash.geojson:
                    geojson = json.loads(crash.geojson)
                else:
                    geojson = {}
                zipcode = geojson.get("properties", {}).get("postal")
                row = (crash.case_no, crash.dob, crash.gender,
                       crash.initials, crash.date, crash.time,
                       crash.injury_region, crash.injury_severity,
                       crash.location, zipcode, crash.latitude, crash.longitude,
                       crash.hit_and_run, crash.hit_and_run_status,
                       crash.road_location_name, crash.report)
                writer.writerow(row)
                rows += 1
        LOG.info("Dumped %s rows to %s", rows, output_path)

    def __call__(self):
        if not os.path.exists(self.options.csvdir):
            os.makedirs(self.options.csvdir)

        self.dump_tickets()
        self.dump_collisions()
