var everyOther = function(value, index) {
    return index % 2 === 0 ? value : null;
};

var everyOtherLabel = {"labelInterpolationFnc": everyOther}

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


function initChart(cls, defaultData, tooltipElement, url, graphID, options) {
    charts[graphID] = new cls(
        '#' + graphID, defaultData, options
    ).on('data', function(context) {
        if (context.type == 'update') {
            if ("tooltips" in context.data) {
                charts[graphID].tooltips = context.data["tooltips"];
            }
        }
    }).on('draw', function(context) {
        if (context.type === 'bar' &&
            charts[graphID].tooltips.length > context.seriesIndex) {
            title = charts[graphID].tooltips[context.seriesIndex][context.index]
            if (title !== null) {
                context.element.attr(
                    {"title": title.replace(newline, '<br />'),
                     "data-toggle": "tooltip"});
            }
        }
        $('#' + graphID + ' ' + tooltipElement).tooltip({
            container: 'body',
            html: true,
            trigger: 'click'
        });
    });

    charts[graphID].tooltips = [];

    $.getJSON(url, function(data){
        charts[graphID].update(data)
    });

    return charts[graphID]
}


function initPieChart(url, graphID, options) {
    return initChart(Chartist.Pie, {"labels": [], "series": []}, "path",
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
        Chartist.Bar, {"labels": [], "series": [[]]}, "line",
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
    return initChart(Chartist.Line, {"labels": [], "series": [[]]}, "line",
                     url, graphID, options);
}


$(document).ready(function(){
    initPieChart("data/graph/proportions.json",
                 "location-pie-chart");
    initPieChart("data/graph/injury_severities.json",
                 "injury-severity-pie-chart");
    initPieChart("data/graph/injury_regions.json",
                 "injury-region-pie-chart");

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

    initBarChart("data/graph/location_by_age.json",
                  "location-by-age-bar-chart", {}, "% of collisions");
});
