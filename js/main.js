var all_map;
var layers = {};
//var datadir = "http://localhost:8000/data/geojson/";
var datadir = "http://stpierre.github.io/crashes/data/geojson/";
var markers = "http://www.googlemapsmarkers.com/v1/";
//var bike_paths_data = "http://localhost:8000/data/bike-paths.geojson";
var bike_paths_data = "http://stpierre.github.io/lincoln-bike-routes/data/bike-paths.geojson";


function init_maps() {
    all_map = new google.maps.Map(
        document.getElementById('all-collisions-map-canvas'), {
            zoom: 12,
            center: {lat: 40.807, lng: -96.69}
    });

    layers['crosswalk'] = new google.maps.Data()
    layers['crosswalk'].loadGeoJson(datadir + "crosswalk.json");
    layers['crosswalk'].setStyle({icon: markers + "C/FF9900/"})
    layers['crosswalk'].setMap(all_map)

    layers['sidewalk'] = new google.maps.Data()
    layers['sidewalk'].loadGeoJson(datadir + "sidewalk.json");
    layers['sidewalk'].setStyle({icon: markers + "S/FFFF66/"})
    layers['sidewalk'].setMap(all_map)

    layers['road'] = new google.maps.Data()
    layers['road'].loadGeoJson(datadir + "road.json");
    layers['road'].setStyle({icon: markers + "R/009900/"})
    layers['road'].setMap(all_map)

    layers['intersection'] = new google.maps.Data()
    layers['intersection'].loadGeoJson(datadir + "intersection.json");
    layers['intersection'].setStyle({icon: markers + "I/0099FF/"})
    layers['intersection'].setMap(all_map)

    layers['elsewhere'] = new google.maps.Data()
    layers['elsewhere'].loadGeoJson(datadir + "elsewhere.json");
    layers['elsewhere'].setStyle({icon: markers + "E/CC33FF"})
    layers['elsewhere'].setMap(all_map)

    // set up event listeners for main map
    var all_info_window = new google.maps.InfoWindow();

    google.maps.event.addListener(all_map, 'click', function() {
      all_info_window.close();
    });

    for (var ctype in layers) {
        layers[ctype].addListener('click', function(event) {
            all_info_window.setContent(event.feature.getProperty('case_no'));
            all_info_window.setPosition(event.latLng);
            all_info_window.setOptions(
                {pixelOffset: new google.maps.Size(0,-34)});
            all_info_window.open(all_map);
        });
    }

    // LB716 map

    var lb716_map = new google.maps.Map(
        document.getElementById('lb716-map-canvas'), {
            zoom: 12,
            center: {lat: 40.807, lng: -96.69}
    });

    lb716_collisions = new google.maps.Data();
    lb716_collisions.loadGeoJson(datadir + "lb716.geojson");
    lb716_collisions.setMap(lb716_map);

    bike_paths = new google.maps.Data();
    bike_paths.loadGeoJson(bike_paths_data);
    bike_paths.setStyle({strokeWeight: 1});
    bike_paths.setMap(lb716_map);

    // set up event listener for LB716 map
    var lb716_info_window = new google.maps.InfoWindow();

    google.maps.event.addListener(lb716_map, 'click', function() {
      lb716_info_window.close();
    });

    lb716_collisions.addListener('click', function(event) {
        lb716_info_window.setContent(event.feature.getProperty('case_no'));
        lb716_info_window.setPosition(event.latLng);
        lb716_info_window.setOptions(
            {pixelOffset: new google.maps.Size(0,-34)});
        lb716_info_window.open(lb716_map);
    });
}

$(document).ready(function(){
    google.maps.event.addDomListener(window, 'load', init_maps);

    $('#toc').toc();

    $('button.map-buttons').click(function(){
	var layer_name = $(this).attr('map-layer');

	$(this).toggleClass('current');
        layers[layer_name].setMap($(this).hasClass('current') ? all_map : null)
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
