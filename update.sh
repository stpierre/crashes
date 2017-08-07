#!/bin/bash -ex
#
# Update the downloaded and curated data

if [[ ! -e crashes.sqlite ]]; then
    crashes database restore
fi

crashes -v fetch --autostart

echo "Parsing new PDFs"
crashes -v parse

if [ -t 1 ]; then
    # stdout is a tty, so we can curate what we downloaded
    crashes curate
    crashes geocode

    # only generate results if we could do everything else, too
    crashes xform
    crashes results
    crashes csvify
fi

crashes database dump
