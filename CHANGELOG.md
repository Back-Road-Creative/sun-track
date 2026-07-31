# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 0.1.0

First release.

### Added

- `sun_track.solar` — apparent solar elevation for a latitude, longitude and UTC
  instant, using the NOAA solar-position algorithm with the standard
  atmospheric-refraction correction. Naive datetimes are rejected rather than
  assumed to be UTC.
- A golden-hour band defined over that elevation: `GOLDEN_ELEVATION_MIN` /
  `GOLDEN_ELEVATION_MAX` (`-4.0` to `6.0` degrees, inclusive), the
  `is_golden_elevation()` predicate, and the `is_golden_at()` convenience that
  composes the two.
- `sun_track.gpx` — `load_track_index()` merges every `*.gpx` directly inside a
  directory into one UTC-sorted `TrackIndex`, and `TrackIndex.position_at()`
  linearly interpolates a position at a capture time. It never extrapolates past
  the ends of a track, and the match window is the per-call `max_gap_min`
  argument (default `DEFAULT_MAX_GAP_MIN`, 90 minutes).
- `parse_gpx_time()` for turning an ISO-8601 timestamp into the aware-UTC form the
  lookup requires.
- A `python -m sun_track` shell with `sun` and `where` subcommands.
- Type hints throughout, with `py.typed` so they reach downstream type checkers.

### Notes

- No runtime dependencies; the standard library only. Nothing in the package opens
  a network connection.
- Accuracy is about half a degree of elevation in the worst case, not arc-seconds:
  the position terms are Fourier fits in day-of-year, which are good to a few
  hundredths of a degree near the solstices and a few tenths near the equinoxes.
  The README's *Limits* section spells this out, and a characterization test in
  `tests/test_solar.py` fails if the underlying approximation is ever replaced, so
  the claim cannot drift out of date silently.
