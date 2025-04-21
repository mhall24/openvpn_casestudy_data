#!/bin/sh

# Filter for the aggregated results from the perf_test.py output.

grep -A6 "Aggregated" $* | grep -P ",\d+"
