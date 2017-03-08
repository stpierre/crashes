"""Produce graphs of collision data."""

import calendar
import collections
import datetime
import functools
import json
import math
import operator
import os

import astral
import numpy
import pytz

from crashes.commands import base
from crashes.commands import curate
from crashes import log

LOG = log.getLogger(__name__)


def _relpath(path):
    prefix = os.path.commonprefix([path, os.getcwd()])
    return os.path.relpath(path, prefix)


@functools.total_ordering
class AgeRange(object):
    def __init__(self, min=None, max=None):
        self._min = min or 0
        self._max = max

    def contains(self, other):
        if isinstance(other, AgeRange):
            return self.contains(other._min) and self.contains(other._max)
        return ((self._max is None and other >= self._min) or
                (self._min <= other <= self._max))

    def __str__(self):
        if self._max:
            return "%s-%s" % (self._min, self._max)
        else:
            return "%s+" % self._min

    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__, str(self))

    def __eq__(self, other):
        return self._min == other._min and self._max == other._max

    def __gt__(self, other):
        return self._min > other._min and self._max > other._max

    def __lt__(self, other):
        return self._min < other._min and self._max < other._max


def auto_percent_with_abs(total):
    return lambda p: "%d (%0.1f%%)" % (round(total * p / 100), p)


