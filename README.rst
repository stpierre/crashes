===========================
 Bike Crash Data Analytics
===========================

This repository contains a set of Python modules that process and
analyze public accident report data from the Lincoln (Nebraska) Police
Department in order to gather statistics about crashes that involve a
bicycle.

This README documents the code. The results of the data can be found
at `<http://github.io/stpierre/crashes/>`_.

The CLI is divided into five subcommands that should be run in order:

* ``fetch`` downloads the raw PDF accident reports from LPD;
* ``jsonify`` extracts key data from the PDFs and generates a single
  (large) JSON document containing those data;
* ``curate`` assists in manually categorizing all of the
  potentially-relevant accident reports;
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
* ``report``: The full text of the accident description.
* ``cyclist_injured``: Whether or not the cyclist was injured in the
  crash.

Additional data can be added, but all PDFs must be completely
reparsed, which takes for-freaking-ever.

As it turns out, PDFs in general and the accident report PDFs
specifically are an appalling disaster, so this parsing is decidedly
crufty. RTFS at your peril.

``jsonify`` takes two (optional) arguments:

* ``--processes`` can be used to specify the number of processes to
  spawn, in case you don't want to melt your CPU.
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
  riding on the road.
* ``elsewhere`` (**E**): Crash happened elsewhere. This also includes
  crashes that happened on the road, but where the cyclist was not
  riding on the road as such. (E.g., the cyclist was crossing the
  street away from a crosswalk.)
* ``not_involved`` (**N**): Bicycle was not involved in the crash. A
  cyclist may have been a witness, or a bike rack damaged, etc.

``graph``
=========

Produce pretty pictures of the data. Three graphs are drawn:

* ``monthly.png``: A histogram of crashes per month.
* ``injury_rates.png``: A histogram of the injury rates of each of the
  four accident types.
* ``proportions.png``: A pie chart of the relative proportions of the
  four accident types.

``results``
===========

Render a template that includes an explanation of the results in long
form.

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
| ``fetch`` | ``days``             | Days of accident report data to download     | 365                                          |
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
| ``files`` | ``imagedir``         | Directory, relative to ``datadir``, where    | ``images``                                   |
|           |                      | graph images will be stored.                 |                                              |
+-----------+----------------------+----------------------------------------------+----------------------------------------------+
| ``files`` | ``templates``        | Directory where result templates are stored. | ``./templates``                              |
+-----------+----------------------+----------------------------------------------+----------------------------------------------+
| ``files`` | ``content``          | Directory where Pelican input content is     | ``./content``                                |
|           |                      | stored.                                      |                                              |
+-----------+----------------------+----------------------------------------------+----------------------------------------------+
