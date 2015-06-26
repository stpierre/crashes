#!/bin/bash -ex
#
# Update the results.

git rebase master

echo "Generating graphs and results"
crashes graph
crashes results
