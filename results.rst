======================
 Bike Crash Analytics
======================

:date: {{now.strftime("%Y-%m-%d %H:%M")}}

In February 2015, I was hit by a car while on my bike in a crosswalk,
and was ticketed for failure to yield the right of way. I got
interested in bicycle safety and, as a software engineer by trade, I
decided to download, parse, and quantify as much crash data as
possible from the Lincoln Police Department.

Quantitative Results
====================

The current dataset includes {{report_count}} reports, from
{{first_report.strftime("%B %e, %Y")}} to
{{last_report.strftime("%B %e, %Y")}}. {{unparseable_count}} reports
could not be parsed, largely because they were handwritten. Of the
reports that could be parsed, {{bike_reports}} ({{ '%0.1f' % (100.0 *
bike_reports / report_count) }}%) involved a person on a bicycle.

This number is almost certainly an underestimate, for several reasons:

* Not every accident is reported. Non-injury accidents in particular
  may not be; anecdotally, I was initially advised not to file an
  accident report when I was hit, since my injuries were very minor.
* Some accident reports are not available online.
* Some accident reports, particularly older ones, are handwritten and
  thus were not automatically parseable.
* Accident reports are not written for bicycle-bicycle or
  bicycle-pedestrian crashes.

Location
--------

The majority of crashes involving a bicycle
({{statuses.crosswalk}}/{{bike_reports}}) happened in a crosswalk:

.. image:: {{imagedir}}/proportions.png

Large numbers of crashes also involve people riding in the street, and
people riding in sidewalks. (Most sidewalk accidents involve cars
turning into private drives, but a few featured cars jumping the
curb.) A smattering involves people riding elsewhere, which includes
parking lots, or crossing streets in the middle of blocks (i.e., away
from crosswalks). For the sake of this analysis, I have counted bike
lanes as the road, although I noted only one case of
{{"B2-035865"|report_link("an accident involving a bike lane")}}.

Clearly, crosswalks are far and away the most dangerous place for
cyclists. No matter what other riding patterns are, cyclists almost
certainly spend orders of magnitude more time out of crosswalks, so
more than half the accidents happening in crosswalks is pretty clearly
damning.

Unfortunately clear data on the number of miles ridden on streets as
compared to sidewalks are not available, so it's not possible to
extrapolate from the data shown above to conclude whether it's more
dangerous to ride in the street or on the sidewalk. However, since
riding on the sidewalk forces you to encounter crosswalks,
pragmatically speaking it would seem to be much safer to ride in the
street.

Unsurprisingly, no crashes were reported on off-street bike
paths. (Recall that these data only include car-bike accidents;
bike-bike and bike-pedestrian accidents certainly do occur on the
off-street bike paths.)

The location of crashes varies slightly by the age of the cyclist:

.. image:: {{imagedir}}/location_by_age.png

Again, though, without data on the number of miles ridden in various
scenarios, it's hard to make much sense of these data -- especially
with such variable-sized (and often small) data sets. The 51-to-60 set
seems to be doing something interesting, though.

Timing
------

Predictably, most accidents happen during the summer months:

.. image:: {{imagedir}}/monthly.png

Although this graph appears to show a trend of increasing accidents,
this interpretation should be adopted cautiously, as there are a
number of confounding variables. (Hopefully, it represents an increase
in the number of miles ridden; it almost certainly also represents a
decrease in handwritten accident reports.)

By time of day, commutes are the most dangerous:

.. image:: {{imagedir}}/crash_times.png

It's interesting that the evening commute -- not the presumably darker
morning commute -- is more dangerous.

Injury rates
------------

Interestingly, different locations have different injury rates:

.. image:: {{imagedir}}/injury_rates.png

Non-injury crashes are the most likely crashes to not be reported, so
these rates are hopefully overestimates.

Sidewalks have the highest injury rate, but also the most
non-disabling injuries. Crashes occurring on the road are the least
likely to lead to injuries, but when they do, the injuries are more
likely to be disabling.

