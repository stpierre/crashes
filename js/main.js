var map;
var layers = {};

function initialize() {
    map = new google.maps.Map(document.getElementById('map-canvas'), {
        zoom: 12,
        center: {lat: 40.807, lng: -96.69}
    });

    //var datadir = "http://localhost:8000/data/geojson/"
    var datadir = "http://stpierre.github.io/crashes/data/geojson/"
    var markers = "http://www.googlemapsmarkers.com/v1/"

    layers['crosswalk'] = new google.maps.Data()
    layers['crosswalk'].loadGeoJson(datadir + "crosswalk.json");
    layers['crosswalk'].setStyle({icon: markers + "C/FF9900/"})
    layers['crosswalk'].setMap(map)

    layers['sidewalk'] = new google.maps.Data()
    layers['sidewalk'].loadGeoJson(datadir + "sidewalk.json");
    layers['sidewalk'].setStyle({icon: markers + "S/FFFF66/"})
    layers['sidewalk'].setMap(map)

    layers['road'] = new google.maps.Data()
    layers['road'].loadGeoJson(datadir + "road.json");
    layers['road'].setStyle({icon: markers + "R/009900/"})
    layers['road'].setMap(map)

    layers['intersection'] = new google.maps.Data()
    layers['intersection'].loadGeoJson(datadir + "intersection.json");
    layers['intersection'].setStyle({icon: markers + "I/0099FF/"})
    layers['intersection'].setMap(map)

    layers['elsewhere'] = new google.maps.Data()
    layers['elsewhere'].loadGeoJson(datadir + "elsewhere.json");
    layers['elsewhere'].setStyle({icon: markers + "E/CC33FF"})
    layers['elsewhere'].setMap(map)
}

$(document).ready(function(){
    google.maps.event.addDomListener(window, 'load', initialize);

    $('button.map-buttons').click(function(){
	var layer_name = $(this).attr('map-layer');

	$(this).toggleClass('current');
        layers[layer_name].setMap($(this).hasClass('current') ? map : null)
    })

    $('ul.tabs li').click(function(){
        var tab_group = $(this).attr('tab-group')
	var tab_id = $(this).attr('data-tab');

	$('ul.tabs li[tab-group='+tab_group+']').removeClass('current');
	$('.tab-content[tab-group='+tab_group+']').removeClass('current');

	$(this).addClass('current');
	$("#"+tab_id).addClass('current');
    })
})
