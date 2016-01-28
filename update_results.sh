#!/bin/bash -ex
#
# Update the results.

git rebase master

echo "Generating graph data and results"
crashes xform
crashes results