Note that these data are based entirely on accident reports, and so do
not take into account cyclists who are hit and later killed; the
"Killed" category only represents cyclists who were dead at the scene.

Overall, while disabling injuries are scary, they represent a fairly
small percentage of crashes:

.. image:: {{imagedir}}/injury_severities.png

That said, it's still worrisome that a cyclist is about as likely to
escape a crash unscathed as to suffer disabling injury.

Injury severity varies only slightly with the age of the cyclist:

.. image:: {{imagedir}}/severity_by_age.png

This graph uses the LPD injury rating scale, where ``1`` is killed and
``5`` is uninjured, so lower numbers are more severe
injuries. Teenagers and early twenty-somethings seem to suffer the
most severe injuries, but even then the average hovers near "Visible
but not disabling." (The other points on the graph that dip below that
line have too few data points to be reliable.)  Unfortunately the age
of uninjured cyclists is rarely included in the accident report, and
never in a fashion that's trivial to parse automatically, so this
graph does not take into account uninjured cyclists.

Predictably, injuries are most common to the extremities, particularly
the lower legs:

.. image:: {{imagedir}}/injury_regions.png

Map
===

The location of each crash is not machine-parseable (or at least not
reliably so), but following is a lovingly hand-crafted map of
crashes. All locations should be considered approximations, and there
are almost certainly mistakes in places.

.. image:: {{imagedir}}/map.png

Some takeaways:

* Some intersections may seem more dangerous solely because they are
  more heavily trafficked, not because they are actually more
  dangerous.
* That said, a few corridors seem particularly dangerous, with Capital
  Parkway/Normal Blvd. leading the pack. The intersections with 27th,
  33rd, and South are all among the most dangerous in the city.
* The 27th street and Vine street corridors put in strong bids for
  second-most dangerous, and unsurprisingly 27th and Vine is a hotbed
  of crosswalk crashes.
* In general, crashes increase towards downtown and diminish as you
  get further out. There are two notable exceptions: The entire length
  of 84th street (with nearly twice as many crosswalk crashes as 70th
  and 56th streets); and Pine Lake near 27th. These two areas have
  something in common: Bike paths adjacent to streets, where cyclists
  must still cross many side streets. Superior street, which also has
  a street-adjacent bike path, has no nearby analogue to compare it
  to, but it has as many crosswalk crashes as Havelock, Adams,
  Fremont, and Holdrege combined.
* A significant number of crosswalk and sidewalk crashes occur in the
  downtown exclusion area. Stop riding on the sidewalks downtown
  already! It's not even safer!
* Road crashes, predictably, are focused downtown. But at least riding
  on the streets is legal.

This map may actually contain actionable information; many of the most
dangerous intersections are at or near bike path underpasses or
overpasses, so you can avoid crossing 27th at Vine, for instance, on
the Mopac Trail.

Qualitative Results
===================

