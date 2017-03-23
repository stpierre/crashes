$(document).ready(function(){
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

    drawAllGraphs();

    google.maps.event.addDomListener(window, 'load', init_maps);
});
