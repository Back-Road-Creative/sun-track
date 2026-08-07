# sun-track

Where the sun was, and where you were, at a given instant — with no dependencies.

Two small, independent modules:

- **`sun_track.solar`** — apparent solar elevation from a latitude, a longitude and a
  UTC instant (NOAA solar-position algorithm plus atmospheric refraction), and a
  golden-hour test defined over that elevation.
- **`sun_track.gpx`** — a GPX track log becomes a lookup: "where was I at 18:42:07?",
  by linear interpolation between the bracketing track points.

Standard library only. No network calls, ever.

## Why

Two ideas, each of which keeps getting reimplemented badly.

**Golden hour is not a clock reading.** Software that tags photos as "golden hour"
usually tests the wall-clock hour. That is wrong the moment you leave the equator or the
equinox. At 55° north on the Greenwich meridian, the morning band this library computes
runs 07:49–09:22 UTC on 15 January and 02:46–04:20 UTC on 21 June — the same band, five
hours earlier, about an hour and a half wide in both cases. A fixed 07:00–08:00 rule
overlaps the January one by some eleven minutes and misses the June one entirely, by more
than two and a half hours. (Those times are this library's own output for longitude 0;
every degree of longitude east or west shifts them four minutes, and
[`tests/test_solar.py`](tests/test_solar.py) recomputes them on every run so they cannot
quietly go stale.) What actually sets the quality of the light is how high the sun is, and
therefore how much atmosphere it is shining through. That is a number you can compute from
a position and an instant, and then threshold. `solar_elevation_deg()` is that number;
`is_golden_elevation()` is that threshold.

**A photo without GPS is not a photo without a position.** Plenty of cameras write a
timestamp but no coordinates, while a phone in the same pocket logs a GPX track all day.
Joining them is a small interpolation problem that is easy to get subtly wrong —
extrapolating past the end of the track, silently matching a photo to a point six hours
away, or comparing a naive local timestamp against UTC track times and landing a
continent away. `TrackIndex.position_at()` is that join, with those three mistakes made
impossible.

They compose (position from the track, elevation at that position), but neither imports
the other and either is useful alone.

## Install

```bash
pip install git+https://github.com/Back-Road-Creative/sun-track
```

Requires Python 3.11 or newer. There are no runtime dependencies.

## Usage

### Was the sun low?

```python
from datetime import datetime, timezone

from sun_track import is_golden_elevation, solar_elevation_deg

when = datetime(2026, 4, 15, 18, 30, tzinfo=timezone.utc)
elevation = solar_elevation_deg(40.0, -3.7, when)  # degrees above the horizon

print(f"{elevation:.2f}°", "golden" if is_golden_elevation(elevation) else "not golden")
```

Negative elevations mean the sun is below the horizon. The datetime must be
timezone-aware — a naive one raises `ValueError` rather than guessing (see *Limits*).

### Where was the camera?

```python
from datetime import datetime, timezone
from pathlib import Path

from sun_track import load_track_index

index = load_track_index(Path("~/tracks/2026-04-15").expanduser())
position = index.position_at(datetime(2026, 4, 15, 18, 30, tzinfo=timezone.utc))

if position is None:
    print("no track point near that time")
else:
    print("lat %.5f lon %.5f" % position)
```

`load_track_index` reads every `*.gpx` file directly inside the directory (not
recursively) and merges them into one time-sorted index, so a day split across several
log files needs no stitching. A file it cannot parse is skipped with a warning; a
malformed point is dropped on its own. One corrupt track never takes down a batch.

By default a capture is matched to the track when the nearest point is within 90
minutes, which is generous on purpose: for placing a photo on a map, or for feeding a
solar calculation, "somewhere along this road" beats "unknown". Tighten it per call when
you need a real fix:

```python
index.position_at(capture_utc, max_gap_min=5)
```

### Both at once

```python
from sun_track import is_golden_at, load_track_index

index = load_track_index(track_dir)
position = index.position_at(capture_utc)
golden = position is not None and is_golden_at(position[0], position[1], capture_utc)
```

### From the shell

```bash
$ python -m sun_track sun 40.0 -3.7 2026-04-15T18:30:00Z
3.509 golden

$ python -m sun_track where ~/tracks/2026-04-15 2026-04-15T18:30:00Z
40.025000,-3.650000
```

`sun` always exits 0 once its arguments parse. `where` exits 1 and prints `NONE`
when no track point is close enough, so a shell script can branch on it. Both exit
2 when called wrongly.

## API

Everything below is importable straight from `sun_track`.