A number of interesting trends revealed themselves in reading through
the reports. Most disturbingly, at least some members of LPD have a
significant misunderstanding of the law, claiming in the
{{"B3-063805"|report_link("accident")}}
{{"B4-050934"|report_link("report")}} that
{{"B4-085278"|report_link("cyclists are required")}} to walk their
bike across intersections, and {{"B4-107448"|report_link("in some
cases")}} specifically noting that they
"{{"B3-104457"|report_link("lectured")}}" the cyclist.

In other (fewer) {{"B3-096911"|report_link("cases")}}, the officer has
a {{"B4-063856"|report_link("correct understanding")}} of the law, and
in some cases {{"B3-042103"|report_link("the driver of the car was
ticketed")}} for {{"B2-062920"|report_link("failure to yield")}} to a
cyclist in a crosswalk.

The law for crossing private drives is less clear, but
{{"B2-106960"|report_link("at least one cop")}} thinks that bikes on
sidewalks must yield to cars in driveways.

Perhaps ironically, in {{"B4-055506"|report_link("one case")}} a
cyclist who had dismounted to walk his bike across the intersection
was hit while on foot.

In some cases, the accident report
{{"B3-046597"|report_link("mentions")}} that the cyclist
{{"B4-032910"|report_link("was not wearing a helmet")}}, despite the
fact that this has absolutely no legal bearing, nor does it have any
bearing on whether or not a cyclist is hit. It's hard to see this as
anything other than editorial victim-blaming.

A {{"B3-049103"|report_link("number")}} of accident reports reverse
the agents, claiming that {{"B4-065578"|report_link("a bike hit a
car")}} in cases where the car clearly hit the bike. In some cases,
it's described {{"B4-034454"|report_link("both ways")}}. It's not
clear why this inversion of causality occurs.

In some cases, bicyclists "{{"B2-019522"|report_link("suddenly
appear")}}". Stop {{"B3-063032"|report_link("apparating")}} in public
or the muggles will catch on!

The only place {{"B2-057557"|report_link("two")}} "elsewhere"
{{"B3-023161"|report_link("crashes")}} occurred is on 27th street,
just south of Highway 2, where there's a cutout of the median to let
train tracks cross 27th street. People are crossing a busy arterial
street with no crosswalk along train tracks -- with a pedestrian
bridge overhead. Please don't be dumb.

{{"B2-072693"|report_link("Please")}}, {{"B4-049988"|report_link("get
information")}} from a {{"B2-072693"|report_link("driver")}} who
{{"B4-090913"|report_link("hits
you")}}. {{"B2-065976"|report_link("Call the police.")}}
{{"B3-047233"|report_link("File a report.")}}

Methodology
===========

Accident reports are downloaded automatically from the `Lincoln Police
Department's website
<https://lincoln.ne.gov/city/police/stats/acc.htm>`_. The reports are
parsed automatically and selected data are extracted. The data are
available at `<{{all_reports}}>`_.

These reports are then curated by hand to determine where the crash
happened, as described above. This depends on the accuracy of the
accident report; anecdotally, several cyclists have reported to me
that their accident reports were not completely accurate. These
inaccuracies are not expected to be significant, but there's no
obvious way to test this with the given data set.

Much of the methodology is described in more detail in the `README
<https://github.com/stpierre/crashes/blob/master/README.rst>`_.  All
of the code used to generate this report is free and open source under
the `GPLv2
<http://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html>`_.

I have made no effort at all to determine fault, as that process would
be fraught beyond any semblance of reason.

Further Study
=============

There are lots of hit-and-runs, mostly by cars but in some cases by
cyclists, too. (The cyclists who run from a crash seem to generally be
kids.) It'd be nice to gather data on that.

The data may be too few to be statistically significant, but
quantifying the number of crosswalk crashes in areas with
street-adjacent bike paths (as opposed to other areas) could be an
eye-opener.

Charting the time of day of crashes throughout the calendar year might
demonstrate how darkness affects (or doesn't affect) crashes.

Differentiating between on-street crashes in an intersection and away
from an intersection might be edifying.

Links
=====

* `Official Nebraska Department of Roads Crash Data
  <http://www.transportation.nebraska.gov/highway-safety/>`_. Monthly
  and yearly summaries with lots of aggregate crash data, but little
  in the way of bicycyle-specific data.
* `Nebraska Bike Laws <http://www.nebike.org/laws/>`_, courtesy of the
  Nebraska Bicycling Alliance.
* `What to do when you're hit by a car
  <http://www.citylab.com/navigator/2015/05/what-to-do-when-youre-hit-by-a-car/393809/>`_
  (and have the time, money, and presence of mind to handle it the
  best way).
* `What to do if you're hit by a car while riding your bike
  <http://grist.org/living/what-to-do-if-youre-hit-by-a-car-while-riding-your-bike/>`_.
  A little more pragmatic.
