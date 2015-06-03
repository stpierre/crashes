#!/bin/bash -ex
#
# Update the results.

git checkout master

# determine when we last ran
start=$(python -c 'import datetime,json;print(max(datetime.datetime.strptime(r["date"], "%Y-%m-%d") for r in json.load(open("data/reports.json")).values() if r["date"]).strftime("%Y-%m-%d"))')

echo "Starting fetch from $start"
crashes -v fetch --start "$start"

echo "JSONifying new data"
crashes jsonify --processes 2

if [ -t 1 ]; then
    # stdout is a tty, so we can curate what we downloaded
    crashes curate
fi

if ! git diff --quiet; then
    git commit -a -m "Data updated by update.sh"
    git push
else
    echo "No new data to commit"
fi

git checkout gh-pages
git rebase master

echo "Generating graphs and results"
crashes graph
crashes results

if ! git diff --exit-code; then
    git commit -a -m "Results updated by update.sh"
    git push origin -f gh-pages
else
    echo "No new results to commit"
fi