| Name | What it does |
| --- | --- |
| `solar_elevation_deg(lat, lon, utc) -> float` | Apparent solar elevation in degrees. Negative means below the horizon. Raises `ValueError` on a naive datetime. |
| `is_golden_elevation(elevation_deg) -> bool` | Whether an elevation falls inside the golden band, edges inclusive. |
| `is_golden_at(lat, lon, utc) -> bool` | The two calls above composed, for the common case. |
| `GOLDEN_ELEVATION_MIN` / `GOLDEN_ELEVATION_MAX` | The band edges, `-4.0` and `6.0` degrees. |
| `load_track_index(gpx_dir) -> TrackIndex` | Merge every `*.gpx` directly under a directory into one UTC-sorted index. Never raises. |
| `TrackIndex.position_at(utc, max_gap_min=90.0) -> tuple[float, float] \| None` | Interpolated `(lat, lon)`, or `None` when no track point is close enough. Raises `ValueError` on a naive datetime or a negative gap. |
| `TrackIndex.points` | The raw `(datetime, lat, lon)` tuples, sorted by time. |
| `parse_gpx_time(text) -> datetime \| None` | ISO-8601 to aware UTC, `None` when unparseable. A value with no offset is read as UTC, per the GPX spec. |
| `DEFAULT_MAX_GAP_MIN` | The default match window, `90.0` minutes. |

## Limits

Worth knowing before you rely on this.

- **Elevation only.** No azimuth, no sunrise/sunset/twilight times, no moon, no
  equation-of-time accessor. If you need a full ephemeris, use one.
- **Accuracy is about half a degree, worst case — not arc-seconds.** The solar
  position comes from Fourier fits in day-of-year rather than a full ephemeris, so
  the answer for a given calendar date is the same in every non-leap year, while the
  real sun shifts about a quarter of a day per year within the leap cycle. Near the
  solstices, where the declination is barely moving, that costs a few hundredths of a
  degree. Near the equinoxes, where it moves about 0.4° a day, it costs a few tenths.
  The equation of time stays inside a minute year-round. Fine for a ten-degree
  lighting band; useless for pointing a telescope.
- **Precision degrades close to the zenith.** Elevation comes out of an inverse
  cosine, which is vertical at its limit, so within a degree or so of straight
  overhead a small error in the sun's position becomes a larger error in the
  reported elevation. This only matters in the tropics near local noon, and never
  matters for low-sun work, which is what the library is for.
- **Refraction assumes a standard atmosphere.** Real refraction within a degree or so
  of the horizon varies with temperature and pressure by a few tenths of a degree, and
  can do stranger things over cold water. Near-horizon results are approximate by
  nature, not by implementation.
- **No terrain and no observer altitude.** The horizon is the ideal sea-level one. A
  ridge to the west means the sun goes behind it well before the computed elevation
  reaches zero.
- **The golden band edges are a photographic judgement, not physics.** `-4.0` to `6.0`
  degrees is a defensible default — it reaches into the afterglow just past sunset and
  stops where the light stops reading as warm — but it is a taste setting. Nothing else
  in the library depends on those particular numbers.
- **You must resolve the timezone.** Every entry point demands an aware datetime and
  raises on a naive one. This is the single largest error source in this problem
  domain: a camera's wall-clock time taken for UTC can be hours out, and an hour of
  error is 10–18 degrees of elevation at mid-latitudes — an error many times larger
  than the entire golden band. Guessing here would quietly poison every result, so the
  library refuses to guess.
- **GPX interpolation is a straight line in degrees** between two logged points, not a
  path along a road and not a great circle. Over a 90-minute gap that can be far from
  where you actually went. It is a plausible position, not a fix.
- **Track points need a time.** Only `<trkpt>` elements carrying a `<time>` and valid
  `lat`/`lon` are indexed; waypoints, routes and untimed points are ignored. There is
  no filtering on reported GPS accuracy, and no plausibility check on speed.
- **No extrapolation.** Before the first point or after the last one, you get that end
  point's own position if it is within the window, and `None` otherwise — never a
  projected position.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
.venv/bin/ruff check .
```

The test suite deliberately does not pin numbers this library produced. The solar tests
check it against facts that hold independently of any implementation — that the peak
elevation of the day equals `90 - |latitude - declination|`, that solar noon at
longitude 0 lands at 12:00 UTC offset by the equation of time, that the sun never sets
at 80° north in June — by scanning a whole day a minute at a time. See
[`tests/test_solar.py`](tests/test_solar.py).

## License

MIT — see [LICENSE](LICENSE).
