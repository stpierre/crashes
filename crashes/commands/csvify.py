"""Collision database operations."""

import csv
import datetime
import logging
import operator
import os

import unicodecsv

from crashes.commands import base
from crashes import db

LOG = logging.getLogger(__name__)


def _collision_row_sort(row):
    date = row[4]
    if date is None:
        date = datetime.date.fromtimestamp(0)
    time = row[5]
    if time is None:
        time = datetime.time()
    return (date, time)


def _ticket_row_sort(row):
    case_no = row[0]
    report = db.collisions[case_no]
    date = report.get("date") or datetime.date.fromtimestamp(0)
    time = (report.get("time")
            if report.get("time") is not None else datetime.time())
    return (date, time)


class CSVify(base.Command):
    """Collision database operations."""

    def dump_tickets(self):
        output_path = os.path.join(self.options.csvdir, "ticket.csv")
        LOG.info("Dumping data from %s to %s", db.tickets.filename,
                 output_path)
        rows = []
        for ticket in db.tickets:
            report = db.collisions[ticket["case_no"]]
            if report.get("road_location") in ("None", "not involved"):
                continue
            rows.append((ticket["case_no"], ticket["initials"],
                         ticket["desc"]))
        rows.sort(key=_ticket_row_sort)

        with open(output_path, "w") as outfile:
            writer = unicodecsv.writer(
                outfile, encoding="utf-8", dialect=csv.excel)
            writer.writerow(("Case #", "Initials", "Description"))
            writer.writerows(rows)
        LOG.info("Dumped %s rows to %s", len(rows), output_path)

    def dump_collisions(self):
        output_path = os.path.join(self.options.csvdir, "collision.csv")
        LOG.info("Dumping data from %s to %s", db.collisions.filename,
                 output_path)
        rows = []
        for crash in db.collisions:
            if crash.get("road_location") in (None, "not involved"):
                continue
            row = [
                crash["case_no"],
                crash.get("dob"),
                crash.get("gender"),
                crash.get("initials"), crash["date"], crash["time"]
            ]
            if crash.get("injury_region"):
                row.append(db.injury_region[crash["injury_region"]]["desc"])
            else:
                row.append(None)
            if crash.get("injury_severity"):
                row.append(
                    db.injury_severity[crash["injury_severity"]]["desc"])
            else:
                row.append(None)
            row.append(crash.get("location"))
            if crash.get("geojson"):
                row.append(
                    crash["geojson"].get("properties", {}).get("postal"))
            else:
                row.append(None)

            row.extend([
                crash.get("latitude"),
                crash.get("longitude"),
                crash.get("hit_and_run"),
                crash.get("hit_and_run_status"),
                crash.get("road_location"),
                crash.get("report")
            ])
            rows.append(row)
        rows.sort(key=_collision_row_sort)

        with open(output_path, "w") as outfile:
            writer = unicodecsv.writer(
                outfile, encoding="utf-8", dialect=csv.excel)
            writer.writerow(
                ("Case #", "Cyclist DOB", "Cyclist gender", "Cyclist initials",
                 "Date", "Time", "Injury region", "Injury severity",
                 "Location", "ZIP", "Latitude", "Longitude", "Hit and run?",
                 "Hit and runner", "Road location", "Report"))
            writer.writerows(rows)
        LOG.info("Dumped %s rows to %s", len(rows), output_path)

    def dump_traffic(self):
        for ttype in ("bike", "car"):
            output_path = os.path.join(self.options.csvdir,
                                       "traffic-%s.csv" % ttype)
            LOG.info("Dumping data on %s traffic from %s to %s", ttype,
                     db.traffic.filename, output_path)
            rows = []
            for record in db.traffic:
                if record["type"] == ttype:
                    rows.append(
                        (record["date"], record["start"], record["end"],
                         record["count"], record["location"]))
            rows.sort(key=operator.itemgetter(0, 1))

            with open(output_path, "w") as outfile:
                writer = unicodecsv.writer(
                    outfile, encoding="utf-8", dialect=csv.excel)
                writer.writerow(("Date", "Start", "End", "Count", "Location"))
                writer.writerows(rows)
                LOG.info("Dumped %s rows to %s", len(rows), output_path)

    def __call__(self):
        if not os.path.exists(self.options.csvdir):
            os.makedirs(self.options.csvdir)

        self.dump_tickets()
        self.dump_collisions()
        self.dump_traffic()
