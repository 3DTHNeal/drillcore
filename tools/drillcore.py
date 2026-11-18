#!/usr/bin/env python3
"""Drillcore command line. Run `python3 tools/drillcore.py --help`."""
import sys

# Kept to syntax any Python 3 can read, so an old one gets this message instead of a traceback.
if sys.version_info < (3, 11):  # noqa: UP036
    sys.exit("Drillcore needs Python 3.11 or newer, and this is {}.{}. On Windows, `py -3 tools/drillcore.py ...` runs the "
             "newest one installed, and elsewhere `python3` may be newer.".format(*sys.version_info[:2]))

from drillcore.__main__ import run

if __name__ == "__main__":
    run()
