"""A GPX track log becomes a position index for timestamped captures.

Phones and handheld loggers write standard GPX 1.0/1.1 (``<trkpt lat lon>``
carrying a ``<time>``, inside ``trk``/``trkseg``), often several files per
day. :func:`load_track_index` folds every ``*.gpx`` directly inside one
directory into a single UTC-sorted index, and :meth:`TrackIndex.position_at`
answers "where was the camera at this instant" — so a photo whose file has a
timestamp but no GPS EXIF can still be placed on the map.

Matching is deliberately generous, because the downstream accuracy demand is
usually low. (If you are feeding the position to a solar-elevation
calculation, a kilometre of position error moves the answer by about a
hundredth of a degree.) The position is linearly interpolated between the two
bracketing track points and accepted whenever the nearer of them is within
``max_gap_min`` minutes; tighten that argument when you need a real fix
rather than a plausible one.

Parsing never raises past the :func:`load_track_index` boundary: an unreadable
file is skipped with one warning naming it, and a malformed point is dropped
individually, so a single corrupt track cannot kill a whole batch.
"""

from __future__ import annotations

import logging
from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

__all__ = ["DEFAULT_MAX_GAP_MIN", "TrackIndex", "load_track_index", "parse_gpx_time"]

logger = logging.getLogger(__name__)

# Default for the ``max_gap_min`` argument of :meth:`TrackIndex.position_at`:
# how far, in minutes, a capture time may sit from the nearest track point and
# still be given a position.
#
# 90 suits a logger that keeps running through stops and only drops out in
# tunnels, car parks and dead zones — it interpolates straight across a lunch
# break rather than refusing to place the photos taken during it. That is the
# right trade when a coarse position is far more useful than none, and the
# wrong one when a position must be trustworthy to the metre. Pass your own
# value per call; nothing in this module treats 90 as special.
DEFAULT_MAX_GAP_MIN = 90.0


def parse_gpx_time(text: str) -> datetime | None:
    """ISO-8601 -> aware UTC datetime; None when unparseable.

    GPX times are UTC by specification, so a (nonstandard) offset-less value
    is taken as UTC rather than rejected. Public because callers routinely
    need to put a capture timestamp into the same aware-UTC form that
    :meth:`TrackIndex.position_at` demands, under the same rule.
    """
    try:
        parsed = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class TrackIndex:
    """UTC-sorted ``(time, lat, lon)`` points gathered from every readable track."""

    points: tuple[tuple[datetime, float, float], ...] = ()

    def position_at(
        self, utc: datetime, max_gap_min: float = DEFAULT_MAX_GAP_MIN
    ) -> tuple[float, float] | None:
        """The interpolated ``(lat, lon)`` at ``utc``, or None.

        Between two track points: linear interpolation, accepted when the
        nearer bracket is within ``max_gap_min`` minutes (default
        :data:`DEFAULT_MAX_GAP_MIN`). Beyond the ends of the track it NEVER
        extrapolates — before the first point or after the last, that end
        point's own position is returned if it is within the gap, else None.

        A naive ``utc`` raises :class:`ValueError`: a capture clock of unknown
        zone matched against a UTC track would silently place the photo hours
        of longitude away. A negative ``max_gap_min`` also raises, rather than
        quietly turning every lookup into None.
        """
        if utc.tzinfo is None:
            raise ValueError("position_at() needs an aware UTC datetime, got a naive one")
        if max_gap_min < 0:
            raise ValueError(f"max_gap_min must be >= 0, got {max_gap_min}")
        if not self.points:
            return None
        max_gap = timedelta(minutes=max_gap_min)
        i = bisect_left(self.points, utc, key=lambda p: p[0])
        if i == 0:
            first_t, lat, lon = self.points[0]
            return (lat, lon) if first_t - utc <= max_gap else None
        if i == len(self.points):
            last_t, lat, lon = self.points[-1]
            return (lat, lon) if utc - last_t <= max_gap else None
        t0, lat0, lon0 = self.points[i - 1]
        t1, lat1, lon1 = self.points[i]
        if min(utc - t0, t1 - utc) > max_gap:
            return None
        span = (t1 - t0).total_seconds()
        if span <= 0:  # duplicate timestamps across files
            return (lat0, lon0)
        frac = (utc - t0).total_seconds() / span
        return (lat0 + frac * (lat1 - lat0), lon0 + frac * (lon1 - lon0))


def _points_from_file(path: Path) -> list[tuple[datetime, float, float]]:
    """Every usable trkpt in one file; may raise — the caller contains it."""
    root = ElementTree.parse(path).getroot()
    points: list[tuple[datetime, float, float]] = []
    seen = dropped = 0
    # Local-name matching: GPX files carry an xmlns whose URI is versioned
    # (.../GPX/1/0 vs .../GPX/1/1), so tags arrive as "{uri}trkpt". Never
    # hardcode the namespace.
    for elem in root.iter():
        if elem.tag.rpartition("}")[2] != "trkpt":
            continue
        seen += 1
        time_text = next(
            (child.text for child in elem if child.tag.rpartition("}")[2] == "time"), None
        )
        when = parse_gpx_time(time_text) if time_text else None
        try:
            lat = float(elem.attrib["lat"])
            lon = float(elem.attrib["lon"])
        except (KeyError, ValueError):
            when = None
        if when is None:
            dropped += 1
            continue
        points.append((when, lat, lon))
    if dropped:
        logger.warning(
            "GPX %s: dropped %d of %d trkpt (missing/bad time or lat/lon)", path, dropped, seen
        )
    return points


def load_track_index(gpx_dir: Path) -> TrackIndex:
    """Parse every ``*.gpx`` directly under ``gpx_dir`` into one sorted index.

    Non-recursive by choice — a logger's sync target is normally a flat
    directory, and recursing into it tends to pick up archives of old trips.
    A file that cannot be parsed is skipped with one warning naming it; this
    boundary never raises. A missing or empty directory yields an empty index.
    """
    points: list[tuple[datetime, float, float]] = []
    if gpx_dir.is_dir():
        for path in sorted(gpx_dir.glob("*.gpx")):
            try:
                points.extend(_points_from_file(path))
            except Exception as exc:  # one bad track must never kill a batch
                logger.warning("GPX %s: unparseable, skipped (%s)", path, exc)
    points.sort(key=lambda p: p[0])
    return TrackIndex(tuple(points))
