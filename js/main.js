var all_map;
var layers = {};
//var datadir = "http://localhost:8000/data/geojson/";
var datadir = "http://stpierre.github.io/crashes/data/geojson/";
var markers = "http://www.googlemapsmarkers.com/v1/";


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
}


$(document).ready(function(){
    google.maps.event.addDomListener(window, 'load', init_maps);

    $('#toc').toc();

    $('button.map-buttons').click(function(){
	var layer_name = $(this).attr('map-layer');

	$(this).toggleClass('current');
        layers[layer_name].setMap($(this).hasClass('current') ? all_map : null)
    });

    $('[data-toggle="tooltip"]').tooltip({
        container: 'body',
        html: true,
        trigger: 'click'
    });
})
