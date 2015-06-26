===========================
 Bike Crash Data Analytics
===========================

This repository contains a set of Python modules that process and
analyze public accident report data from the Lincoln (Nebraska) Police
Department in order to gather statistics about crashes that involve a
bicycle.

This README documents the code. The results of the data can be found
at `<http://stpierre.github.io/crashes/>`_.

The CLI is divided into several subcommands that should be run in order:

* ``fetch`` downloads the raw PDF accident reports from LPD;
* ``jsonify`` extracts key data from the PDFs and generates a single
  (large) JSON document containing those data;
* ``curate`` assists in manually categorizing all of the
  potentially-relevant accident reports;
* ``geocode`` assists in manually geocoding (i.e., determining the
  exact location) of curated accident reports;
* ``graph`` generates useful graphs of the curated data;
* ``results`` generates the input data for the explanation of results.

Running any command before its "parent" commands have been run will
automatically invoke the prerequisite commands.

Each command is described in more detail below.

``fetch``
=========

``fetch`` downloads the raw PDF accident reports from LPD. It does so
by searching for reports by date, then screen-scraping the search
results and downloading each report. It sleeps randomly between
requests to avoid a DoS, or even the appearance of a DoS.

PDFs are saved to ``datadir``.

``jsonify``
===========

``jsonify`` extracts data that we care about from the PDFs so that the
data are more usable. It is very computationally expensive, and so
runs multiple processes. (By default, it spawns one process per CPU.)
``jsonify`` extracts four data:

* ``location``: The location of the accident. Often this is just a
  street name, and the accident report must be read to find a specific
  location.
* ``date``: The date of the accident.
* ``time``: The time of the accident
* ``report``: The full text of the accident description.
* ``injury_severity``: The severity of the injury to the cyclist using
  LPD's bespoke 1-5 scale, where 1 is "Killed" and 5 is "No injury."
  5's are rarely (if ever) reported.
* ``injury_region``: Body region of primary injury to the cyclist.
* ``cyclist_dob``: Date of birth of the cyclist.

Additional data can be added and (fairly) easily added to the data set
with the ``--reparse-curated`` flag.

As it turns out, PDFs in general and the accident report PDFs
specifically are an appalling disaster, so this parsing is decidedly
crufty. RTFS at your peril.

``jsonify`` takes a few(optional) arguments:

* ``--processes`` can be used to specify the number of processes to
  spawn, in case you don't want to melt your CPU.
* ``--reparse-curated`` tells ``jsonify`` to only parse those accident
  reports that have already been curated and identified as bike-car
  crashes.
* Any additional arguments are filenames to parse, which will be used
  instead of trying to parse all of the PDFs in the datadir.

If filenames are supplied to ``jsonify``, the results are printed to
stdout instead of added to ``reports.json``. This is mostly useful for
testing changes to the ``jsonify`` code.

``curate``
==========

Once the data have been extracted, we must find crashes that involved
a bicycle. This is, unfortunately, a manual process. ``curate``
iterates over every accident report that includes the word
``bicycle``, ``bike``, ``cyclist``, or ``bicyclist``. Each report is
then manually assigned one of five statuses:

* ``crosswalk`` (**C**): Crash happened while a person on a bicycle
  was using a crosswalk.
* ``sidewalk`` (**S**): Crash happened while a person on a bicycle was
  riding on a sidewalk. For instance, a car entering or leaving a
  private driveway or, in extreme situations, a car that jumps the
  curb.
* ``road`` (**R**): Crash happened while a person on a bicycle was
  riding on the road, excluding intersections.
* ``intersection`` (**I**): Crash happened while a person on a bicycle
  was riding through an intersection on the road, not using a
  crosswalk.
* ``elsewhere`` (**E**): Crash happened elsewhere. This also includes
  crashes that happened on the road, but where the cyclist was not
  riding on the road as such. (E.g., the cyclist was crossing the
  street away from a crosswalk.)
* ``not_involved`` (**N**): Bicycle was not involved in the crash. A
  cyclist may have been a witness, or a bike rack damaged, etc.

``geocode``
===========

After the data has been curated, we want to geocode the bike-related
crashes in order to map them; this command assists with that
semi-manual process. The "Location" field on accident reports is
frequently ambiguous or incomplete, so ``geocode`` iterates over each
bike-related accident and attempts to use the "Location" field as
provided on the report, plus any user input necessary, to look up the
exact location of the accident (using the Google Geocoding API) and
output GeoJSON to be used in mapping.

``graph``
=========

Produce pretty pictures of the data. The following graphs are drawn:

