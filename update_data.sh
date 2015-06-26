#!/bin/bash -ex
#
# Update the downloaded and curated data

# determine when we last ran
start=$(python -c 'import datetime,json;print(max(datetime.datetime.strptime(r["date"], "%Y-%m-%d") for r in json.load(open("data/reports.json")).values() if r["date"]).strftime("%Y-%m-%d"))')

echo "Starting fetch from $start"
crashes -v fetch --start "$start"

echo "JSONifying new data"
crashes jsonify

if [ -t 1 ]; then
    # stdout is a tty, so we can curate what we downloaded
    crashes curate
    crashes geocode
fi
