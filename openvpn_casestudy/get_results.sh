#!/bin/sh

grep -A6 "Aggregated" $* | grep -P ",\d+"
