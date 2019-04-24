"""Command to download reports from LPD."""

import datetime
import logging
import os
import random
import time

import bs4
import requests

from crashes.commands import base
from crashes import db
from crashes import utils

LOG = logging.getLogger(__name__)


def retry(func, args=(), kwargs=None, exceptions=None, times=1, wait=5):
    tries = 0
    if kwargs is None:
        kwargs = {}
    if exceptions is None:
        exceptions = (Exception, )
    while tries < times:
        tries += 1
        try:
            return func(*args, **kwargs)
        except exceptions as err:
            if tries == times:
                LOG.error("Retried %s %s times, failed: %s", func, tries, err)
                raise
            else:
                LOG.info(
                    "%s failed, waiting %s seconds and retrying (%s/%s): %s",
                    func, wait, tries, times, err)
            time.sleep(wait)


class Fetch(base.Command):
    """Download reports from LPD."""
    bs4_parser = "lxml"

    arguments = [
        base.Argument(
            "--start",
            type=lambda d: datetime.datetime.strptime(d, "%Y-%m-%d")),
        base.Argument(
            "--end", type=lambda d: datetime.datetime.strptime(d, "%Y-%m-%d")),
        base.Argument("--autostart", action="store_true"),
        base.Argument("--refetch-curated", action="store_true"),
        base.Argument("--force", action="store_true"),
    ]

    @staticmethod
    def _munge_name(name):
        """Anonymize a name so that it can be compared but not read.

        Even though all of this is public data, I don't want to be
        "leaking" it myself. So we munge names to include just
        initials, which should be enough to uniquely identify the
        people in a collision without storing their names.
        """
        parts = name.split(" (dob) ")
        return " ".join(["".join(w[0] for w in parts[0].split()),
                         parts[1]]).strip()

    def _sleep(self):
        sleep_duration = random.randint(self.options.sleep_min,
                                        self.options.sleep_max)
        LOG.debug("Sleeping %s seconds", sleep_duration)
        time.sleep(sleep_duration)

    def _parse_tickets(self, case_no, url, post_data):
        self._sleep()
        LOG.info("Fetching tickets for %s", case_no)
        response = retry(
            requests.post,
            args=(url, ),
            kwargs={"data": post_data},
            exceptions=(requests.exceptions.ConnectionError, ),
            times=self.options.fetch_retries)
        if response.status_code != 200:
            LOG.warning("Failed to fetch tickets for %s: %s", case_no,
                        response.status_code)
            return None

        page_data = bs4.BeautifulSoup(response.text, self.bs4_parser)
        ticket_table = page_data.find('table', attrs={'border': 1})

        current_person = None
        for row in ticket_table.find_all("tr"):
            if "person cited" in row.text.lower():
                headers = row.find_all("th")
                current_person = self._munge_name(headers[1].string)
                LOG.debug("Found tickets for %s", current_person)
            elif "cited for" in row.text.lower():
                data = row.find_all("td")
                charge = data[3].b.text.strip()
                LOG.debug("Found ticket for %s: %s", current_person, charge)
                db.tickets.append({
                    "case_no": case_no,
                    "initials": current_person,
                    "desc": charge
                })

    def _list_reports_for_date(self, date):
        """Get a list of URLs for reports from a given date."""
        post_data = {
            "CGI": self.options.form_token,
            "rky": '',
            "date": date.strftime("%m-%d-%Y")
        }
        response = retry(
            requests.post,
            args=(self.options.form_url, ),
            kwargs={"data": post_data},
            exceptions=(requests.exceptions.ConnectionError, ),
            times=self.options.fetch_retries)
        if response.status_code != 200:
            raise Exception("Failed to list reports for %s: %s" %
                            (date.isoformat(), response.status_code))
        page_data = bs4.BeautifulSoup(response.text, self.bs4_parser)
        crash_table = page_data.find('table', attrs={'border': 1})

        ticket_url = crash_table.form["action"]
        ticket_token = crash_table.input["value"]

        with db.collisions.delay_write():
            for row in crash_table.find_all('tr'):
                if row.td and row.th and row.th.a:
                    case_no = row.th.a.string.strip()
                    cols = row.find_all("td")
                    record = db.collisions.get(case_no)
                    hit_and_run = "H&R" in cols[3].string
                    if record is None:
                        date = datetime.datetime.strptime(
                            cols[1].string.strip(), "%m-%d-%Y").date()
                        db.collisions.append({
                            "case_no": case_no,
                            "date": date,
                            "hit_and_run": hit_and_run
                        })

                        submit = cols[4].input
                        if submit:
                            ticket_post_data = {
                                "CGI": ticket_token,
                                submit["name"]: submit["value"]
                            }

                            self._parse_tickets(case_no, ticket_url,
                                                ticket_post_data)
                    elif hit_and_run != record.get("hit_and_run"):
                        LOG.info(
                            "Setting hit-and-run status for %s: %s (was %s)",
                            case_no, hit_and_run, record.get("hit_and_run"))
                        record["hit_and_run"] = hit_and_run
                        db.collisions.replace(record)

                    yield row.th.a['href'].strip()

    def _dates_in_range(self):
        """Generate all dates in the desired range, not including
        today."""
        if self.options.end:
            end = self.options.end.date()
        else:
            end = datetime.date.today()

        if self.options.autostart:
            last = max(r["date"] for r in db.collisions if r.get("date"))
            LOG.debug("Last report was fetched from %s", last)
            current = last - datetime.timedelta(2)
        elif self.options.start:
            current = self.options.start.date()
        elif self.options.fetch_start:
            current = datetime.datetime.strptime(self.options.fetch_start,
                                                 "%Y-%m-%d").date()
        else:
            current = end - datetime.timedelta(self.options.fetch_days)
        LOG.debug("Fetching reports starting from %s", current)

        while current <= end:
            yield current

            current += datetime.timedelta(1)

    def _download_report(self, url, force=False):
        """Download the report at the URL to the pdfdir."""
        filename = os.path.split(url)[1]
        filepath = os.path.join(self.options.pdfdir, filename)
        case_no = utils.filename_to_case_no(filename)

        if not force and db.collisions[case_no].get("parsed"):
            LOG.debug("Already parsed %s, skipping", case_no)
        elif os.path.exists(filepath):
            LOG.debug("%s already exists, skipping", filepath)
        else:
            LOG.debug("Downloading %s to %s", url, filepath)
            response = retry(
                requests.get,
                args=(url, ),
                kwargs={"stream": True},
                exceptions=(requests.exceptions.ConnectionError,
                            requests.exceptions.ChunkedEncodingError),
                times=self.options.fetch_retries)
            if response.status_code != 200:
                raise Exception("Failed to download report %s: %s", url,
                                response.status_code)
            with open(filepath, 'wb') as outfile:
                for chunk in response.iter_content():
                    outfile.write(chunk)
            LOG.debug("Wrote data from %s to %s", url, filepath)
            self._sleep()

    def __call__(self):
        if self.options.refetch_curated:
            self._fetch_curated()
        else:
            self._fetch_by_date()

    def _fetch_curated(self):
        reports = [
            c for c in db.collisions if c["road_location"] is not None
            and not c["case_no"].startswith("NDOR")
        ]
        for report in reports:
            filename = utils.case_no_to_filename(report.case_no)
            prefix = filename[0:4]
            url = "%s/%s/%s" % (self.options.fetch_direct_base_url, prefix,
                                filename)
            self._download_report(url, force=True)

    def _fetch_by_date(self):
        for date in self._dates_in_range():
            LOG.info("Fetching reports from %s", date.isoformat())
            for url in self._list_reports_for_date(date):
                self._download_report(url, force=self.options.force)
