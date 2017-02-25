"""Command to download reports from LPD."""

import datetime
import glob
import json
import logging
import operator
import os
import random
import time

import bs4
import requests

from crashes.commands import base

LOG = logging.getLogger(__name__)


def retry(func, args=(), kwargs=None, exceptions=None, times=1, wait=5):
    tries = 0
    if kwargs is None:
        kwargs = {}
    if exceptions is None:
        exceptions = (Exception,)
    while tries < times:
        tries += 1
        try:
            return func(*args, **kwargs)
        except exceptions as err:
            if tries == times:
                LOG.error("Retried %s %s times, failed: %s",
                          func, tries, err)
                raise
            else:
                LOG.info(
                    "%s failed, waiting %s seconds and retrying (%s/%s): %s",
                    func, wait, tries, times, err)
            time.sleep(wait)


class Fetch(base.Command):
    """Download reports from LPD."""

    arguments = [
        base.Argument("--start",
                      type=lambda d: datetime.datetime.strptime(d, "%Y-%m-%d")),
        base.Argument("--refetch-curated", action="store_true")
    ]

    def __init__(self, options):
        super(Fetch, self).__init__(options)
        self._metadata = {}
        if os.path.exists(self.options.metadata):
            self._metadata = json.load(open(self.options.metadata))
        self.report_data = json.load(open(self.options.all_reports))

    @staticmethod
    def _munge_name(name):
        """Anonymize a name so that it can be compared but not read.

        Even though all of this is public data, I don't want to be
        "leaking" it myself. So we munge names to include just
        initials, which should be enough to uniquely identify the
        people in a collision without storing their names.
        """
        parts = name.split(" (dob) ")
        return " ".join([
            "".join(w[0] for w in parts[0].split()),
            parts[1]])

    def _parse_tickets(self, case_no, url, post_data):
        time.sleep(random.randint(self.options.sleep_min,
                                  self.options.sleep_max))
        LOG.info("Fetching tickets for %s", case_no)
        response = retry(requests.post, args=(url,),
                         kwargs={"data": post_data},
                         exceptions=(requests.exceptions.ConnectionError,),
                         times=self.options.fetch_retries)
        if response.status_code != 200:
            LOG.warning("Failed to fetch tickets for %s: %s" %
                        (case_no, response.status_code))
            return None

        page_data = bs4.BeautifulSoup(response.text, "html.parser")
        ticket_table = page_data.find('table', attrs={'width': 800})

        tickets = {}
        current_person = None
        for row in ticket_table.find_all("tr"):
            if "person cited" in row.text.lower():
                headers = row.find_all("th")
                current_person = self._munge_name(headers[1].string)
                LOG.debug("Found tickets for %s" % current_person)
                tickets[current_person] = []
            elif "cited for" in row.text.lower():
                data = row.find_all("td")
                charge = data[3].b.text.strip()
                LOG.debug("Found ticket for %s: %s" % (current_person,
                                                       charge))
                tickets[current_person].append(charge)
        return tickets

    def _list_reports_for_date(self, date):
        """Get a list of URLs for reports from a given date."""
        post_data = {"CGI": self.options.form_token,
                     "rky": '',
                     "date": date.strftime("%m-%d-%Y")}
        response = retry(requests.post, args=(self.options.form_url,),
                         kwargs={"data": post_data},
                         exceptions=(requests.exceptions.ConnectionError,),
                         times=self.options.fetch_retries)
        if response.status_code != 200:
            raise Exception("Failed to list reports for %s: %s" %
                            (date.isoformat(), response.status_code))
        page_data = bs4.BeautifulSoup(response.text, "html.parser")
        crash_table = page_data.find('table', attrs={'width': 800})

        ticket_url = crash_table.tbody.form["action"]
        ticket_token = crash_table.tbody.input["value"]

        for row in crash_table.find_all('tr'):
            if row.td and row.td.a:
                cols = row.find_all("td")
                case_no = cols[0].a.string.strip()
                if case_no not in self._metadata:
                    self._metadata[case_no] = {
                        "date": datetime.datetime.strptime(
                            cols[2].string.strip(),
                            "%m-%d-%Y").strftime("%Y-%m-%d"),
                        "hit_and_run": "H&R" in cols[4].string
                    }
                    submit = cols[5].input
                    if submit:
                        ticket_post_data = {
                            "CGI": ticket_token,
                            submit["name"]: submit["value"]}
                        self._metadata[case_no]["tickets"] = (
                            self._parse_tickets(case_no, ticket_url,
                                                ticket_post_data))

                yield cols[0].a['href'].strip()

    def _dates_in_range(self):
        """Generate all dates in the desired range, not including today."""
        end = datetime.date.today()
        if self.options.start:
            current = self.options.start.date()
        elif self.options.fetch_start:
            current = datetime.datetime.strptime(self.options.fetch_start,
                                                 "%Y-%m-%d").date()
        else:
            current = end - datetime.timedelta(self.options.fetch_days)

        while current <= end:
            yield current

            current += datetime.timedelta(1)

    def _download_report(self, url, force=False):
        """Download the report at the URL to the pdfdir."""
        filename = os.path.split(url)[1]
        filepath = os.path.join(self.options.pdfdir, filename)
        case_no = "-".join((filename[0:2], filename[2:8]))
        if not force and case_no in self.report_data:
            LOG.debug("Already parsed %s, skipping" % case_no)
        else:
            LOG.debug("Downloading %s to %s" % (url, filepath))
            if os.path.exists(filepath):
                LOG.debug("%s already exists, skipping" % filepath)
            else:
                response = retry(
                    requests.get, args=(url,),
                    kwargs={"stream": True},
                    exceptions=(requests.exceptions.ConnectionError,
                                requests.exceptions.ChunkedEncodingError),
                    times=self.options.fetch_retries)
                if response.status_code != 200:
                    raise Exception("Failed to download report %s: %s" %
                                    (url, response.status_code))
                with open(filepath, 'wb') as outfile:
                    for chunk in response.iter_content():
                        outfile.write(chunk)
                LOG.debug("Wrote data from %s to %s" % (url, filepath))
                time.sleep(random.randint(self.options.sleep_min,
                                          self.options.sleep_max))

    def __call__(self):
        if self.options.refetch_curated:
            self._fetch_curated()
        else:
            self._fetch_by_date()

    def _fetch_curated(self):
        curation = json.load(open(self.options.curation_results))
        for case_no in reduce(operator.add, curation.values()):
            if case_no.startswith("NDOR"):
                continue
            filename = self.report_data[case_no]["filename"]
            prefix = filename[0:4]
            url = "%s/%s/%s" % (self.options.fetch_direct_base_url,
                              prefix, filename)
            self._download_report(url, force=True)

    def _fetch_by_date(self):
        for date in self._dates_in_range():
            time.sleep(random.randint(self.options.sleep_min,
                                      self.options.sleep_max))
            LOG.info("Fetching reports from %s" % date.isoformat())
            for url in self._list_reports_for_date(date):
                self._download_report(url)
                json.dump(self._metadata, open(self.options.metadata, 'w'))

    def satisfied(self):
        # consider it success if any reports have ever been downloaded
        return len(glob.glob(os.path.join(self.options.pdfdir, "*"))) > 0
