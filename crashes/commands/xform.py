"""Produce graphs of collision data."""

import calendar
import collections
import datetime
import functools
import json
import logging
import math
import operator
import os

import astral
import numpy
import pytz

from crashes.commands import base
from crashes import db

LOG = logging.getLogger(__name__)


def _relpath(path):
    prefix = os.path.commonprefix([path, os.getcwd()])
    return os.path.relpath(path, prefix)


@functools.total_ordering
class AgeRange(object):
    # pylint: disable=redefined-builtin
    def __init__(self, min=None, max=None):
        self.min = min or 0
        self.max = max

    # pylint: enable=redefined-builtin

    def contains(self, other):
        if isinstance(other, AgeRange):
            return self.contains(other.min) and self.contains(other.max)
        return ((self.max is None and other >= self.min)
                or (self.min <= other <= self.max))

    def __str__(self):
        if self.max:
            return "%s-%s" % (self.min, self.max)
        else:
            return "%s+" % self.min

    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__, str(self))

    def __eq__(self, other):
        return self.min == other.min and self.max == other.max

    def __gt__(self, other):
        return self.min > other.min and self.max > other.max

    def __lt__(self, other):
        return self.min < other.min and self.max < other.max


def auto_percent_with_abs(total):
    return lambda p: "%d (%0.1f%%)" % (round(total * p / 100), p)


def get_crash_time(report):
    return report.get('time', report.get('accident_time'))


