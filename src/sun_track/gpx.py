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
bracketing track points (longitude along the shorter arc, so a track that
crosses the 180th meridian stays on it) and accepted whenever the nearer of
them is within ``max_gap_min`` minutes; tighten that argument when you need a
real fix rather than a plausible one. Where the position is published as
evidence of where the camera was, pass ``strict=True``: the window then bounds
the span between the two bracketing points instead, so a capture inside a long
hole in the track is refused however close it sits to one end.
:meth:`TrackIndex.fix_at` returns the same position with an ``inferred`` flag.

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

__all__ = [
    "DEFAULT_MAX_GAP_MIN",
    "TrackFix",
    "TrackIndex",
    "load_track_index",
    "parse_gpx_time",
]

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
class TrackFix:
    """A position from :meth:`TrackIndex.fix_at`.

    ``inferred`` is False only for a position the logger itself recorded at
    exactly the queried instant; interpolated and end-snapped positions are
    estimates and are True.
    """

    lat: float
    lon: float
    inferred: bool


@dataclass(frozen=True)
class TrackIndex:
    """UTC-sorted ``(time, lat, lon)`` points gathered from every readable track."""

    points: tuple[tuple[datetime, float, float], ...] = ()

    def position_at(
        self,
        utc: datetime,
        max_gap_min: float = DEFAULT_MAX_GAP_MIN,
        *,
        strict: bool = False,
    ) -> tuple[float, float] | None:
        """The interpolated ``(lat, lon)`` at ``utc``, or None.

        A thin wrapper over :meth:`fix_at` that drops the ``inferred`` flag;
        see there for the two gap policies. Use :meth:`fix_at` when the caller
        must tell a logged position from an estimated one.
        """
        fix = self.fix_at(utc, max_gap_min, strict=strict)
        return None if fix is None else (fix.lat, fix.lon)

    def fix_at(
        self,
        utc: datetime,
        max_gap_min: float = DEFAULT_MAX_GAP_MIN,
        *,
        strict: bool = False,
    ) -> TrackFix | None:
        """The position at ``utc`` as a :class:`TrackFix`, or None.

        Two gap policies, chosen per call:

        * ``strict=False`` (default, the legacy policy). Between two track
          points: linear interpolation, accepted when the NEARER bracket is
          within ``max_gap_min`` minutes (default :data:`DEFAULT_MAX_GAP_MIN`),
          however wide the hole between them is. Beyond the ends of the track
          it NEVER extrapolates — before the first point or after the last,
          that end point's own position is returned if it is within the gap,
          else None.
        * ``strict=True``. ``max_gap_min`` becomes the largest allowed SPAN
          between the two bracketing points: a capture inside a wider hole is
          refused even when it sits seconds from one end, and a capture before
          the first or after the last point is refused outright. A capture
          landing exactly on a logged point is always accepted. Use it where
          a position is published as evidence of where the camera was.

        ``inferred`` is False only when ``utc`` equals a logged point's
        timestamp, so the position is the logger's own reading; every
        interpolated or end-snapped position is True.

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
        if i < len(self.points) and self.points[i][0] == utc:
            return TrackFix(self.points[i][1], self.points[i][2], inferred=False)
        if i == 0:
            first_t, lat, lon = self.points[0]
            if strict or first_t - utc > max_gap:
                return None
            return TrackFix(lat, lon, inferred=True)
        if i == len(self.points):
            last_t, lat, lon = self.points[-1]
            if strict or utc - last_t > max_gap:
                return None
            return TrackFix(lat, lon, inferred=True)
        t0, lat0, lon0 = self.points[i - 1]
        t1, lat1, lon1 = self.points[i]
        if strict:
            if t1 - t0 > max_gap:
                return None
        elif min(utc - t0, t1 - utc) > max_gap:
            return None
        frac = (utc - t0).total_seconds() / (t1 - t0).total_seconds()
        return TrackFix(
            lat0 + frac * (lat1 - lat0), _interpolate_lon(lon0, lon1, frac), inferred=True
        )


def _interpolate_lon(lon0: float, lon1: float, frac: float) -> float:
    """Longitude ``frac`` of the way from ``lon0`` to ``lon1`` along the shorter arc.

    A step wider than 180 degrees is a date-line crossing, so it is taken the
    other way round (179 -> -179 is 2 degrees east, not 358 west) and the
    result is wrapped back into [-180, 180]. A step that does not cross the
    line is plain linear interpolation, and a result that never leaves the
    range is returned untouched, so endpoints come back exactly as logged.
    """
    delta = lon1 - lon0
    if delta > 180.0:
        delta -= 360.0
    elif delta < -180.0:
        delta += 360.0
    lon = lon0 + frac * delta
    if lon > 180.0:
        lon -= 360.0
    elif lon < -180.0:
        lon += 360.0
    return lon


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
