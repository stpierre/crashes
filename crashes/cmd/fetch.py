"""Command to download reports from LPD."""

import datetime
import glob
import logging
import os
import random
import time

from time import sleep

import bs4
import requests

from crashes.cmd import base

LOG = logging.getLogger(__name__)


def retry(func, args=(), kwargs=None, exceptions=None, times=1, wait=3):
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
                LOG.error("Retried %s %s times, failed: %s" %
                          (func, tries, err))
                raise
            else:
                LOG.info("%s failed, retrying (%s/%s): %s" %
                         (func, tries, times, err))
            time.sleep(wait)


class Fetch(base.Command):
    """Download reports from LPD."""

    arguments = [
        base.Argument("--start",
                      type=lambda d: datetime.datetime.strptime(d, "%Y-%m-%d"))
    ]

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
        page_data = bs4.BeautifulSoup(response.text)
        crash_table = page_data.find('table', attrs={'width': 800})
        for row in crash_table.find_all('tr'):
            if row.td and row.td.a:
                yield row.td.a['href'].strip()

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

        while current < end:
            yield current

            current += datetime.timedelta(1)

    def _download_report(self, url):
        """Download the report at the URL to the pdfdir."""
        filename = os.path.split(url)[1]
        filepath = os.path.join(self.options.pdfdir, filename)
        LOG.debug("Downloading %s to %s" % (url, filepath))
        if os.path.exists(filepath):
            LOG.debug("%s already exists, skipping" % filepath)
        else:
            response = retry(requests.get, args=(url,),
                             kwargs={"stream": True},
                             exceptions=(requests.exceptions.ConnectionError,),
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
        for date in self._dates_in_range():
            time.sleep(random.randint(self.options.sleep_min,
                                      self.options.sleep_max))
            LOG.info("Fetching reports from %s" % date.isoformat())
            for url in self._list_reports_for_date(date):
                self._download_report(url)

    def satisfied(self):
        # consider it success if any reports have ever been downloaded
        return len(glob.glob(os.path.join(self.options.pdfdir, "*"))) > 0
