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
            tickets = self.db.query(models.Ticket).join(
                models.Collision).filter(
                    models.Collision.road_location_name.isnot(None)).filter(
                        models.Collision.road_location_name != "not involved").order_by(
                            models.Collision.date, models.Collision.time).all()
            for ticket in tickets:
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
            crashes = self.db.query(models.Collision).filter(
                models.Collision.road_location_name.isnot(None)).filter(
                    models.Collision.road_location_name != "not involved").order_by(
                        models.Collision.date, models.Collision.time).all()
            for crash in crashes:
                if crash.geojson:
                    geojson = json.loads(crash.geojson)
                else:
                    geojson = {}
                zipcode = geojson.get("properties", {}).get("postal")
                row = [crash.case_no, crash.dob, crash.gender,
                       crash.initials, crash.date, crash.time]
                if crash.injury_region:
                    row.append(crash.injury_region.desc)
                else:
                    row.append(None)
                if crash.injury_severity:
                    row.append(crash.injury_severity.desc)
                else:
                    row.append(None)
                row.extend(
                    [crash.location, zipcode, crash.latitude, crash.longitude,
                     crash.hit_and_run, crash.hit_and_run_status_name,
                     crash.road_location_name, crash.report])
                writer.writerow(row)
                rows += 1
        LOG.info("Dumped %s rows to %s", rows, output_path)

    def dump_traffic(self):
        for ttype in ("bike", "car"):
            output_path = os.path.join(self.options.csvdir,
                                       "%s-%s.csv" % (
                                           models.Traffic.__tablename__,
                                           ttype))
            LOG.info("Dumping data on %s traffic from %r table to %s",
                     ttype, models.Traffic.__tablename__, output_path)
            rows = 0
            with open(output_path, "w") as outfile:
                writer = unicodecsv.writer(outfile, encoding="utf-8",
                                           dialect=csv.excel)
                writer.writerow(("Date", "Start", "End", "Count", "Location"))
                traffic = self.db.query(models.Traffic).filter(
                    models.Traffic.type == ttype).order_by(
                        models.Traffic.date,
                        models.Traffic.start).all()
                for record in traffic:
                    writer.writerow((record.date, record.start, record.end,
                                     record.count, record.location))
                    rows += 1
                LOG.info("Dumped %s rows to %s", rows, output_path)

    def __call__(self):
        if not os.path.exists(self.options.csvdir):
            os.makedirs(self.options.csvdir)

        self.dump_tickets()
        self.dump_collisions()
        self.dump_traffic()
