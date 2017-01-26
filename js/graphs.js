var everyOther = function(value, index) {
    return index % 2 === 0 ? value : null;
};

var everyOtherLabel = {"labelInterpolationFnc": everyOther}

var ageRanges = ["0-10", "11-20", "21-30", "31-40", "41-50", "51-60", "61+"]

var allColors = ['#d70206',
                 '#f05b4f',
                 '#f4c63d',
                 '#d17905',
                 '#453d3f',
                 '#59922b',
                 '#0544d3',
                 '#6b0392',
                 '#f05b4f',
                 '#dda458',
                 '#eacf7d',
                 '#86797d',
                 '#b2c326',
                 '#6188e2',
                 '#a748ca']

var charts = {};
var chartColors = {};
var newline = new RegExp('\r?\n', 'g');


function getBarWidth(bins) {
    return Math.floor(80.0 / bins) + '%';
}


function initChart(cls, defaultData, url, graphID, options) {
    charts[graphID] = new cls(
        '#' + graphID, defaultData, options
    ).on('data', function(context) {
        if (context.type == 'update') {
            if ("tooltips" in context.data) {
                charts[graphID].tooltips = context.data["tooltips"];
                if ("activate_tooltips" in context.data) {
                    charts[graphID].activate_tooltips = context.data[
                        "activate_tooltips"];
                }
            }
            if (context.type == 'update' && "title" in context.data) {
                var titleID = '#' + graphID + "-title";
                $(titleID).html(context.data["title"].replace(newline,
                                                              '<br />'));
            }
        }
    }).on('draw', function(context) {
        var title;
        var activate = false;
        if (context.type == "bar" || context.type == "line" ||
            context.type == "slice") {
            if (typeof(context.seriesIndex) === 'undefined') {
                title = charts[graphID].tooltips[context.index];
                activate = charts[graphID].activate_tooltips[context.index];
            } else if (charts[graphID].tooltips.length > context.seriesIndex) {
                title = charts[graphID].tooltips[
                    context.seriesIndex][context.index];
                if (charts[graphID].activate_tooltips.length >
                    context.seriesIndex) {
                    activate = charts[graphID].activate_tooltips[
                        context.seriesIndex][context.index];
                }
            }
            if (typeof(title) !== "undefined" && title !== null) {
                var attr = {"title": title.replace(newline, '<br />'),
                            "data-toggle": "tooltip"};
                if (activate === true) {
                    attr["default-tooltip-on"] = "";
                }
                context.element.attr(attr);
            }
            if ((typeof(context.seriesIndex) !== 'undefined' &&
                 charts[graphID].tooltips.length == context.seriesIndex + 1 &&
                 charts[graphID].tooltips[context.seriesIndex].length ==
                 context.index + 1) ||
                (typeof(context.seriesIndex) === 'undefined' &&
                 charts[graphID].tooltips.length ==  context.index + 1)) {
                $('#' + graphID + ' [data-toggle="tooltip"]').tooltip({
                    container: 'body',
                    html: true,
                    trigger: 'click'
                });

                $('#' + graphID + ' [default-tooltip-on]').tooltip("show");
            }
        }
    });

    charts[graphID].tooltips = [];
    charts[graphID].activate_tooltips = [];

    $.getJSON(url, function(data){
        charts[graphID].update(data)
    });

    return charts[graphID]
}


function initPieChart(url, graphID, options) {
    return initChart(Chartist.Pie, {"labels": [], "series": []},
                     url, graphID, options);
}


var defaultAxisOptions = {"axisY": {"onlyInteger": true}}


function mergeOptions(defaults, user) {
    var retval = {};
    for (var attr in defaults) {
        retval[attr] = defaults[attr];
    }
    for (var attr in user) {
        retval[attr] = user[attr];
    }
    return retval
}


function skipLabels(value, index, labels) {
    return index % 2 === 0 ? value : null;
}


function initAxialChart(cls, url, graphID, options, yLabel) {
    var labelOpt = {
        chartPadding: {
            left: 20
        },
        plugins: [
            Chartist.plugins.ctAxisTitle({
                axisY: {
                    axisTitle: yLabel,
                    axisClass: 'ct-axis-title',
                    offset: {
                        x: 0,
                        y: -5
                    },
                    textAnchor: 'middle'
                },
                axisX: {
                    axisTitle: '',
                    axisClass: 'ct-axis-title',
                    offset: {
                        x: 0,
                        y: 0
                    },
                    textAnchor: 'middle'
                }})
            ]};

    return initChart(
        cls, {"labels": [], "series": [[]]},
        url, graphID, mergeOptions(mergeOptions(defaultAxisOptions, options),
                                   labelOpt));
}


function initDynamicWidthBarChart(url, graphID, options, yLabel) {
    initAxialChart(
        Chartist.Bar, url, graphID, options, yLabel
    ).on('data', function(context) {
        if (context.type == 'update') {
            charts[graphID].barWidth = getBarWidth(
                context.data['labels'].length);
        }
    }).on('draw', function(context) {
        if (context.type === 'bar') {
            context.element.attr(
                {style: 'stroke-width: ' + charts[graphID].barWidth + ';'});
        }
    });

    charts[graphID].barWidth = "30px";

    return charts[graphID];
}


function initLineChart(url, graphID, options, yLabel) {
    return initAxialChart(Chartist.Line, url, graphID, options, yLabel);
}


$(document).ready(function(){
    initPieChart("data/graph/proportions.json",
                 "location-pie-chart");
    initPieChart("data/graph/injury_severities.json",
                 "injury-severity-pie-chart");
    initPieChart("data/graph/injury_regions.json",
                 "injury-region-pie-chart");
    initPieChart("data/graph/hit_and_runs.json",
                 "hit-and-run-pie-chart");

    initLineChart("data/graph/location_by_age.json",
                  "location-by-age-line-chart",
                  {"showArea": true,
                   "high": 100,
                   "lineSmooth": Chartist.Interpolation.none(),
                   "showPoint": false},
                  "Percentage of collisions");
    initLineChart("data/graph/monthly.json",
                  "monthly-line-chart",
                  {"lineSmooth": Chartist.Interpolation.none(),
                   "showPoint": false,
                   "axisX": {"labelInterpolationFnc": skipLabels}});

    initDynamicWidthBarChart("data/graph/yearly.json",
                             "yearly-bar-chart",
                             {"stackBars": false},
                            "Collisions");
    initDynamicWidthBarChart("data/graph/hourly.json",
                             "hourly-bar-chart",
                             {"axisX": everyOtherLabel},
                             "Collisions");
    initDynamicWidthBarChart("data/graph/ages.json",
                             "ages-bar-chart", {},
                             "Collisions");
    initDynamicWidthBarChart("data/graph/monthly_aggregate.json",
                             "monthly-aggregate-bar-chart", {},
                             "Collisions");
    initDynamicWidthBarChart("data/graph/injury_rates.json",
                             "injury-rates-bar-chart",
                             {"stackBars": true, "high": 100},
                             "Injury rate (%)");
});
