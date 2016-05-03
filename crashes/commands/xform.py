"""Produce graphs of collision data."""

import calendar
import collections
import datetime
import functools
import json
import operator
import os

from crashes.commands import base
from crashes.commands import curate
from crashes import log

LOG = log.getLogger(__name__)


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

    def __init__(self, options):
        super(Xform, self).__init__(options)
        self._reports = json.load(open(self.options.all_reports))
        self._curation = json.load(open(self.options.curation_results))
        del self._curation['not_involved']

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
        return diff.days / 365.0

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
        months = collections.defaultdict(set)

        relevant = reduce(operator.add, self._curation.values())
        for case_no in relevant:
            date_str = self._reports[case_no]['date']
            date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            month = datetime.date(date.year, date.month, 1)
            collision_counts[month] += 1
            yearly_counts[date.year] += 1
            monthly_aggregate[date.month] += 1
            months[month.strftime("%b")].add(date.year)

        avg_per_month = {}
        labels = []
        series = []
        tooltips = []
        month = min(collision_counts.keys())

        while month <= datetime.date.today():
            count = collision_counts.get(month, 0)
            labels.append(month.strftime("%b %Y"))
            series.append(count)
            month_name = month.strftime("%B")
            avg_per_month[month.month] = (
                float(monthly_aggregate[month.month]) /
                len(months[month.strftime("%b")]))

            tooltips.append(
                "%s: %d\n%0.1f%% of total\n%0.1f%% of %s\n%s average: %0.1f" %
                (month.strftime("%b %Y"), count,
                 100 * (float(count) / len(relevant)),
                 100 * (float(count) / yearly_counts[month.year]),
                 month.strftime("%Y"), month_name,
                 avg_per_month[month.month]))
            next_month = month + datetime.timedelta(31)
            month = datetime.date(next_month.year, next_month.month, 1)

        self._save_data("monthly.json", {"labels": labels,
                                         "series": [series],
                                         "tooltips": [tooltips]})

        aggregate_data = {"labels": [], "series": [[]], "tooltips": [[]],
                          "activate_tooltips": [[]]}
        min_count = min(monthly_aggregate.values())
        max_count = max(monthly_aggregate.values())
        for i in range(12):
            month = datetime.date(2000, i + 1, 1)
            month_name = month.strftime("%B")
            aggregate_data["labels"].append(month_name)
            count = monthly_aggregate[month.month]
            aggregate_data["series"][0].append(count)
            aggregate_data["tooltips"][0].append("%s: %d\n%0.1f%% of total" % (
                month_name, count, 100 * float(count) / len(relevant)))
            if min_count is not None and count == min_count:
                aggregate_data["activate_tooltips"][0].append(True)
                min_count = None
                aggregate_data["tooltips"][0][-1] += "\nLeast collisions per month"
            elif max_count is not None and count == max_count:
                aggregate_data["activate_tooltips"][0].append(True)
                max_count = None
                aggregate_data["tooltips"][0][-1] += "\nMost collisions per month"
            else:
                aggregate_data["activate_tooltips"][0].append(False)

        self._save_data("monthly_aggregate.json", aggregate_data)

        years = sorted(yearly_counts.keys())
        yearly_data = {
            "labels": years,
            "tooltips": [[
                "%s: %d\n%01.f%% of total" % (
                    year, yearly_counts[year],
                    100 * float(yearly_counts[year]) / len(relevant))
                for year in years]],
            "series": [[yearly_counts[k] for k in years]]}

        # a flat multiplier doesn't work to predict the collision rate
        # for the current year, since different months have wildly
        # different rates of collisions. so first we calculate how
        # many collisions should have happened by this point in the
        # year
        cur_year = datetime.date.today().year
        expected = 0
        last = max(datetime.datetime.strptime(r["date"], "%Y-%m-%d")
                   for r in self._reports.values() if r["date"]).date()
        for i in range(12):
            days_in_month = calendar.monthrange(cur_year, i + 1)[1]
            end = datetime.date(cur_year, i + 1, days_in_month)
            if last > end:
                expected += avg_per_month[end.month]
            else:
                month_portion = float(last.day) / days_in_month
                expected += avg_per_month[end.month] * month_portion
                break
        avg_per_year = (float(sum(yearly_counts.values()[0:-1])) /
                        (len(yearly_counts) - 1))
        predicted = (float(yearly_counts[cur_year]) / expected) * avg_per_year

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
        """Collate three age-related datasets.

        * Collision location by age
        * A histogram of total number of collisions by age
        """
        LOG.info("Collecting data on ages of cyclists "
                 "and collision locations by age")

        loc_by_age = {}
        total_by_age = collections.defaultdict(int)
        for name, cases in self._curation.items():
            location = name.title()
            for case_no in cases:
                age = self._get_age(case_no)
                if age:
                    narrow_age_range = self._get_narrow_age_range(age)
                    wide_age_range = self._get_wide_age_range(age)
                    if location not in loc_by_age:
                        loc_by_age[location] = {r: 0
                                                for r in self.wide_age_ranges}
                    loc_by_age[location][wide_age_range] += 1
                    total_by_age[wide_age_range] += 1
                    if wide_age_range != narrow_age_range:
                        total_by_age[narrow_age_range] += 1
                    if narrow_age_range == self.narrow_age_ranges[0]:
                        print(case_no)

        locations = loc_by_age.keys()
        for age_range in self.wide_age_ranges:
            series = []
            labels = []
            tooltips = []
            for loc in locations:
                collisions = loc_by_age[loc].get(age_range, 0)
                if collisions:
                    # the values are absolute numbers of collisions;
                    # we want the Y axis to be the proportion of
                    # collisions by people that age, not number
                    series.append(
                        collisions /
                        float(total_by_age[age_range]) * 100)
                    labels.append(loc)
                    tooltips.append("%0.1f%%\n%d collisions" % (
                        series[-1], collisions))
                else:
                    series.append(0)
                    labels.append("")
                    tooltips.append("")
            self._save_data("location_by_age_%s.json" % age_range,
                            {"labels": labels,
                             "tooltips": tooltips,
                             "series": series,
                             "age_range": str(age_range),
                             "title": "%s years old\n%d total collisions" % (
                                 age_range, total_by_age[age_range])})

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
        """Collect data for collision time of day."""
        LOG.info("Collecting data on collision times")

        relevant = reduce(operator.add, self._curation.values())
        times = [0] * 24
        for case_no in relevant:
            try:
                time = datetime.datetime.strptime(
                    self._reports[case_no]['time'], "%H:%M")
            except TypeError:
                continue
            times[time.hour] += 1

        labels = []
        tooltips = []
        activate_tooltips = []
        min_count = min(times)
        max_count = max(times)
        for i in range(24):
            end = i + 1 if i < 23 else 0
            labels.append("%d:00 - %d:00" % (i, end))
            tooltips.append("%s: %d\n%0.1f%% of total" % (
                labels[-1], times[i], 100 * float(times[i]) / len(relevant)))
            if min_count is not None and times[i] == min_count:
                activate_tooltips.append(True)
                min_count = None
                tooltips[-1] += "\nLeast collisions per hour"
            elif max_count is not None and times[i] == max_count:
                activate_tooltips.append(True)
                max_count = None
                tooltips[-1] += "\nMost collisions per hour"
            else:
                activate_tooltips.append(False)

        self._save_data("hourly.json",
                        {"labels": labels,
                         "series": [times],
                         "tooltips": [tooltips],
                         "activate_tooltips": [activate_tooltips]})

    def _xform_injury_severities_by_location(self):
        """Collect data on injury rates by collision location."""
        LOG.info("Collecting data on injury severity")

        injuries = {}
        injuries_by_loc = {}
        injuries_by_sev = collections.defaultdict(int)
        cases_by_loc = {}
        rates_by_loc = {}
        for name, cases in self._curation.items():
            loc = name.title()
            counts = [0 for _ in range(5)]
            for case_no in cases:
                sev = self._reports[case_no]['injury_severity'] or 5
                if sev != 5:
                    counts[sev] += 1
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
        LOG.info("Collecting data on proportions of collision locations")

        data = {"labels": [], "series": []}
        total = len(reduce(operator.add, self._curation.values()))
        for name, cases in reversed(sorted(self._curation.items(),
                                           key=lambda d: len(d[1]))):
            num_cases = len(cases)
            data["labels"].append("%s: %d (%0.1f%%)" % (
                name.title(), num_cases, float(num_cases) / total * 100))
            data["series"].append(num_cases)
        self._save_data("proportions.json", data)

    def _xform_lb716(self):
        """Create data for various LB716-related charts."""
        lb716_data = json.load(open(self.options.lb716_results))

        row_collisions = len(lb716_data["row"])
        non_row_collisions = len(lb716_data["non-row"])
        self._save_data(
            "lb716_crosswalk_proportions.json",
            {"series": [row_collisions, non_row_collisions],
             "labels": [
                 "%0.1f%%" % (
                     100 * float(row_collisions) / (
                         row_collisions + non_row_collisions)),
                 ""],
             "title": ("%0.1f%% of collisions in bike path crosswalks "
                       "could be prevented by LB716" % (
                           100 * float(row_collisions) / (
                               row_collisions + non_row_collisions)))})

        sidewalk_collisions = len(lb716_data["sidewalk"])
        total_path_collisions = (sidewalk_collisions + row_collisions +
                                 non_row_collisions)
        self._save_data(
            "lb716_proportions.json",
            {"series": [row_collisions,
                        sidewalk_collisions + non_row_collisions],
             "labels": [
                 "%0.1f%%" % (
                     100 * float(row_collisions) / total_path_collisions),
                 ""],
             "title": ("%0.1f%% of all collisions in bike paths could be "
                       "prevented by LB716" % (
                           100 * float(row_collisions) / total_path_collisions
                       ))})

        all_crosswalk = len(self._curation["crosswalk"])
        self._save_data(
            "lb716_all_crosswalks.json",
            {"series": [row_collisions, all_crosswalk - row_collisions],
             "labels": [
                 "%0.1f%%" % (100 * float(row_collisions) / all_crosswalk),
                 ""],
             "title": ("%0.1f%% of all crosswalk collisions could be "
                       "prevented by LB716" % (
                           100 * float(row_collisions) / all_crosswalk))})

        total = len(reduce(operator.add, self._curation.values()))
        self._save_data(
            "lb716_all.json",
            {"series": [row_collisions, total - row_collisions],
             "labels": [
                 "%0.1f%%" % (100 * float(row_collisions) / total),
                 ""],
             "title": ("%0.1f%% of all collisions city-wide could be "
                       "prevented by LB716" % (
                           100 * float(row_collisions) / total))})

        by_severity = collections.defaultdict(int)
        by_age = collections.defaultdict(int)
        yearly_counts = collections.defaultdict(int)
        for case_no in lb716_data["row"]:
            age = self._get_age(case_no)
            if age:
                age_range = self._get_wide_age_range(age)
                by_age[age_range] += 1

            sev = self._reports[case_no]['injury_severity'] or 5
            by_severity[sev] += 1

            date_str = self._reports[case_no]['date']
            date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            yearly_counts[date.year] += 1

        ages_data = {"labels": [], "series": [[]], "tooltips": [[]]}
        total_with_known_age = sum(by_age.values())
        for age_range in self.wide_age_ranges:
            ages_data["labels"].append(str(age_range))
            ages_data["series"][0].append(by_age[age_range])
            ages_data["tooltips"][0].append(
                "%s: %d collisions\n%0.1f%% of bike path collisions" % (
                    age_range, by_age[age_range],
                    100 * float(by_age[age_range]) / total_with_known_age))

        self._save_data("lb716_ages.json", ages_data)

        severity_data = {"labels": [], "series": [], "tooltips": []}
        for sevid, severity in self.injury_severities.items():
            count = by_severity.get(sevid, 0)
            severity_data["series"].append(count)
            if count > 0:
                severity_data["labels"].append(severity)
                severity_data["tooltips"].append(
                    "%s: %0.1f%%\n%d collisions" % (
                        severity,
                        100 * float(count) / total_path_collisions,
                        count))
            else:
                severity_data["labels"].append("")
                severity_data["tooltips"].append("")

        self._save_data("lb716_severity.json", severity_data)

        years = sorted(yearly_counts.keys())
        self._save_data("lb716_years.json", {
            "labels": years,
            "tooltips": [["%s: %d" % (year, yearly_counts[year])
                          for year in years]],
            "series": [[yearly_counts[k] for k in years]]})

    def _save_data(self, filename, data):
        """Save JSON to the given filename."""
        path = os.path.join(self.options.graph_data, filename)
        LOG.info("Writing graph data to %s" % path)
        json.dump(data, open(path, "w"))

    def __call__(self):
        self._xform_proportions()
        self._xform_injury_severities()
        self._xform_injury_severities_by_location()
        self._xform_injury_regions()
        self._xform_timings()
        self._xform_collision_times()
        self._xform_ages()
        self._xform_lb716()

    def satisfied(self):
        return os.path.exists(self.options.collision_graph)
