Reveal.addEventListener('slidechanged', function(event) {
    var slide=$('#' + event.currentSlide.id);
    slide.find("div.ct-chart").each(function(idx) {
        drawGraph($(this).attr('id'));
    });
});
