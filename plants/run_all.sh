#!/bin/sh
# Every plant under this folder through ct_hold on the real stdio server (cartouche selftest runs this too).
# honest/* must seal; counterfeit/* must be refused or reported with the faults their expect.json names.
# Prints one line per plant and ends with "plants: N PASS / M FAIL". Exit 1 if any plant fails.
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd -P)"
PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}" exec "${PYTHON:-python3}" -m cartouche.selftest --plants "$HERE/plants"
