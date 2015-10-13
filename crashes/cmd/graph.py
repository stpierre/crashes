"""Produce graphs of crash data."""

import collections
import datetime
import itertools
import json
import operator
import os

from matplotlib import pyplot
from matplotlib import ticker

from crashes.cmd import base
from crashes.cmd import curate
from crashes import log

LOG = log.getLogger(__name__)

SeverityAgePoint = collections.namedtuple("SeverityAgePoint",
                                          ["severity", "age"])


class AgeRange(object):
    def __init__(self, min=None, max=None):
        self._min = min or 0
        self._max = max

    def contains(self, other):
        return ((self._max is None and other >= self._min) or
                (self._min <= other <= self._max))

    def __str__(self):
        if self._max:
            return "%s-%s" % (self._min, self._max)
        else:
            return "%s+" % self._min


def auto_percent_with_abs(total):
    return lambda p: "%d (%0.1f%%)" % (round(total * p / 100), p)


class Graph(base.Command):
    """Produce graphs of crash data."""

    prerequisites = [curate.Curate]
    location_colors = {"crosswalk": "#ff9900",
                       "sidewalk": "#eeee66",
                       "road": "#009900",
                       "intersection": "#0099ff",
                       "elsewhere": "#cc33ff"}
    colors = ['yellowgreen', 'gold', 'lightskyblue', 'lightcoral', 'limegreen',
              'orchid', 'palegoldenrod']

    injury_severities = {
        1: "Killed",
        2: "Disabling",
        3: "Visible but not disabling",
        4: "Possible but not visible",
        5: "None"}

    age_ranges = [AgeRange(max=10),
                  AgeRange(11, 20),
                  AgeRange(21, 30),
                  AgeRange(31, 40),
                  AgeRange(41, 50),
                  AgeRange(51, 60),
                  AgeRange(min=61)]

    def __init__(self, options):
        super(Graph, self).__init__(options)
        self._reports = json.load(open(self.options.all_reports))
        self._curation = json.load(open(self.options.curation_results))
        del self._curation['not_involved']

    def _get_age(self, case_no):
        """Get the age of the cyclist in years for the given crash."""
        try:
            dob = datetime.datetime.strptime(
                self._reports[case_no]['cyclist_dob'], "%Y-%m-%d")
            date = datetime.datetime.strptime(
                self._reports[case_no]['date'], "%Y-%m-%d")
        except TypeError:
            return None

        diff = date - dob
        return diff.days / 365.0

    def _get_age_range(self, case_no_or_age):
        try:
            age = int(case_no_or_age)
        except ValueError:
            age = self._get_age(case_no_or_age)
        for range_id, age_range in enumerate(self.age_ranges):
            if age_range.contains(age):
                return range_id

    def _graph_monthly(self):
        """Draw a bar graph of crashes per month over the entire dataset."""
        LOG.info("Creating graph of crashes per month")
        crash_counts = collections.defaultdict(int)
        relevant = reduce(operator.add, self._curation.values())
        for case_no in relevant:
            date_str = self._reports[case_no]['date']
            date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            month = datetime.date(date.year, date.month, 1)
            crash_counts[month] += 1

        data = collections.OrderedDict()
        month = min(crash_counts.keys())

        # color each year differently
        year = month.year
        colors = []
        color_indexes = itertools.cycle(range(len(self.colors)))
        cur_color = color_indexes.next()

        while month <= datetime.date.today():
            data[month.strftime("%b %Y")] = crash_counts.get(month, 0)

            # color each year differently
            if month.year > year:
                cur_color = color_indexes.next()
                year = month.year
            colors.append(self.colors[cur_color])

            next_month = month + datetime.timedelta(31)
            month = datetime.date(next_month.year, next_month.month, 1)

        figure = pyplot.figure()
        axis = figure.add_subplot(1, 1, 1)
        axis.bar(range(len(data.keys())), data.values(), width=1,
                 color=colors)
        axis.set_xticks([0.5 + i for i in range(len(data.keys()))])
        axis.set_xticklabels(data.keys(), rotation=90,
                             ha='center')
        axis.axis(xmax=len(data.keys()))
        axis.set_xlabel("Crashes between a vehicle and bicycle")
        axis.set_ylabel("Number of crashes")
        self._savefig(figure, "monthly.png", bbox_inches='tight')

    def _graph_ages(self):
        """Draw three age-related graphs:

        * Crash location by age
        * Injury severity by age
        * A histogram of total number of crashes by age
        """
        LOG.info("Graphing ages of cyclists and crash locations by age")

        ages = []
        sev_by_age = []
        loc_by_age = {}
        total_by_age = collections.defaultdict(int)
        for name, cases in self._curation.items():
            for case_no in cases:
                age = self._get_age(case_no)
                if age:
                    ages.append(age)
                    sev = self._reports[case_no]['injury_severity'] or 5
                    sev_by_age.append(SeverityAgePoint(sev, age))
                    age_range = self._get_age_range(age)
                    if name.title() not in loc_by_age:
                        loc_by_age[name.title()] = {
                            i: 0 for i in range(len(self.age_ranges))}
                    loc_by_age[name.title()][age_range] += 1
                    total_by_age[age_range] += 1

        figure = pyplot.figure()
        axis = figure.add_subplot(1, 1, 1)
        for location, data in loc_by_age.items():
            # the values are absolute numbers of crashes; we want the
            # Y axis to be the proportion of crashes by people that
            # age, not number
            y = [n / float(total_by_age[r]) * 100
                 for r, n in data.items()]
            axis.plot(data.keys(), y, '-', linewidth=2,
                      color=self.location_colors[location.lower()],
                      label=location)
        axis.plot(total_by_age.keys(), total_by_age.values(), 'o',
                  color=self.colors[0], label="Total recorded crashes")
        axis.legend(bbox_to_anchor=(1.1, 1.1))
        axis.axis(ymax=max(total_by_age.values()) + 5)
        axis.set_xticks(range(len(self.age_ranges)))
        axis.set_xticklabels(self.age_ranges, ha='center')
        axis.set_xlabel("Age")
        axis.set_ylabel("Proportion of crashes by age")
        self._savefig(figure, "location_by_age.png")

        # calculate rolling average of severity by age
        avg_sev_by_age = []
        points = []
        for point in sorted(sev_by_age, key=operator.attrgetter("age")):
            points.append(point)
            while point.age - points[0].age > 5:  # 5-year rolling average
                points.pop(0)
            avg_sev = sum(p.severity for p in points) / float(len(points))
            avg_age = sum(p.age for p in points) / float(len(points))
            avg_sev_by_age.append(SeverityAgePoint(avg_sev, avg_age))

        figure = pyplot.figure()
        axis = figure.add_subplot(1, 1, 1)
        axis.plot([p.age for p in sev_by_age],
                  [p.severity for p in sev_by_age],
                  'o', color=self.colors[0])
        axis.plot([p.age for p in avg_sev_by_age],
                  [p.severity for p in avg_sev_by_age],
                  '-', color=self.colors[3],
                  label="5-year rolling average")
        axis.axis(ymin=0.75, ymax=4.5)
        axis.set_xlabel("Age of cyclist")
        axis.set_ylabel("Injury severity")
        axis.set_yticks(self.injury_severities.keys())
        axis.set_yticklabels(self.injury_severities.values(),
                             rotation=60, verticalalignment="top")
        axis.legend()
        self._savefig(figure, "severity_by_age.png", bbox_inches='tight')

        figure = pyplot.figure()
        axis = figure.add_subplot(1, 1, 1)
        axis.hist(ages, bins=20, color=self.colors[0])
        axis.set_xlabel("Age of cyclist")
        axis.set_ylabel("Number of crashes")
        self._savefig(figure, "ages.png")

    def _graph_crash_times(self):
        """Draw a histogram of crash time of day."""
        LOG.info("Graphing crash times")

        times = []
        for case_no in reduce(operator.add, self._curation.values()):
            try:
                time = datetime.datetime.strptime(
                    self._reports[case_no]['time'], "%H:%M")
            except TypeError:
                continue
            times.append(time.hour)

        figure = pyplot.figure()
        axis = figure.add_subplot(1, 1, 1)
        axis.hist(times, bins=range(25), color=self.colors[0])
        axis.set_xticks(range(0, 23, 2))
        axis.set_xticklabels(["%d:00" % i for i in range(0, 23, 2)],
                             rotation=90)
        axis.set_xlabel("Distribution of bicycle crash times")
        axis.set_ylabel("Number of crashes")
        self._savefig(figure, "crash_times.png", bbox_inches='tight')

    def _graph_injury_severities(self):
        """Draw injury-related graphs:

        * A stacked bar graph of injury rates by crash location
        * A pie chart of the relative rates of injury severities
        """
        LOG.info("Graphing injury severity data")

        injury_rates = {}
        total_injuries = {}
        severities = collections.defaultdict(int)
        for name, cases in self._curation.items():
            loc = name.title()
            counts = [0 for _ in range(5)]
            for case_no in cases:
                sev = self._reports[case_no]['injury_severity'] or 5
                if sev != 5:
                    counts[sev] += 1
                severities[self.injury_severities[sev]] += 1

            injury_rates[loc] = {i: float(counts[i]) / len(cases) * 100
                                 for i in range(1, 5)}
            injuries = sum(c for c in counts)
            total_injuries[loc] = float(injuries) / len(cases) * 100

        def _combined_injury_rates(key1, key2):
            name = "%s + %s" % (key1, key2)
            injury_rates[name] = {
                i: (injury_rates[key1][i] + injury_rates[key2][i]) / 2.0
                for i in range(1, 5)}
            total_injuries[name] = (total_injuries[key1] +
                                    total_injuries[key2]) / 2.0

        _combined_injury_rates("Sidewalk", "Crosswalk")
        _combined_injury_rates("Road", "Intersection")

        labels = []
        for loc, _ in reversed(sorted(total_injuries.items(),
                                      key=operator.itemgetter(1))):
            labels.append(loc)

        figure = pyplot.figure()
        axis = figure.add_subplot(1, 1, 1)
        bottoms = [0 for _ in labels]
        rects = None
        for i in range(1, 5):
            sev_data = [injury_rates[l][i] for l in labels]
            rects = axis.bar(range(len(labels)), sev_data, width=0.9,
                             color=self.colors[i - 1], bottom=bottoms,
                             label=self.injury_severities[i])
            bottoms = [bottoms[j] + sev_data[j] for j in range(len(bottoms))]

            # label each region
            for rect in rects:
                if rect.get_height():
                    x = rect.get_x() + rect.get_width() / 2.0
                    y = rect.get_y() + rect.get_height() / 2.0 - 1
                    axis.text(x, y, "%0.1f%%" % rect.get_height(),
                              ha='center', va='bottom')

        self._autolabel(axis, rects)
        axis.legend(bbox_to_anchor=(1.1, 1.25))
        axis.set_xticks([0.5 + i for i in range(len(labels))])
        axis.set_xticklabels(labels, rotation=90, ha='center')
        axis.yaxis.set_major_formatter(ticker.FormatStrFormatter('%d%%'))
        axis.set_xlabel("Injury rates by crash location")
        self._savefig(figure, "injury_rates.png", bbox_inches='tight')

        figure = pyplot.figure()
        axis = figure.add_subplot(1, 1, 1)
        total = sum(severities.values())
        axis.pie(severities.values(), labels=severities.keys(),
                 colors=self.colors,
                 autopct=auto_percent_with_abs(total),
                 shadow=True)
        axis.set_xlabel("Injury severities")
        self._savefig(figure, "injury_severities.png", bbox_inches='tight')

    def _graph_injury_regions(self):
        """Draw a pie chart of rates of injury by primary injury region."""
        LOG.info("Graphing injury regions")

        regions = collections.defaultdict(int)
        for case_no in reduce(operator.add, self._curation.values()):
            region = self._reports[case_no]['injury_region']
            sev = self._reports[case_no]['injury_severity'] or 5
            if region:
                regions[region] += 1
            elif sev != 5:
                # injury reported, but no injury region
                regions['Unknown'] += 1

        labels = []
        sizes = []
        total = sum(regions.values())
        other = 0
        for region, count in reversed(sorted(regions.items(),
                                             key=operator.itemgetter(1))):
            if region == "Unknown" or float(count) / total < 0.04:
                other += count
            else:
                labels.append(region)
                sizes.append(count)
        if other:
            labels.append("Other/Unknown")
            sizes.append(other)

        figure = pyplot.figure()
        axis = figure.add_subplot(1, 1, 1)
        axis.pie(sizes, labels=labels, colors=self.colors,
                 autopct=lambda p: "%0.1f%%" % p,
                 startangle=90, shadow=True)
        axis.set_xlabel("Region of primary injury")
        self._savefig(figure, "injury_regions.png")

    def _graph_proportions(self):
        """Draw a pie chart of crashes by location."""
        LOG.info("Graphing proportions of crash locations")

        labels = []
        sizes = []
        colors = []
        total = 0
        for name, cases in reversed(sorted(self._curation.items(),
                                           key=lambda d: len(d[1]))):
            labels.append(name.title())
            sizes.append(len(cases))
            colors.append(self.location_colors[name])
            total += len(cases)

        figure = pyplot.figure()
        axis = figure.add_subplot(1, 1, 1)
        axis.pie(sizes, labels=labels, colors=colors,
                 autopct=auto_percent_with_abs(total),
                 startangle=90, shadow=True)
        axis.set_xlabel("Crash locations")
        self._savefig(figure, "proportions.png")

    @staticmethod
    def _autolabel(axis, rects, fmt="%0.1f%%"):
        """Attach text labels to the top of a bar chart."""
        for rect in rects:
            height = rect.get_height() + rect.get_y()
            axis.text(rect.get_x() + rect.get_width() / 2.0,
                      height + 1, fmt % height,
                      ha='center', va='bottom')

    def _savefig(self, figure, filename, **kwargs):
        """Save a pyplot figure to the given filename."""
        path = os.path.join(self.options.imagedir, filename)
        LOG.info("Writing graph to %s" % path)
        return figure.savefig(path, **kwargs)

    def __call__(self):
        self._graph_monthly()
        self._graph_proportions()
        self._graph_injury_severities()
        self._graph_ages()
        self._graph_crash_times()
        self._graph_injury_regions()

    def satisfied(self):
        return os.path.exists(self.options.crash_graph)
