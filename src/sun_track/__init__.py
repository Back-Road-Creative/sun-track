"""sun-track: apparent solar elevation, a golden-hour band, and GPX position lookup.

Two independent, dependency-free pieces that happen to compose well:

* :mod:`sun_track.solar` — where the sun is (NOAA solar-position maths with
  atmospheric refraction), and whether that counts as golden light.
* :mod:`sun_track.gpx` — where *you* were, by interpolating a GPX track log at
  a timestamp.

Compose them to answer "was this photo taken in golden light?" for a photo
that carries a capture time but no GPS::

    from sun_track import is_golden_at, load_track_index

    index = load_track_index(Path("~/tracks").expanduser())
    position = index.position_at(capture_utc)
    golden = position is not None and is_golden_at(*position, capture_utc)

Either half works on its own; neither imports the other.
"""

from sun_track.gpx import (
    DEFAULT_MAX_GAP_MIN,
    TrackFix,
    TrackIndex,
    load_track_index,
    parse_gpx_time,
)
from sun_track.solar import (
    GOLDEN_ELEVATION_MAX,
    GOLDEN_ELEVATION_MIN,
    is_golden_at,
    is_golden_elevation,
    solar_elevation_deg,
)

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_MAX_GAP_MIN",
    "GOLDEN_ELEVATION_MAX",
    "GOLDEN_ELEVATION_MIN",
    "TrackFix",
    "TrackIndex",
    "__version__",
    "is_golden_at",
    "is_golden_elevation",
    "load_track_index",
    "parse_gpx_time",
    "solar_elevation_deg",
]
