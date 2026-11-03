"""All-22 Play Viewer data pipeline.

Turns NFL Big Data Bowl tracking files plus nflverse labels into one small
binary file per play (see docs/play-format.md) and a SQLite catalog that the
iPhone app bundles. Every play is checked before it ships; see checks.py.
"""

__version__ = "0.1.0"