* ``monthly.png``: A histogram of crashes per month.
* ``location_by_age.png``: Plot of crash location by age of cyclist.
* ``severity_by_age.png``: Accident severities by age of cyclist.
* ``ages.png``: Histogram of the distribution of ages of injured
  cyclists.
* ``crash_times.png``: Histogram of what time of day crashes happen.
* ``injury_rates.png``: A histogram of the injury rates of each of the
  four accident types.
* ``injury_severities.png``: Pie chart of proportions of injury
  severities.
* ``injury_regions.png``: Pie chart of the body region with the
  primary injury.
* ``proportions.png``: A pie chart of the relative proportions of the
  four accident types.

``results``
===========

Render a template that includes an explanation of the results in long
form. Currently that template is a Pelican input file, so Pelican must
be run to generate the final site.

Configuration
=============

The following configuration options (in ``crashes.conf``) are
recognized:

+-----------+----------------------+----------------------------------------------+----------------------------------------------+
| Section   | Name                 | Description                                  | Default                                      |
+===========+======================+==============================================+==============================================+
| ``form``  | ``url``              | The POST URL of LPD's accident report search | ``HTTP://CJIS.LINCOLN.NE.GOV/HTBIN/CGI.COM`` |
|           |                      | form.                                        |                                              |
+-----------+----------------------+----------------------------------------------+----------------------------------------------+
| ``form``  | ``token``            | The POST token to include in accident report | ``DISK0:[020020.WWW]ACCDESK.COM``            |
|           |                      | search POSTs.                                |                                              |
+-----------+----------------------+----------------------------------------------+----------------------------------------------+
| ``form``  | ``sleep_min``        | Minimum time, in seconds, to sleep between   | 5                                            |
|           |                      | requests to LPD's website.                   |                                              |
+-----------+----------------------+----------------------------------------------+----------------------------------------------+
| ``form``  | ``sleep_max``        | Maximum time, in seconds, to sleep between   | 30                                           |
|           |                      | requests to LPD's website.                   |                                              |
+-----------+----------------------+----------------------------------------------+----------------------------------------------+
| ``fetch`` | ``days``             | Days of accident report data to download.    | 365                                          |
+-----------+----------------------+----------------------------------------------+----------------------------------------------+
| ``fetch`` | ``start``            | Date (in ``YYYY-MM-DD`` format) from which   | None                                         |
|           |                      | to download crash data. If ``start`` is      |                                              |
|           |                      | given, it takes precedence over ``days``.    |                                              |
+-----------+----------------------+----------------------------------------------+----------------------------------------------+
| ``fetch`` | ``retries``          | Number of times to retry an HTTP request to  | 3                                            |
|           |                      | LPD's website, either for submitting the     |                                              |
|           |                      | search form or for downloading a report.     |                                              |
+-----------+----------------------+----------------------------------------------+----------------------------------------------+
| ``files`` | ``datadir``          | Base directory to use for persistent data    | ``./data``                                   |
|           |                      | storage.                                     |                                              |
+-----------+----------------------+----------------------------------------------+----------------------------------------------+
| ``files`` | ``pdfdir``           | Directory, relative to ``datadir``, where    | ``pdfs``                                     |
|           |                      | accident report PDFs will be stored.         |                                              |
+-----------+----------------------+----------------------------------------------+----------------------------------------------+
| ``files`` | ``all_reports``      | File, relative to ``datadir``, where the     | ``reports.json``                             |
|           |                      | results of the ``jsonify`` command will be   |                                              |
|           |                      | stored.                                      |                                              |
+-----------+----------------------+----------------------------------------------+----------------------------------------------+
| ``files`` | ``curation_results`` | File, relative to ``datadir``, where the     | ``curation.json``                            |
|           |                      | results of the ``curate`` command will be    |                                              |
|           |                      | stored.                                      |                                              |
+-----------+----------------------+----------------------------------------------+----------------------------------------------+
| ``files`` | ``geocoding``        | Directory, relative to ``datadir``, where    | ``geojson``                                  |
|           |                      | output from the ``geocode`` command will be  |                                              |
|           |                      | stored.                                      |                                              |
+-----------+----------------------+----------------------------------------------+----------------------------------------------+
| ``files`` | ``imagedir``         | Directory, relative to ``datadir``, where    | ``images``                                   |
|           |                      | graph images will be stored.                 |                                              |
+-----------+----------------------+----------------------------------------------+----------------------------------------------+
| ``files`` | ``template``         | Jinja2 template for results.                 | ``./results.html``                           |
+-----------+----------------------+----------------------------------------------+----------------------------------------------+
| ``files`` | ``results_output``   | Filename to write results output to.         | ``./index.html``                             |
+-----------+----------------------+----------------------------------------------+----------------------------------------------+
