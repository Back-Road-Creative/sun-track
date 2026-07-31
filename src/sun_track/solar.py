"""Apparent solar elevation, and the golden-hour band defined over it.

A fixed wall-clock "golden hour" is the wrong test, and it gets more wrong
the further you go from the equator. At 55 degrees north on the Greenwich
meridian the band below runs 07:49-09:22 UTC on 15 January and 02:46-04:20
UTC on 21 June — five hours of seasonal drift, on top of four minutes more
for every degree of longitude you move. A window pinned to the clock is out
by hours for half the year. (Those figures are this module's own output;
``tests/test_solar.py`` recomputes them, so they fail rather than rot.) The
physically correct test is the sun's *elevation*, which needs only a position
and a UTC instant.

This module is that calculation and nothing else: the NOAA solar-position
algorithm (fractional year -> equation of time + declination -> true solar
time from longitude -> hour angle -> elevation), plus the standard
atmospheric-refraction correction, so the result is the *apparent* elevation
an observer actually sees rather than the geometric one. Deterministic,
standard-library :mod:`math` only, no I/O and no network — callers bring
their own coordinates and UTC anchor (from a GPS fix and an EXIF timestamp,
for instance).

Accuracy, honestly. The declination and equation-of-time terms are Fourier
fits in day-of-year, not a full ephemeris. Their argument is the day number
and nothing else, so the answer for a given calendar date is identical in
every non-leap year, while the sun's true position on that date shifts by
about a quarter of a day per year within the leap cycle. Near the solstices
that costs nothing, because the declination is at a turning point: the error
there is a few hundredths of a degree. Near the equinoxes, where declination
moves some 0.4 degrees a day, the same phase slip becomes a few tenths of a
degree. The equation of time stays inside a minute all year.

Call it half a degree of apparent elevation, worst case. That is twenty times
tighter than the ten-degree band this module gates, and nowhere near enough
for pointing a telescope. If you need arc-seconds, use an ephemeris library.

The golden band lives here and only here: :data:`GOLDEN_ELEVATION_MIN` /
:data:`GOLDEN_ELEVATION_MAX` (degrees, inclusive) with
:func:`is_golden_elevation` as the band test. Import those names rather than
restating the numbers.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

__all__ = [
    "GOLDEN_ELEVATION_MAX",
    "GOLDEN_ELEVATION_MIN",
    "is_golden_at",
    "is_golden_elevation",
    "solar_elevation_deg",
]

# The golden band, in degrees of apparent solar elevation, both edges
# inclusive. Roughly civil-twilight-to-low-sun: -4 reaches into the warm
# afterglow just past sunset, +6 is about where the light stops reading as
# noticeably golden. These are a photographic judgement, not a physical
# constant — widen or narrow them for your own taste, but do it here.
GOLDEN_ELEVATION_MIN = -4.0
GOLDEN_ELEVATION_MAX = 6.0


def solar_elevation_deg(lat: float, lon: float, utc: datetime) -> float:
    """Apparent solar elevation in degrees at (``lat``, ``lon``) at ``utc``.

    ``lat`` is degrees north (negative south), ``lon`` degrees east (negative
    west). ``utc`` must be timezone-aware; any aware value is normalized to
    UTC, since it names the same instant either way.

    A naive datetime raises :class:`ValueError`. Guessing a zone is the one
    error that dwarfs every other term here: a camera's wall-clock time read
    as UTC can be hours off, and an hour of hour-angle is 10-18 degrees of
    elevation at typical latitudes. Resolving the offset is the caller's
    contract, not this function's guess.

    Negative return values mean the sun is below the horizon.
    """
    if utc.tzinfo is None or utc.tzinfo.utcoffset(utc) is None:
        raise ValueError(
            "solar_elevation_deg requires a tz-aware UTC datetime; "
            "resolve wall-clock time to UTC before calling"
        )
    utc = utc.astimezone(timezone.utc)

    # Fractional year (radians), from day-of-year and fractional hour.
    year = utc.year
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    frac_hour = utc.hour + utc.minute / 60 + utc.second / 3600
    gamma = (
        2 * math.pi / (366 if leap else 365) * (utc.timetuple().tm_yday - 1 + (frac_hour - 12) / 24)
    )

    # Equation of time (minutes) and solar declination (radians).
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )

    # True solar time (minutes): the input is UTC, so the timezone term is
    # zero and longitude alone (4 minutes per degree) shifts clock time to
    # solar time.
    true_solar_min = frac_hour * 60 + eqtime + 4 * lon
    hour_angle = math.radians(true_solar_min / 4 - 180)

    lat_rad = math.radians(lat)
    cos_zenith = math.sin(lat_rad) * math.sin(decl) + math.cos(lat_rad) * math.cos(decl) * math.cos(
        hour_angle
    )
    # Clamp against float drift at the poles / solar noon before acos.
    cos_zenith = max(-1.0, min(1.0, cos_zenith))
    elevation = 90.0 - math.degrees(math.acos(cos_zenith))

    return elevation + _refraction_correction_deg(elevation)


def _refraction_correction_deg(elevation_deg: float) -> float:
    """NOAA atmospheric-refraction correction (degrees) for a true elevation.

    The atmosphere bends light so the sun *appears* higher than geometry puts
    it — about half a degree at the horizon (roughly its own diameter, which
    is why the sun you see at sunset has geometrically already set), fading
    to nothing overhead. Piecewise per the NOAA solar calculator: zero above
    85 degrees, a tangent series for normal elevations, a polynomial across
    the horizon, a small tail below it.
    """
    if elevation_deg > 85.0:
        return 0.0
    if elevation_deg > 5.0:
        tan_e = math.tan(math.radians(elevation_deg))
        return (58.1 / tan_e - 0.07 / tan_e**3 + 0.000086 / tan_e**5) / 3600
    if elevation_deg > -0.575:
        e = elevation_deg
        return (1735 + e * (-518.2 + e * (103.4 + e * (-12.79 + e * 0.711)))) / 3600
    return (-20.772 / math.tan(math.radians(elevation_deg))) / 3600


def is_golden_elevation(elevation_deg: float) -> bool:
    """True when ``elevation_deg`` sits inside the golden band, edges inclusive."""
    return GOLDEN_ELEVATION_MIN <= elevation_deg <= GOLDEN_ELEVATION_MAX


def is_golden_at(lat: float, lon: float, utc: datetime) -> bool:
    """Whether the light at (``lat``, ``lon``) at ``utc`` is in the golden band.

    Convenience for the common composition of the two calls above; identical to
    ``is_golden_elevation(solar_elevation_deg(lat, lon, utc))``.
    """
    return is_golden_elevation(solar_elevation_deg(lat, lon, utc))
