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


var defaultBarOptions = {"axisY": {"onlyInteger": true}}


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


function initBarChart(url, graphID, options, yLabel) {
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
        Chartist.Bar, {"labels": [], "series": [[]]},
        url, graphID, mergeOptions(mergeOptions(defaultBarOptions, options),
                                   labelOpt));
}


function initDynamicWidthBarChart(url, graphID, options, yLabel) {
    initBarChart(
        url, graphID, options, yLabel
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


function initLineChart(url, graphID, options) {
    return initChart(Chartist.Line, {"labels": [], "series": [[]]},
                     url, graphID, options);
}


$(document).ready(function(){
    initPieChart("data/graph/proportions.json",
                 "location-pie-chart");
    initPieChart("data/graph/injury_severities.json",
                 "injury-severity-pie-chart");
    initPieChart("data/graph/injury_regions.json",
                 "injury-region-pie-chart");
    initPieChart("data/graph/lb716_crosswalk_proportions.json",
                 "lb716-crosswalk-pie");
    initPieChart("data/graph/lb716_proportions.json",
                 "lb716-all-bike-path-pie");
    initPieChart("data/graph/lb716_all_crosswalks.json",
                 "lb716-all-crosswalks-pie");
    initPieChart("data/graph/lb716_all.json",
                 "lb716-all-pie");
    initPieChart("data/graph/lb716_severity.json",
                 "lb716-severity-pie");

    initDynamicWidthBarChart("data/graph/yearly.json",
                             "yearly-bar-chart",
                             {"stackBars": true},
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
    initBarChart("data/graph/lb716_ages.json",
                 "lb716-ages-bar", {},
                 "Collisions");
    initBarChart("data/graph/lb716_years.json",
                 "lb716-yearly-bar", {},
                 "Collisions");

    var lastYear = null;
    var availableColors = allColors.slice(0);
    var curColor;
    chartColors['monthly-bar-chart'] = [];
    initBarChart(
        "data/graph/monthly.json",
        'monthly-bar-chart', {}, "Collisions"
    ).on('data', function(context){
        if (context.type == 'update') {
            for (var i = 0; i <= context.data['labels'].length; i++) {
                label = context.data['labels'][i]
                if (typeof(label) !== 'undefined') {
                    var space = label.indexOf(" ")
                    if (space != -1) {
                        year = parseInt(label.substr(space + 1))
                        if (year != lastYear) {
                            lastYear = year;
                            curColor = availableColors.shift()
                        }
                        chartColors['monthly-bar-chart'].push(curColor);
                    }
                }
            }
        }
    }).on('draw', function(context) {
        if (context.type === 'bar') {
            color = chartColors['monthly-bar-chart'][context.index];
            context.element.attr({"style": "stroke: " + color});
        }
    });

    for (var i = 0; i < ageRanges.length; i++) {
        var ageRange = ageRanges[i];
        var graphID = "location-by-age-" + ageRanges[i].replace("+",
                                                                "_") + "-pie";
        var dataURL = "data/graph/location_by_age_" + ageRanges[i] + ".json";

        initPieChart(dataURL, graphID);
    }
});