class Xform(base.Command):
    """Produce nicely transformed data for graphs."""

    narrow_age_ranges = [
        AgeRange(max=5),
        AgeRange(6, 10),
        AgeRange(11, 15),
        AgeRange(16, 20),
        AgeRange(21, 25),
        AgeRange(26, 30),
        AgeRange(31, 35),
        AgeRange(36, 40),
        AgeRange(41, 45),
        AgeRange(46, 50),
        AgeRange(51, 55),
        AgeRange(56, 60),
        AgeRange(61, 65),
        AgeRange(66, 70),
        AgeRange(min=70)
    ]

    wide_age_ranges = [
        AgeRange(max=10),
        AgeRange(11, 20),
        AgeRange(21, 30),
        AgeRange(31, 40),
        AgeRange(41, 50),
        AgeRange(51, 60),
        AgeRange(min=61)
    ]

    daylight_phases = ("night", "dawn", "dusk", "day")
    tz = pytz.timezone("US/Central")
    city = astral.Astral()["Lincoln"]

    def __init__(self, options):
        super(Xform, self).__init__(options)
        self._sun_cache = {}
        self._template_data = {}

    @staticmethod
    def _get_age(report):
        """Get the age of the cyclist in years for the given collision.

        Frequently data about the cyclist is not recorded, but they're
        usually the first (and only) injury. There are a few isolated
        reports in which the cyclist is listed as a 'driver,' and I
        suppose it's possible for the cyclist to not be the first
        injured party in a report, so this isn't perfect, but it's
        close enough."""
        if report["date"] and report.get("injury1_dob"):
            if not hasattr(report["injury1_dob"], "day"):
                LOG.warn("Unknown date format in %s: %s", report["case_no"],
                         report["injury1_dob"])
                return None
            diff = report["date"] - report["injury1_dob"]
            return diff.days / 365.25
        else:
            return None

    def _get_age_range(self, report_or_age, ranges):
        try:
            age = int(report_or_age)
        except ValueError:
            age = self._get_age(report_or_age)
        for age_range in ranges:
            if age_range.contains(age):
                return age_range

    def _get_wide_age_range(self, report_or_age):
        return self._get_age_range(report_or_age, self.wide_age_ranges)

    def _get_narrow_age_range(self, report_or_age):
        return self._get_age_range(report_or_age, self.narrow_age_ranges)

    @staticmethod
    def _get_relevant_crashes(unknown=True):
        ignore = [None, "not involved"]
        if not unknown:
            ignore.append("unknown")
        for report in db.collisions:
            if report.get("road_location") not in ignore:
                yield report

    @staticmethod
    def _get_bike_traffic():
        for record in db.traffic:
            if record["type"] == "bike":
                yield record

    def _xform_timings(self):
        """Collect data on crashes per month and year."""
        LOG.info("Creating data for collisions per month and per year")
        collision_counts = collections.defaultdict(int)
        yearly_counts = collections.defaultdict(int)
        monthly_aggregate = collections.defaultdict(int)

        traffic_raw_counts = collections.defaultdict(int)
        traffic_num_readings = collections.defaultdict(int)
        first_traffic_reading = min(
            t["date"] for t in self._get_bike_traffic())
        last_traffic_reading = max(t["date"] for t in self._get_bike_traffic())

        for record in self._get_bike_traffic():
            traffic_raw_counts[record["date"].month] += record["count"]
            traffic_num_readings[record["date"].month] += 1

        relevant = list(self._get_relevant_crashes())
        for report in relevant:
            month = datetime.date(report["date"].year, report["date"].month, 1)
            collision_counts[month] += 1
            yearly_counts[report["date"].year] += 1
            monthly_aggregate[report["date"].month] += 1

        labels = []
        series = []
        month = min(collision_counts.keys())

        while month <= datetime.date.today():
            count = collision_counts.get(month, 0)
            labels.append(month.strftime("%b %Y"))
            series.append(count)
            next_month = month + datetime.timedelta(31)
            month = datetime.date(next_month.year, next_month.month, 1)

        self._save_data("monthly.json", {"labels": labels, "series": [series]})

        average_data = {
            "labels": [],
            "series": [[]],
            "tooltips": [[]],
            "activate_tooltips": [[False] * 12]
        }
        avg_per_month = {}
        min_avg = ()
        max_avg = ()

        cur_year = datetime.date.today().year
        expected = 0
        last = max(c["date"] for c in db.collisions if c.get("date"))

        rate_labels = []
        monthly_rate = []
        monthly_traffic_counts = []
        monthly_collision_rate = []
        lowest_rate = ()
        highest_rate = ()
        for i in range(1, 13):
            today = datetime.date.today()
            month = datetime.date(today.year, i, 1)

            # determine how many years of traffic data from this month
            # we have. We need to figure this out from both ends,
            # since it starts mid-year and ends whenever I last got
            # data from the city.
            traffic_years = (
                last_traffic_reading.year - first_traffic_reading.year - 1)
            if month.month >= first_traffic_reading.month:
                traffic_years += 1
            if month.month <= last_traffic_reading.month:
                traffic_years += 1

            # determine how many years of collision data from this
            # month we have. this is a lot easier because we know that
            # the data starts at the beginning of 2008, so we only
            # need to compare at the tail end; and because we can
            # reasonably expect that the data has been updated
            # recently.
            if month.month <= today.month:
                num_years = math.ceil(self._template_data["report_years"])
            else:
                num_years = math.floor(self._template_data["report_years"])

            # determine how many days this month has so that we know
            # how many traffic readings to expect
            days_in_month = calendar.monthrange(today.year, i)[1]
            readings = days_in_month * 24 * 4
            traffic_count = (traffic_raw_counts[i] * (
                float(readings) / traffic_num_readings[i])) / traffic_years

            # calculate rate data
            month_name = month.strftime("%B")
            rate_labels.append(month_name)
            count = monthly_aggregate[month.month]
            cpm = float(count) / num_years
            monthly_rate.append(cpm)
            monthly_traffic_counts.append(traffic_count)
            cpmrir = cpm / (traffic_count / 1000.0)
            monthly_collision_rate.append(cpmrir)

            if not lowest_rate or cpmrir < lowest_rate[0]:
                lowest_rate = (cpmrir, month)
            if not highest_rate or cpmrir > highest_rate[0]:
                highest_rate = (cpmrir, month)

            # calculate average data
            avg = float(count) / num_years
            avg_per_month[month.month] = avg
            average_data["series"][0].append(avg)
            average_data["tooltips"][0].append(
                "%s: %0.1f average\n%d total\n%0.1f%% of total" %
                (month_name, avg, count, 100 * float(count) / len(relevant)))
            if not min_avg or avg < min_avg[0]:
                min_avg = (avg, month)
            if not max_avg or avg > max_avg[0]:
                max_avg = (avg, month)

            # calculate multiplier for predicting the current year's
            # data. a flat multiplier doesn't work to predict the
            # collision rate for the current year, since different
            # months have wildly different rates of collisions. so
            # first we calculate how many collisions should have
            # happened by this point in the year
            days_in_month = calendar.monthrange(cur_year, i)[1]
            end = datetime.date(cur_year, i, days_in_month)
            if last > end:
                expected += avg_per_month[end.month]
            elif last.month == end.month:
                month_portion = float(last.day) / days_in_month
                expected += avg_per_month[end.month] * month_portion

        min_month = min_avg[1].month - 1
        average_data["activate_tooltips"][0][min_month] = True
        average_data["tooltips"][0][
            min_month] += "\nLeast collisions per month"
        max_month = max_avg[1].month - 1
        average_data["activate_tooltips"][0][max_month] = True
        average_data["tooltips"][0][max_month] += "\nMost collisions per month"
        average_data["labels"] = rate_labels

        self._save_data("monthly_average.json", average_data)
        self._save_data(
            "monthly_rates.json", {
                "labels":
                rate_labels,
                "series": [
                    monthly_rate, [], monthly_traffic_counts, [],
                    monthly_collision_rate
                ]
            })

        self._template_data["mrir_correlation"] = numpy.corrcoef(
            monthly_traffic_counts, monthly_rate)[1][0]
        self._template_data["cpmrir_multiplier"] = (
            highest_rate[0] / lowest_rate[0])
        self._template_data["cpmrir_max_month"] = highest_rate[1].strftime(
            "%B")
        self._template_data["cpmrir_min_month"] = lowest_rate[1].strftime("%B")

        avg_per_year = (float(sum(yearly_counts.values()[0:-1])) /
                        (len(yearly_counts) - 1))
        predicted = (yearly_counts[cur_year] / expected) * avg_per_year
        self._template_data["yearly_mean"] = avg_per_year
        self._template_data["yearly_median"] = (sorted(
            yearly_counts.values())[len(yearly_counts) / 2])

        years = sorted(yearly_counts.keys())
        yearly_data = {
            "labels":
            years,
            "tooltips": [[
                "%s: %d\n%01.f%% of total" %
                (year, yearly_counts[year],
                 100 * float(yearly_counts[year]) / len(relevant))
                for year in years
            ]],
            "series": [[yearly_counts[k] for k in years]]
        }

        # calculate projected data for this year
        projected = [0] * len(years)
        projected[-1] = predicted
        yearly_data["series"].append(projected)
        yearly_data["labels"][
            -1] = "%s (projected)" % (yearly_data["labels"][-1], )
        tooltip = yearly_data["tooltips"][0][-1].splitlines()
        tooltip[0] = "%s (actual)" % (tooltip[0])
        tooltip.insert(1, "%d (projected)" % (projected[-1]))
        yearly_data["tooltips"][0][-1] = "\n".join(tooltip)
        yearly_data["tooltips"].append([None] * (len(years) - 1))
        yearly_data["tooltips"][1].append("\n".join(tooltip))

        self._save_data("yearly.json", yearly_data)

    def _xform_ages(self):
        """Collate two age-related datasets.

        * Collision location by age
        * A histogram of total number of collisions by age
        """
        LOG.info("Collecting data on ages of cyclists "
                 "and collision locations by age")

        loc_by_age = {}
        total_by_age = collections.defaultdict(int)
        for report in self._get_relevant_crashes():
            location = report["road_location"].title()
            age = self._get_age(report)
            if age:
                age_range = self._get_narrow_age_range(age)
                if location not in loc_by_age:
                    loc_by_age[location] = {
                        r: 0
                        for r in self.narrow_age_ranges
                    }
                loc_by_age[location][age_range] += 1
                total_by_age[age_range] += 1

                # record some template data while we're at it
                if age < 20:
                    self._template_data['num_children'] += 1
                    if age < 11:
                        self._template_data['under_11'] += 1

        labels = [str(a) for a in self.narrow_age_ranges]
        series = []
        for loc, loc_collisions in loc_by_age.items():
            loc_series = []
            loc_tooltips = []
            for age_range in self.narrow_age_ranges:
                collisions = loc_collisions.get(age_range, 0)
                if collisions:
                    # the values are absolute numbers of collisions;
                    # we want the Y axis to be the proportion of
                    # collisions by people that age, not number. in
                    # order to stack the lines, we need to add the
                    # previous number to it.
                    abs_proportion = (
                        collisions / float(total_by_age[age_range]) * 100)
                else:
                    abs_proportion = 0
                proportion = abs_proportion
                if series:
                    proportion += series[-1][len(loc_series)]
                loc_series.append(proportion)
                loc_tooltips.append("%s: %0.1f%%\n%d collisions" %
                                    (loc, abs_proportion, collisions))
            series.append(loc_series)
        # reverse the data so that the smallest data are on the "top"
        # of the stack when rendered by Chartist.js. This lets us set
        # the fill-opacity to 1 and it looks stacked, rather than
        # having the big (100%) line blot everything else out.
        series.reverse()
        self._save_data("location_by_age.json", {
            "labels": labels,
            "series": series
        })

        ages_data = {"labels": [], "series": [[]], "tooltips": [[]]}
        total = sum(total_by_age.values())
        for age_range in self.narrow_age_ranges:
            ages_data["labels"].append(str(age_range))
            ages_data["series"][0].append(total_by_age[age_range])
            ages_data["tooltips"][0].append(
                "%s: %d collisions\n%0.1f%% of total" %
                (age_range, total_by_age[age_range],
                 100 * float(total_by_age[age_range]) / total))

        self._save_data("ages.json", ages_data)

    def _xform_collision_times(self):
        """Collect data for collision time of day and rates per hour."""
        LOG.info("Collecting data on collision times")

        traffic_raw_counts = [0] * 24
        traffic_num_readings = [0] * 24
        for record in self._get_bike_traffic():
            traffic_raw_counts[record["start"].hour] += record["count"]
            traffic_num_readings[record["start"].hour] += 1

        times = [0] * 24
        for report in self._get_relevant_crashes():
            crash_time = get_crash_time(report)
            if crash_time is None:
                continue
            times[crash_time.hour] += 1 / self._template_data['report_years']

        rates = []
        labels = []
        traffic_counts = [0] * 24
        for i in range(24):
            end = i + 1 if i < 23 else 0
            labels.append("%d:00 - %d:00" % (i, end))
            traffic_counts[
                i] = traffic_raw_counts[i] / (traffic_num_readings[i] / 4.0)
            rates.append(float(times[i]) / traffic_counts[i])

        self._save_data("hourly.json", {
            "labels": labels,
            "series": [times, [], traffic_counts, [], rates]
        })

        self._template_data["hrir_correlation"] = numpy.corrcoef(
            times, traffic_counts)[1][0]

    def _xform_injury_severities_by_location(self):
        """Collect data on injury rates by collision location."""
        LOG.info("Collecting data on injury severity")

        injuries = collections.defaultdict(
            lambda: collections.defaultdict(int))
        injuries_by_loc = collections.defaultdict(int)
        injuries_by_sev = collections.defaultdict(int)
        cases_by_loc = collections.defaultdict(int)
        for report in self._get_relevant_crashes(unknown=False):
            loc = report["road_location"].title()
            sev = report.get("injury_severity", 5)
            if sev != 5:
                self._template_data['injured_count'] += 1
            injuries_by_sev[sev] += 1
            injuries_by_loc[loc] += 1
            cases_by_loc[loc] += 1
            injuries[loc][sev] += 1

        rates_by_loc = {}
        for loc, cases in cases_by_loc.items():
            rates_by_loc[loc] = float(injuries_by_loc[loc]) / cases

        labels = []
        series = [[] for i in range(1, 5)]
        tooltips = [[] for i in range(1, 5)]
        for loc, _ in reversed(
                sorted(rates_by_loc.items(), key=operator.itemgetter(1))):
            labels.append(loc)
            for i in range(1, 5):
                sev_name = db.injury_severity[i]["desc"]
                count = injuries[loc][i]
                sev_rate = 100 * float(count) / cases_by_loc[loc]
                series[i - 1].append(sev_rate)
                tooltips[i - 1].append(
                    "Rate of %s on %s: %0.1f%%\nCount: %d\n%0.1f%% of %s\n"
                    "%0.1f%% of %s\n" %
                    (sev_name, loc, sev_rate, count,
                     100 * float(count) / injuries_by_sev[i], sev_name,
                     100 * float(count) / injuries_by_loc[loc], loc))

        self._save_data("injury_rates.json", {
            "labels": labels,
            "series": series,
            "tooltips": tooltips
        })

    def _xform_injury_severities(self):
        """Munge data for pie chart of the relative rates of injury severities
        """
        LOG.info("Transforming injury severity data")

        severities = collections.defaultdict(int)
        for report in self._get_relevant_crashes():
            if report.get("injury_severity"):
                description = db.injury_severity[report["injury_severity"]][
                    "desc"]
                severities[description] += 1

        total = sum(severities.values())
        data = {"labels": [], "series": []}
        for key, val in severities.items():
            data["labels"].append(
                "%s: %d (%0.1f%%)" % (key, val, float(val) / total * 100))
            data["series"].append(val)
        self._save_data("injury_severities.json", data)

    def _xform_injury_regions(self):
        """Data for rates of injury by primary injury region."""
        LOG.info("Transforming data for injury regions")

        regions = collections.defaultdict(int)
        for report in self._get_relevant_crashes():
            if report["case_no"].startswith("NDOR"):
                continue
            sev = report.get("injury_severity", 5)
            if report.get("injury_region"):
                regions[db.injury_region[report["injury_region"]]["desc"]] += 1
            elif sev != 5:
                # injury reported, but no injury region
                regions['Unknown'] += 1

        data = {"labels": [], "series": []}
        total = sum(regions.values())
        other = 0
        for region, count in reversed(
                sorted(regions.items(), key=operator.itemgetter(1))):
            if region == "Unknown" or float(count) / total < 0.04:
                other += count
            else:
                data["labels"].append(
                    "%s: %d (%0.1f%%)" % (region, count,
                                          float(count) / total * 100))
                data["series"].append(count)
        if other:
            data["labels"].append("Other/Unknown: %d (%0.1f%%)" %
                                  (other, float(other) / total * 100))
            data["series"].append(other)

        self._save_data("injury_regions.json", data)

    def _xform_proportions(self):
        """Create data for pie chart of collisions by location."""
        LOG.info("Transforming data on proportions of collision locations")

        statuses = collections.defaultdict(int)
        for report in self._get_relevant_crashes(unknown=False):
            statuses[report["road_location"]] += 1

        total = sum(statuses.values())
        data = {"labels": [], "series": []}
        for name, num_cases in reversed(
                sorted(statuses.items(), key=operator.itemgetter(1))):
            data["labels"].append(
                "%s: %d (%0.1f%%)" % (name.title(), num_cases,
                                      float(num_cases) / total * 100))
            data["series"].append(num_cases)
        self._save_data("proportions.json", data)

    def _xform_genders(self):
        """Create data for pie chart of collisions by gender."""
        LOG.info("Transforming data on collisions by gender")

        by_gender = collections.Counter(r["gender"]
                                        for r in self._get_relevant_crashes()
                                        if r.get("gender") is not None)
        total = sum(by_gender.values())

        data = {"labels": [], "series": []}

        def _record(label, count):
            data["labels"].append(
                "%s: %s (%0.1f%%)" % (label, count, 100.0 * count / total))
            data["series"].append(count)

        _record("Male", by_gender["M"])
        _record("Female", by_gender["F"])

        self._save_data("by_gender.json", data)

    def _xform_hit_and_runs(self):
        """Create data for pie chart of hit-and-runs."""
        LOG.info("Transforming data on hit-and-runs")

        hit_and_runs = collections.defaultdict(int)
        for report in db.collisions:
            if report.get("hit_and_run_status") is not None:
                hit_and_runs[report["hit_and_run_status"]] += 1

        total_hnrs = sum(hit_and_runs.values())

        data = {"labels": [], "series": []}
        data["series"].append(hit_and_runs["driver"])
        data["labels"].append("Driver only left scene: %s (%0.1f%%)" %
                              (hit_and_runs["driver"],
                               100.0 * hit_and_runs["driver"] / total_hnrs))

        data["series"].append(hit_and_runs["cyclist"])
        data["labels"].append("Cyclist only left scene: %s (%0.1f%%)" %
                              (hit_and_runs["cyclist"],
                               100.0 * hit_and_runs["cyclist"] / total_hnrs))

        num_both = hit_and_runs["both"] + hit_and_runs["unknown"]
        data["series"].append(num_both)
        data["labels"].append(
            "Both parties left scene or unclear: %s (%0.1f%%)" %
            (num_both, 100.0 * num_both / total_hnrs))

        self._save_data("hit_and_runs.json", data)

        self._template_data['hit_and_run_counts'] = hit_and_runs
        self._template_data['hit_and_run_total'] = total_hnrs

    def sun_phases(self, date):
        if date not in self._sun_cache:
            self._sun_cache[date] = self.city.sun(date=date, local=True)
        return self._sun_cache[date]

    def _get_daylight_phase(self, when):
        sun = self.sun_phases(when)
        if when < sun["dawn"] or when > sun["dusk"]:
            return "night"
        elif when < sun["sunrise"]:
            return "dawn"
        elif when > sun["sunset"]:
            return "dusk"
        else:
            return "day"

    def _get_phase_duration(self, date):
        sun = self.sun_phases(date)
        return {
            "dawn": sun["sunrise"] - sun["dawn"],
            "day": sun["sunset"] - sun["sunrise"],
            "dusk": sun["dusk"] - sun["sunset"],
            "night": (sun["dawn"] + datetime.timedelta(1)) - sun["dusk"]
        }

    def _xform_daylight(self):
        """Create graphs for daylight/nighttime collision data."""

        by_month = {}

        for report in self._get_relevant_crashes():
            report_time = get_crash_time(report)
            if report["date"] and report_time:
                crashtime = datetime.datetime(
                    report["date"].year, report["date"].month,
                    report["date"].month, report_time.hour, report_time.minute,
                    report_time.second).replace(tzinfo=self.tz)
            else:
                continue

            if crashtime.month not in by_month:
                by_month[crashtime.month] = collections.defaultdict(int)

            by_month[crashtime.month][self._get_daylight_phase(crashtime)] += 1

        totals = collections.defaultdict(int)
        for data in by_month.values():
            for phase, count in data.items():
                totals[phase] += count
        total = sum(totals.values())

        pie_data = {"labels": [], "series": [], "tooltips": []}
        line_data = {
            "labels":
            [datetime.date(2017, m, 1).strftime("%B") for m in range(1, 13)],
            "series": []
        }
        for phase in self.daylight_phases:
            pie_data["labels"].append(
                "%s: %d" % (phase.title(), totals[phase]))
            pie_data["series"].append(totals[phase])
            pie_data["tooltips"].append(
                "%0.1f%% of total" % (100 * float(totals[phase]) / total))

            line_data["series"].append([[] for m in range(12)])
            for month in range(12):
                month_total = sum(by_month[month + 1].values())
                line_data["series"][-1][month] = 100 * float(
                    by_month[month + 1].get(phase, 0)) / month_total

        line_data["series"].append([(100 * operator.sub(*reversed(
            self.city.daylight(date=datetime.date(2017, m, 1)))).seconds / 60.0
                                     / 60 / 24) for m in range(1, 13)])
        self._save_data("daylight_totals.json", pie_data)
        self._save_data("daylight_by_month.json", line_data)

        self._template_data["daylight_correlation"] = numpy.corrcoef(
            line_data["series"][-1], line_data["series"][-2])[1][0]

        traffic_by_phase = collections.defaultdict(float)
        phase_duration = collections.defaultdict(int)
        for record in self._get_bike_traffic():
            time = datetime.datetime(
                year=record["date"].year,
                month=record["date"].month,
                day=record["date"].day,
                hour=record["start"].hour,
                minute=record["start"].minute,
                second=record["start"].second,
                tzinfo=self.tz)
            phase = self._get_daylight_phase(time)
            traffic_by_phase[phase] += record["count"]
            # this is technically not quite accurate, but since we
            # have traffic readings in 15-minute chunks we assign each
            # chunk to a single day phase. So even if the sun sets
            # during a 15-minute chunk, we consider that chunk 'dusk'
            phase_duration[phase] += 15 * 60

        traffic_rates = {}
        collision_rates = {}
        for phase, traffic in traffic_by_phase.items():
            traffic_rates[
                phase] = (float(traffic) / phase_duration[phase]) * 60 * 60
            collision_rates[phase] = (
                float(totals[phase]) / traffic_rates[phase])
            self._template_data["%s_collision_rate" % phase] = (
                collision_rates[phase])

        rate_data = {"labels": [], "series": [[]], "tooltips": [[]]}
        for phase, rate in sorted(
                collision_rates.items(), key=operator.itemgetter(1)):
            rate_data["labels"].append(phase.title())
            rate_data["series"][0].append(rate)
            rate_data["tooltips"][0].append(
                "%0.2f collisions per HRIR\n%s total collisions\n%0.2f HRIR" %
                (rate, totals[phase], traffic_rates[phase]))

        self._save_data("daylight_rates.json", rate_data)

    def _pre_xform_template_data(self):
        """Create template data for rendering index.html."""
        # yapf: disable
        self._template_data.update({
            "now": datetime.datetime.now().strftime("%Y-%m-%d %H:%M %Z"),
            "report_count": len(db.collisions),
            "num_children": 0,
            "under_11": 0,
            "injured_count": 0,
            "imagedir": _relpath(self.options.imagedir),
            "db_dump": _relpath(self.options.dumpdir),
            "unparseable_count": 0,
            "ndor_count": 0
        })
        # yapf: enable
        first_report = None
        last_report = None
        post_2011_reports = 0
        bike_report_count = 0
        for report in db.collisions:
            if report["date"] is None:
                self._template_data['unparseable_count'] += 1
                continue
            if first_report is None or report["date"] < first_report:
                first_report = report["date"]
            if last_report is None or report["date"] > last_report:
                last_report = report["date"]
            if report["case_no"].startswith("NDOR"):
                self._template_data['ndor_count'] += 1
            if report["date"].year > 2011:
                post_2011_reports += 1
                if report.get("road_location") not in (None, "not involved"):
                    bike_report_count += 1

        self._template_data["first_report"] = first_report.strftime(
            "%B %e, %Y")
        self._template_data["last_report"] = last_report.strftime("%B %e, %Y")
        self._template_data["bike_reports"] = bike_report_count
        self._template_data["post_2011_reports"] = post_2011_reports

        self._template_data["bike_pct"] = (
            100.0 * self._template_data["bike_reports"] /
            self._template_data["post_2011_reports"])

        status_counts = collections.defaultdict(int)
        for report in db.collisions:
            if report.get("road_location") not in (None, "not involved",
                                                   "unknown"):
                status_counts[report["road_location"]] += 1

        self._template_data['statuses'] = dict(status_counts)
        self._template_data['total_road'] = (
            status_counts['road'] + status_counts['intersection'])
        self._template_data['total_sidewalk'] = (
            status_counts['sidewalk'] + status_counts['crosswalk'])
        self._template_data['total_bike_infra'] = (
            status_counts.get('bike trail', 0) + status_counts.get(
                'bike trail crossing', 0) + status_counts['bike lane'])

        report_time_period = datetime.date.today() - first_report
        self._template_data['report_years'] = report_time_period.days / 365.25

        self._template_data["status_descriptions"] = sorted(
            [(name.title(), loc["desc"]) for name, loc in db.location.items()
             if name != "not involved"],
            key=operator.itemgetter(0))

    def _post_xform_template_data(self):
        self._template_data['pct_children'] = (
            float(self._template_data['num_children'] * 100) /
            self._template_data['bike_reports'])

        full_data_time_period = (
            datetime.date.today() - datetime.date(2012, 1, 1))
        full_data_years = full_data_time_period.days / 365.25

        self._template_data['under_11_per_year'] = (
            self._template_data['under_11'] / full_data_years)

    def _save_data(self, filename, data):
        """Save JSON to the given filename."""
        path = os.path.join(self.options.graph_data, filename)
        LOG.info("Writing graph data to %s", path)
        json.dump(data, open(path, "w"))

    def __call__(self):
        self._pre_xform_template_data()

        self._xform_proportions()
        self._xform_injury_severities()
        self._xform_injury_severities_by_location()
        self._xform_injury_regions()
        self._xform_timings()
        self._xform_collision_times()
        self._xform_ages()
        self._xform_genders()
        self._xform_hit_and_runs()
        self._xform_daylight()

        self._post_xform_template_data()

        tmpl_path = os.path.join(self.options.datadir, "template_data.json")
        LOG.info("Writing template data to %s", tmpl_path)
        json.dump(self._template_data, open(tmpl_path, "w"))
