"""Licence notices for the third-party data the fetch scripts download.

The obligations travel with the data, not with this repository's MIT licence, so
whoever fetches a file has to be told at the moment they acquire it. Printing on
stderr keeps piped GeoJSON/YAML output clean.
"""

from __future__ import annotations

import sys

OPENSTREETMAP = (
    "Data (c) OpenStreetMap contributors, ODbL 1.0 "
    "<https://www.openstreetmap.org/copyright>. Credit OSM wherever you publish "
    "this data or anything derived from it; publishing an adapted database "
    "requires releasing it under the ODbL too."
)

OPEN_METEO = (
    "Weather data (c) Open-Meteo <https://open-meteo.com/>, CC BY 4.0 "
    "<https://creativecommons.org/licenses/by/4.0/>. Attribution is required "
    "when you redistribute this data or a work derived from it."
)

SRTM = (
    "Elevation data from the NASA Shuttle Radar Topography Mission, public "
    "domain. No attribution required; crediting NASA/USGS is customary."
)

WORLDPOP = (
    "Population data (c) WorldPop <https://www.worldpop.org/>, CC BY 4.0 "
    "<https://creativecommons.org/licenses/by/4.0/>. Attribution is required "
    "when you redistribute this data or a work derived from it."
)


def print_attribution(notice: str) -> None:
    """Write a licence notice to stderr, so stdout stays machine-readable."""
    print(f"Attribution: {notice}", file=sys.stderr)


__all__ = [
    "OPENSTREETMAP",
    "OPEN_METEO",
    "SRTM",
    "WORLDPOP",
    "print_attribution",
]
