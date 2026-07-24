# Notice

bvlos-sim's own source code, documentation, and synthetic example data are
licensed under the [MIT License](./LICENSE).

Some files in this repository are **derived from third-party databases that
carry their own licence terms**. MIT does not and cannot relicense them. If you
redistribute this repository, a fork of it, or any output derived from these
files, the obligations below travel with you.

## OpenStreetMap — ODbL 1.0

| File | Retrieved via |
|---|---|
| `examples/real_world/assets/landing_zones.geojson` | Overpass API (`overpass-api.de`) |

Data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors,
available under the
[Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/).

The ODbL is a share-alike licence for the *database*. In practice:

- Credit OpenStreetMap contributors wherever you show or publish the data or a
  work produced from it.
- If you publicly use an adapted version of the database, you must offer that
  adapted database under the ODbL as well.
- A map, report, or verdict produced *from* the data is a Produced Work: it
  needs the attribution, not the share-alike.

The same obligations apply to anything you fetch yourself with
`bvlos-sim/scripts/fetch_landing_zones.py`, `fetch_geofences.py`, or
`fetch_obstacles.py` — all three query Overpass.

## Open-Meteo — CC BY 4.0

| File | Retrieved via |
|---|---|
| `examples/real_world/assets/wind_grid.yaml` | Open-Meteo historical forecast API |

Weather data © [Open-Meteo](https://open-meteo.com/), available under the
[Creative Commons Attribution 4.0 International licence](https://creativecommons.org/licenses/by/4.0/).
Attribution is required when you redistribute the data or a work derived from
it. `bvlos_sim/scripts/fetch_wind.py` queries the same API.

## SRTM — public domain

| File | Retrieved via |
|---|---|
| `examples/real_world/assets/terrain.yaml` | `srtm.py`, from NASA SRTM tiles |

NASA Shuttle Radar Topography Mission elevation data is in the public domain.
No attribution is required, though crediting NASA/USGS is customary.
`bvlos_sim/scripts/fetch_terrain.py` uses the same source.

## Synthetic data

Everything under `data/` and the remaining files under `examples/` is synthetic,
authored for this repository, and covered by the MIT licence. It describes no
real airspace, aerodrome, or terrain, and must never be flown against.