class Xform(base.Command):
    """Produce nicely transformed data for graphs."""

    prerequisites = [curate.Curate]

    injury_severities = {
        1: "Killed",
        2: "Disabling",
        3: "Visible but not disabling",
        4: "Possible but not visible",
        5: "Uninjured"}

    narrow_age_ranges = [AgeRange(max=5),
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
                         AgeRange(min=70)]

    wide_age_ranges = [AgeRange(max=10),
                       AgeRange(11, 20),
                       AgeRange(21, 30),
                       AgeRange(31, 40),
                       AgeRange(41, 50),
                       AgeRange(51, 60),
                       AgeRange(min=61)]

    daylight_phases = ("night", "dawn", "dusk", "day")
    tz = pytz.timezone("US/Central")
    city = astral.Astral()["Lincoln"]

    def __init__(self, options):
        super(Xform, self).__init__(options)
        self._sun_cache = {}
        self._reports = json.load(open(self.options.all_reports))
        self._curation = json.load(open(self.options.curation_results))
        self._traffic_counts = json.load(open(self.options.traffic_counts))
        del self._curation['not_involved']
        self._template_data = {
            "now": datetime.datetime.now().strftime("%Y-%m-%d %H:%M %Z"),
            "report_count": len(self._reports),
            "num_children": 0,
            "under_11": 0,
            "injured_count": 0,
            "imagedir": _relpath(self.options.imagedir),
            "all_reports": _relpath(self.options.all_reports)}

    def _get_age(self, case_no):
        """Get the age of the cyclist in years for the given collision."""
        try:
            dob = datetime.datetime.strptime(
                self._reports[case_no]['cyclist_dob'], "%Y-%m-%d")
            date = datetime.datetime.strptime(
                self._reports[case_no]['date'], "%Y-%m-%d")
        except TypeError:
            return None

        diff = date - dob
        return diff.days / 365.25

    def _get_age_range(self, case_no_or_age, ranges):
        try:
            age = int(case_no_or_age)
        except ValueError:
            age = self._get_age(case_no_or_age)
        for age_range in ranges:
            if age_range.contains(age):
                return age_range

    def _get_wide_age_range(self, case_no_or_age):
        return self._get_age_range(case_no_or_age, self.wide_age_ranges)

    def _get_narrow_age_range(self, case_no_or_age):
        return self._get_age_range(case_no_or_age, self.narrow_age_ranges)

    def _xform_timings(self):
        """Collect data on crashes per month and year."""
        LOG.info("Creating data for collisions per month and per year")
        collision_counts = collections.defaultdict(int)
        yearly_counts = collections.defaultdict(int)
        monthly_aggregate = collections.defaultdict(int)

        traffic_raw_counts = collections.defaultdict(int)
        traffic_num_readings = collections.defaultdict(int)
        first_traffic_reading = None
        last_traffic_reading = None
        for record in self._traffic_counts:
            date = datetime.datetime.strptime(record['date'], "%Y-%m-%d")
            traffic_raw_counts[date.month] += (record["northbound"] +
                                               record["southbound"])
            traffic_num_readings[date.month] += 1

            if first_traffic_reading is None or date < first_traffic_reading:
                first_traffic_reading = date
            if last_traffic_reading is None or date > last_traffic_reading:
                last_traffic_reading = date

        relevant = reduce(operator.add, self._curation.values())
        for case_no in relevant:
            date_str = self._reports[case_no]['date']
            date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            month = datetime.date(date.year, date.month, 1)
            collision_counts[month] += 1
            yearly_counts[date.year] += 1
            monthly_aggregate[date.month] += 1

        labels = []
        series = []
        month = min(collision_counts.keys())

        while month <= datetime.date.today():
            count = collision_counts.get(month, 0)
            labels.append(month.strftime("%b %Y"))
            series.append(count)
            next_month = month + datetime.timedelta(31)
            month = datetime.date(next_month.year, next_month.month, 1)

        self._save_data("monthly.json", {"labels": labels,
                                         "series": [series]})

        average_data = {"labels": [], "series": [[]], "tooltips": [[]],
                        "activate_tooltips": [[False] * 12]}
        avg_per_month = {}
        min_avg = None
        max_avg = None

        cur_year = datetime.date.today().year
        expected = 0
        last = max(datetime.datetime.strptime(r["date"], "%Y-%m-%d")
                   for r in self._reports.values() if r["date"]).date()

        rate_labels = []
        monthly_rate = []
        monthly_traffic_counts = []
        monthly_collision_rate = []
        lowest_rate = None
        highest_rate = None
        for i in range(1, 13):
            today = datetime.date.today()
            month = datetime.date(today.year, i, 1)

            # determine how many years of traffic data from this month
            # we have. We need to figure this out from both ends,
            # since it starts mid-year and ends whenever I last got
            # data from the city.
            traffic_years = (last_traffic_reading.year -
                             first_traffic_reading.year - 1)
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

            if lowest_rate is None or cpmrir < lowest_rate[0]:
                lowest_rate = (cpmrir, month)
            if highest_rate is None or cpmrir > highest_rate[0]:
                highest_rate = (cpmrir, month)

            # calculate average data
            avg = float(count) / num_years
            avg_per_month[month.month] = avg
            average_data["series"][0].append(avg)
            average_data["tooltips"][0].append(
                "%s: %0.1f average\n%d total\n%0.1f%% of total" % (
                    month_name, avg, count, 100 * float(count) / len(relevant)))
            if min_avg is None or avg < min_avg[0]:
                min_avg = (avg, month)
            if max_avg is None or avg > max_avg[0]:
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

        average_data["activate_tooltips"][0][min_avg[1].month - 1] = True
        average_data["tooltips"][0][min_avg[1].month - 1] += (
            "\nLeast collisions per month")
        average_data["activate_tooltips"][0][max_avg[1].month - 1] = True
        average_data["tooltips"][0][max_avg[1].month - 1] += (
            "\nMost collisions per month")
        average_data["labels"] = rate_labels

        self._save_data("monthly_average.json", average_data)
        self._save_data("monthly_rates.json",
                        {"labels": rate_labels,
                         "series": [monthly_rate, [],
                                    monthly_traffic_counts, [],
                                    monthly_collision_rate]})

        self._template_data["mrir_correlation"] = numpy.corrcoef(
            monthly_traffic_counts, monthly_rate)[1][0]
        self._template_data["cpmrir_multiplier"] = (
            highest_rate[0] / lowest_rate[0])
        self._template_data["cpmrir_max_month"] = highest_rate[1].strftime("%B")
        self._template_data["cpmrir_min_month"] = lowest_rate[1].strftime("%B")

        avg_per_year = (float(sum(yearly_counts.values()[0:-1])) /
                        (len(yearly_counts) - 1))
        predicted = (yearly_counts[cur_year] / expected) * avg_per_year
        self._template_data["yearly_mean"] = avg_per_year
        self._template_data["yearly_median"] = (
            sorted(yearly_counts.values())[len(yearly_counts) / 2])

        years = sorted(yearly_counts.keys())
        yearly_data = {
            "labels": years,
            "tooltips": [[
                "%s: %d\n%01.f%% of total" % (
                    year, yearly_counts[year],
                    100 * float(yearly_counts[year]) / len(relevant))
                for year in years]],
            "series": [[yearly_counts[k] for k in years]]}

        # calculate projected data for this year
        projected = [0] * len(years)
        projected[-1] = predicted
        yearly_data["series"].append(projected)
        yearly_data["labels"][-1] = "%s (projected)" % (
            yearly_data["labels"][-1],)
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
        for name, cases in self._curation.items():
            location = self.title(name)
            for case_no in cases:
                age = self._get_age(case_no)
                if age:
                    age_range = self._get_narrow_age_range(age)
                    if location not in loc_by_age:
                        loc_by_age[location] = {
                            r: 0 for r in self.narrow_age_ranges}
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
                    abs_proportion = (collisions /
                                      float(total_by_age[age_range]) * 100)
                else:
                    abs_proportion = 0
                proportion = abs_proportion
                if len(series):
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
        self._save_data(
            "location_by_age.json",
            {"labels": labels,
             "series": series})

        ages_data = {"labels": [], "series": [[]], "tooltips": [[]]}
        total = sum(total_by_age.values())
        for age_range in self.narrow_age_ranges:
            ages_data["labels"].append(str(age_range))
            ages_data["series"][0].append(total_by_age[age_range])
            ages_data["tooltips"][0].append(
                "%s: %d collisions\n%0.1f%% of total" % (
                    age_range, total_by_age[age_range],
                    100 * float(total_by_age[age_range]) / total))

        self._save_data("ages.json", ages_data)

    def _xform_collision_times(self):
        """Collect data for collision time of day and rates per hour."""
        LOG.info("Collecting data on collision times")

        traffic_raw_counts = [0] * 24
        traffic_num_readings = [0] * 24
        for record in self._traffic_counts:
            time = datetime.datetime.strptime(record['time'], "%H:%M")
            traffic_raw_counts[time.hour] += (record["northbound"] +
                                              record["southbound"])
            traffic_num_readings[time.hour] += 1

        relevant = reduce(operator.add, self._curation.values())
        times = [0] * 24
        for case_no in relevant:
            try:
                time = datetime.datetime.strptime(
                    self._reports[case_no]['time'], "%H:%M")
            except TypeError:
                continue
            times[time.hour] += 1 / self._template_data['report_years']

        rates = []
        labels = []
        traffic_counts = [0] * 24
        for i in range(24):
            end = i + 1 if i < 23 else 0
            labels.append("%d:00 - %d:00" % (i, end))
            traffic_counts[i] = traffic_raw_counts[i] / (
                traffic_num_readings[i] / 4.0)
            rates.append(float(times[i]) / traffic_counts[i])

        self._save_data("hourly.json",
                        {"labels": labels,
                         "series": [times, [], traffic_counts, [], rates]})

        self._template_data["hrir_correlation"] = numpy.corrcoef(
            times, traffic_counts)[1][0]

    def _xform_injury_severities_by_location(self):
        """Collect data on injury rates by collision location."""
        LOG.info("Collecting data on injury severity")

        injuries = {}
        injuries_by_loc = {}
        injuries_by_sev = collections.defaultdict(int)
        cases_by_loc = {}
        rates_by_loc = {}
        for name, cases in self._curation.items():
            if name == "unknown":
                continue
            loc = self.title(name)
            counts = [0 for _ in range(5)]
            for case_no in cases:
                sev = self._reports[case_no]['injury_severity'] or 5
                if sev != 5:
                    counts[sev] += 1
                    self._template_data['injured_count'] += 1
                injuries_by_sev[sev] += 1
            injuries_by_loc[loc] = sum(counts)
            injuries[loc] = counts
            cases_by_loc[loc] = len(cases)
            rates_by_loc[loc] = float(injuries_by_loc[loc]) / cases_by_loc[loc]

        labels = []
        series = [[] for i in range(1, 5)]
        tooltips = [[] for i in range(1, 5)]
        for loc, _ in reversed(sorted(rates_by_loc.items(),
                                      key=operator.itemgetter(1))):
            labels.append(loc)
            for i in range(1, 5):
                count = injuries[loc][i]
                sev_rate = 100 * float(count) / cases_by_loc[loc]
                series[i - 1].append(sev_rate)
                tooltips[i - 1].append(
                    "Rate of %s on %s: %0.1f%%\nCount: %d\n%0.1f%% of %s\n"
                    "%0.1f%% of %s\n" % (
                        self.injury_severities[i], loc, sev_rate, count,
                        100 * float(count) / injuries_by_sev[i],
                        self.injury_severities[i],
                        100 * float(count) / injuries_by_loc[loc],
                        loc))

        self._save_data("injury_rates.json", {"labels": labels,
                                              "series": series,
                                              "tooltips": tooltips})

    def _xform_injury_severities(self):
        """Munge data for pie chart of the relative rates of injury severities
        """
        LOG.info("Transforming injury severity data")

        severities = collections.defaultdict(int)
        for name, cases in self._curation.items():
            for case_no in cases:
                sev = self._reports[case_no]['injury_severity'] or 5
                severities[self.injury_severities[sev]] += 1

        total = sum(severities.values())
        data = {"labels": [], "series": []}
        for key, val in severities.items():
            data["labels"].append("%s: %d (%0.1f%%)" % (
                key, val, float(val) / total * 100))
            data["series"].append(val)
        self._save_data("injury_severities.json", data)

    def _xform_injury_regions(self):
        """Data for rates of injury by primary injury region."""
        LOG.info("Transforming data for injury regions")

        regions = collections.defaultdict(int)
        for case_no in reduce(operator.add, self._curation.values()):
            if case_no.startswith("NDOR"):
                continue
            region = self._reports[case_no]['injury_region']
            sev = self._reports[case_no]['injury_severity'] or 5
            if region:
                regions[region] += 1
            elif sev != 5:
                # injury reported, but no injury region
                regions['Unknown'] += 1

        data = {"labels": [], "series": []}
        total = sum(regions.values())
        other = 0
        for region, count in reversed(sorted(regions.items(),
                                             key=operator.itemgetter(1))):
            if region == "Unknown" or float(count) / total < 0.04:
                other += count
            else:
                data["labels"].append("%s: %d (%0.1f%%)" % (
                    region, count, float(count) / total * 100))
                data["series"].append(count)
        if other:
            data["labels"].append("Other/Unknown: %d (%0.1f%%)" % (
                other, float(other) / total * 100))
            data["series"].append(other)

        self._save_data("injury_regions.json", data)

    def _xform_proportions(self):
        """Create data for pie chart of collisions by location."""
        LOG.info("Transforming data on proportions of collision locations")

        data = {"labels": [], "series": []}
        total = len(reduce(operator.add, self._curation.values()))
        for name, cases in reversed(sorted(self._curation.items(),
                                           key=lambda d: len(d[1]))):
            num_cases = len(cases)
            data["labels"].append("%s: %d (%0.1f%%)" % (
                self.title(name), num_cases, float(num_cases) / total * 100))
            data["series"].append(num_cases)
        self._save_data("proportions.json", data)

    def _xform_genders(self):
        """Create data for pie chart of collisions by gender."""
        LOG.info("Transforming data on collisions by gender")

        by_gender = collections.Counter(r['cyclist_gender']
                                        for c, r in self._reports.items()
                                        if r.get('cyclist_gender') is not None)
        total = sum(by_gender.values())

        data = {"labels": [], "series": []}

        def _record(label, count):
            data["labels"].append("%s: %s (%0.1f%%)" %
                                  (label, count, 100.0 * count / total))
            data["series"].append(count)

        _record("Male", by_gender["M"])
        _record("Female", by_gender["F"])

        self._save_data("by_gender.json", data)

    def _xform_hit_and_runs(self):
        """Create data for pie chart of hit-and-runs."""
        LOG.info("Transforming data on hit-and-runs")
        hitnrun_data = json.load(open(self.options.hitnrun_data))
        total_hnrs = len(reduce(operator.add, hitnrun_data.values()))

        data = {"labels": [], "series": []}
        num_driver = len(hitnrun_data["driver"])
        data["series"].append(num_driver)
        data["labels"].append("Driver only left scene: %s (%0.1f%%)" %
                              (num_driver, 100.0 * num_driver / total_hnrs))

        num_cyclist = len(hitnrun_data["cyclist"])
        data["series"].append(num_cyclist)
        data["labels"].append("Cyclist only left scene: %s (%0.1f%%)" %
                              (num_cyclist, 100.0 * num_cyclist / total_hnrs))

        num_both = len(hitnrun_data["both"]) + len(hitnrun_data["unclear"])
        data["series"].append(num_both)
        data["labels"].append(
            "Both parties left scene or unclear: %s (%0.1f%%)" %
            (num_both, 100.0 * num_both / total_hnrs))

        self._save_data("hit_and_runs.json", data)

        self._template_data['hit_and_run_counts'] = {
            t: len(c) for t, c in hitnrun_data.items()}
        self._template_data['hit_and_run_total'] = sum(
            self._template_data['hit_and_run_counts'].values())

    def sun_phases(self, date):
        if date not in self._sun_cache:
            self._sun_cache[date] = self.city.sun(date=date, local=True)
        return self._sun_cache[date]

    def _get_daylight_phase(self, dt):
        sun = self.sun_phases(dt)
        if dt < sun["dawn"] or dt > sun["dusk"]:
            return "night"
        elif dt < sun["sunrise"]:
            return "dawn"
        elif dt > sun["sunset"]:
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

        relevant = reduce(operator.add, self._curation.values())
        for case_no in relevant:
            try:
                crashtime = datetime.datetime.strptime(
                    "%s %s" % (self._reports[case_no]['date'],
                               self._reports[case_no]['time']),
                    "%Y-%m-%d %H:%M").replace(tzinfo=self.tz)
            except ValueError:
                continue

            if crashtime.month not in by_month:
                by_month[crashtime.month] = collections.defaultdict(int)

            by_month[crashtime.month][self._get_daylight_phase(crashtime)] += 1

        totals = collections.defaultdict(int)
        for data in by_month.values():
            for phase, count in data.items():
                totals[phase] += count
        total = sum(totals.values())

        pie_data = {"labels": [],
                    "series": [],
                    "tooltips": []}
        line_data = {"labels": [datetime.date(2017, m, 1).strftime("%B")
                                for m in range(1, 13)],
                     "series": []}
        for phase in self.daylight_phases:
            pie_data["labels"].append("%s: %d" % (phase.title(),
                                                  totals[phase]))
            pie_data["series"].append(totals[phase])
            pie_data["tooltips"].append("%0.1f%% of total" %
                                        (100 * float(totals[phase]) / total))

            line_data["series"].append([[] for m in range(12)])
            for month in range(12):
                month_total = sum(by_month[month + 1].values())
                line_data["series"][-1][month] = 100 * float(
                    by_month[month + 1].get(phase, 0)) / month_total

        line_data["series"].append([
            (100 * operator.sub(*reversed(
                self.city.daylight(date=datetime.date(2017, m, 1)))).seconds /
             60.0 / 60 / 24)
            for m in range(1, 13)])
        self._save_data("daylight_totals.json", pie_data)
        self._save_data("daylight_by_month.json", line_data)

        self._template_data["daylight_correlation"] = numpy.corrcoef(
            line_data["series"][-1], line_data["series"][-2])[1][0]

        traffic_by_phase = collections.defaultdict(float)
        phase_duration = collections.defaultdict(int)
        for record in self._traffic_counts:
            date = datetime.datetime.strptime(record["date"], "%Y-%m-%d")
            time = datetime.datetime.strptime(record["time"],
                                              "%H:%M").replace(year=date.year,
                                                               month=date.month,
                                                               day=date.day,
                                                               tzinfo=self.tz)
            phase = self._get_daylight_phase(time)
            traffic_by_phase[phase] += (
                record["northbound"] + record["southbound"])
            # this is technically not quite accurate, but since we
            # have traffic readings in 15-minute chunks we assign each
            # chunk to a single day phase. So even if the sun sets
            # during a 15-minute chunk, we consider that chunk 'dusk'
            phase_duration[phase] += 15 * 60

        traffic_rates = {}
        collision_rates = {}
        for phase, traffic in traffic_by_phase.items():
            traffic_rates[phase] = (
                float(traffic) / phase_duration[phase]) * 60 * 60
            collision_rates[phase] = (
                float(totals[phase]) / traffic_rates[phase])
            self._template_data["%s_collision_rate" % phase] = (
                collision_rates[phase])

        rate_data = {"labels": [],
                     "series": [[]],
                     "tooltips": [[]]}
        for phase, rate in sorted(collision_rates.items(),
                                  key=operator.itemgetter(1)):
            rate_data["labels"].append(phase.title())
            rate_data["series"][0].append(rate)
            rate_data["tooltips"][0].append(
                "%0.2f collisions per HRIR\n%s total collisions\n%0.2f HRIR" %
                (rate, totals[phase], traffic_rates[phase]))

        self._save_data("daylight_rates.json", rate_data)

    def _pre_xform_template_data(self):
        """Create template data for rendering index.html."""
        self._template_data.update({"unparseable_count": 0,
                                    "ndor_count": 0})
        first_report = None
        last_report = None
        bike_reports = reduce(operator.add, self._curation.values())
        post_2011_reports = 0
        bike_report_count = 0
        for report in self._reports.values():
            if report['date'] is None:
                self._template_data['unparseable_count'] += 1
                continue
            date = datetime.datetime.strptime(report['date'], "%Y-%m-%d")
            if first_report is None or date < first_report:
                first_report = date
            if last_report is None or date > last_report:
                last_report = date
            if report['case_number'].startswith("NDOR"):
                self._template_data['ndor_count'] += 1
            if date.year > 2011:
                post_2011_reports += 1
                if report['case_number'] in bike_reports:
                    bike_report_count += 1

        self._template_data["first_report"] = first_report.strftime(
            "%B %e, %Y")
        self._template_data["last_report"] = last_report.strftime("%B %e, %Y")
        self._template_data["bike_reports"] = bike_report_count
        self._template_data["post_2011_reports"] = post_2011_reports

        self._template_data["bike_pct"] = (
            100.0 * self._template_data["bike_reports"] /
            self._template_data["post_2011_reports"])
        self._template_data['statuses'] = {n: len(d)
                                           for n, d in self._curation.items()}
        self._template_data['total_road'] = (
            len(self._curation['road']) + len(self._curation['intersection']))
        self._template_data['total_sidewalk'] = (
            len(self._curation['sidewalk']) + len(self._curation['crosswalk']))

        report_time_period = datetime.datetime.now() - first_report
        self._template_data['report_years'] = report_time_period.days / 365.25

    def _post_xform_template_data(self):
        self._template_data['pct_children'] = (
            float(self._template_data['num_children'] * 100) /
            self._template_data['bike_reports'])

        full_data_time_period = (
            datetime.date.today() - datetime.date(2012, 1, 1))
        full_data_years = full_data_time_period.days / 365.25

        self._template_data['under_11_per_year'] = (
            self._template_data['under_11'] /
            full_data_years)

    def _save_data(self, filename, data):
        """Save JSON to the given filename."""
        path = os.path.join(self.options.graph_data, filename)
        LOG.info("Writing graph data to %s" % path)
        json.dump(data, open(path, "w"))

    @staticmethod
    def title(name):
        return name.title().replace("_", " ")

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
        LOG.info("Writing template data to %s" % tmpl_path)
        json.dump(self._template_data, open(tmpl_path, "w"))

    def satisfied(self):
        return os.path.exists(self.options.collision_graph)
