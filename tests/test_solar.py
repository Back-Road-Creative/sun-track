"""Solar elevation maths, checked against astronomy rather than against itself.

Pinning numbers this module produced would only prove it has not changed. So
the reference cases here are physical facts that hold independently of any
implementation:

* At the moment the sun is highest (local solar noon), its elevation is
  ``90 - |latitude - declination|``, and the declination at the solstices is
  the obliquity of the ecliptic, 23.44 degrees.
* Solar noon at longitude 0 falls at 12:00 UTC offset by the equation of
  time, whose well-known extremes are about -14 minutes in mid-February and
  about +16 minutes in early November, crossing zero in mid-April, mid-June,
  early September and late December.
* Solar noon moves four minutes later per degree of longitude westward.
* Above the Arctic Circle the sun never sets at the June solstice and never
  rises at the December one.

Each test finds solar noon by scanning the day a minute at a time, so it
depends on no internal detail of the module. Coordinates are round numbers
chosen only to exercise both hemispheres and a range of latitudes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from sun_track.solar import (
    GOLDEN_ELEVATION_MAX,
    GOLDEN_ELEVATION_MIN,
    _refraction_correction_deg,
    is_golden_at,
    is_golden_elevation,
    solar_elevation_deg,
)

UTC = timezone.utc

# Obliquity of the ecliptic: the sun's declination at the solstices.
SOLSTICE_DECLINATION_DEG = 23.44

# Two tolerances, for two different reasons.
#
# On a solstice the declination is at a turning point, so it is 23.44 degrees
# to within a rounding error whatever hour of that date you evaluate it: the
# reference is exact and the check can be tight.
#
# On an equinox the declination is moving at its fastest, about 0.4 degrees a
# day, and the equinox instant is generally several hours away from local solar
# noon on the nominal date. "Declination is zero" is therefore only good to a
# few tenths, and that slack is in the reference, not in the code.
SOLSTICE_TOLERANCE_DEG = 0.1
EQUINOX_TOLERANCE_DEG = 0.6


def _elevation_curve(lat: float, lon: float, date: datetime) -> list[float]:
    """Apparent elevation at every UTC minute of ``date``."""
    midnight = date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)
    return [solar_elevation_deg(lat, lon, midnight + timedelta(minutes=m)) for m in range(24 * 60)]


def _solar_noon(lat: float, lon: float, date: datetime) -> tuple[float, float]:
    """``(highest apparent elevation, minute of the UTC day it occurs)``.

    A minute-resolution scan, then a one-second refinement around the winner.
    The refinement matters near the zenith: there the elevation curve has a
    sharp peak (it goes as the square root of the time offset, because the
    inverse cosine is vertical at 1), so a minute grid alone can miss the true
    maximum by a few tenths of a degree — enough to swamp what the test is
    trying to measure.
    """
    curve = _elevation_curve(lat, lon, date)
    best_minute = max(range(len(curve)), key=curve.__getitem__)
    midnight = date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)

    def at_second(second: int) -> float:
        return solar_elevation_deg(lat, lon, midnight + timedelta(seconds=second))

    window = range(max(0, best_minute * 60 - 60), min(86400, best_minute * 60 + 61))
    best_second = max(window, key=at_second)
    return at_second(best_second), best_second / 60


SOLSTICE_NOON_CASES = [
    pytest.param(0.0, datetime(2026, 6, 21), SOLSTICE_DECLINATION_DEG, id="equator-jun"),
    pytest.param(0.0, datetime(2026, 12, 21), -SOLSTICE_DECLINATION_DEG, id="equator-dec"),
    pytest.param(35.0, datetime(2026, 6, 21), SOLSTICE_DECLINATION_DEG, id="north35-jun"),
    pytest.param(35.0, datetime(2026, 12, 21), -SOLSTICE_DECLINATION_DEG, id="north35-dec"),
    pytest.param(53.0, datetime(2026, 6, 21), SOLSTICE_DECLINATION_DEG, id="north53-jun"),
    pytest.param(66.5, datetime(2026, 6, 21), SOLSTICE_DECLINATION_DEG, id="arctic-jun"),
    pytest.param(-35.0, datetime(2026, 12, 21), -SOLSTICE_DECLINATION_DEG, id="south35-dec"),
    pytest.param(-35.0, datetime(2026, 6, 21), SOLSTICE_DECLINATION_DEG, id="south35-jun"),
]

# Latitudes are kept off the sub-solar point on purpose. Elevation is an
# inverse cosine, which is vertical at its argument's maximum, so within a
# degree of the zenith a hair of error in the declination becomes several
# tenths of a degree of elevation. That is arithmetic, not a defect, but it
# makes a straight-overhead sun a badly conditioned thing to assert on.
EQUINOX_NOON_CASES = [
    pytest.param(10.0, datetime(2026, 3, 20), id="north10-march"),
    pytest.param(53.0, datetime(2026, 9, 23), id="north53-september"),
    pytest.param(-40.0, datetime(2026, 3, 20), id="south40-march"),
]


@pytest.mark.parametrize("lat, date, declination", SOLSTICE_NOON_CASES)
def test_solstice_noon_elevation_matches_declination_geometry(
    lat: float, date: datetime, declination: float
) -> None:
    """Peak elevation of the day == 90 - |latitude - declination|."""
    expected = 90.0 - abs(lat - declination)
    peak, _ = _solar_noon(lat, 0.0, date)
    assert peak == pytest.approx(expected, abs=SOLSTICE_TOLERANCE_DEG)


@pytest.mark.parametrize("lat, date", EQUINOX_NOON_CASES)
def test_equinox_noon_elevation_is_ninety_minus_latitude(lat: float, date: datetime) -> None:
    """With the declination at zero, the identity collapses to 90 - |latitude|."""
    peak, _ = _solar_noon(lat, 0.0, date)
    assert peak == pytest.approx(90.0 - abs(lat), abs=EQUINOX_TOLERANCE_DEG)


def test_the_documented_leap_cycle_limitation_still_holds() -> None:
    """Characterization test for the accuracy limit the docs promise.

    The position terms are fits in day-of-year, so the same calendar date in
    two non-leap years produces the identical answer, and a leap year differs.
    The real sun does not behave that way, which is exactly why the docstring
    quotes tenths of a degree near the equinoxes rather than hundredths.

    This test exists to keep the documentation honest. If someone upgrades the
    algorithm to something that tracks the leap cycle, this test SHOULD fail —
    delete it and tighten the accuracy claims in the module docstring, the
    README and the equinox tolerance above.
    """

    def at(year: int) -> float:
        return solar_elevation_deg(10.0, 0.0, datetime(year, 3, 20, 12, 0, tzinfo=UTC))

    assert at(2025) == at(2026) == at(2027)
    assert at(2028) != at(2027)
    # The size of the leap-year step is the size of the error being documented:
    # a few tenths of a degree near the equinox, not a few hundredths.
    assert 0.1 < abs(at(2028) - at(2027)) < 0.6


@pytest.mark.parametrize(
    "date, equation_of_time_min",
    [
        pytest.param(datetime(2026, 2, 11), -14.2, id="feb-minimum"),
        pytest.param(datetime(2026, 4, 15), 0.0, id="april-zero"),
        pytest.param(datetime(2026, 6, 13), 0.0, id="june-zero"),
        pytest.param(datetime(2026, 9, 1), 0.0, id="september-zero"),
        pytest.param(datetime(2026, 11, 3), 16.4, id="november-maximum"),
    ],
)
def test_solar_noon_time_matches_equation_of_time(
    date: datetime, equation_of_time_min: float
) -> None:
    """At longitude 0 the sun peaks at 12:00 UTC minus the equation of time.

    This is the analemma: the sun transits up to a quarter of an hour either
    side of clock noon over the year. Getting the sign or the scale of that
    term wrong shifts every answer by tens of minutes of hour angle, which no
    elevation-magnitude check would notice.
    """
    _, minute = _solar_noon(20.0, 0.0, date)
    assert minute == pytest.approx(12 * 60 - equation_of_time_min, abs=2)


def test_longitude_shifts_solar_noon_four_minutes_per_degree() -> None:
    """75 degrees west puts solar noon five hours later in UTC."""
    date = datetime(2026, 4, 15)
    _, at_greenwich = _solar_noon(20.0, 0.0, date)
    _, at_75_west = _solar_noon(20.0, -75.0, date)
    assert at_75_west - at_greenwich == pytest.approx(75 * 4, abs=1)


def test_midnight_sun_and_polar_night_above_the_arctic_circle() -> None:
    """At 80N the sun never sets in June and never rises in December."""
    june = _elevation_curve(80.0, 0.0, datetime(2026, 6, 21))
    december = _elevation_curve(80.0, 0.0, datetime(2026, 12, 21))
    assert min(june) > 0.0
    assert max(december) < 0.0


def test_elevation_is_symmetric_about_solar_noon() -> None:
    """Three hours before noon and three hours after are the same height."""
    date = datetime(2026, 4, 15)
    _, minute = _solar_noon(40.0, 0.0, date)
    noon = date.replace(tzinfo=UTC) + timedelta(minutes=minute)
    before = solar_elevation_deg(40.0, 0.0, noon - timedelta(hours=3))
    after = solar_elevation_deg(40.0, 0.0, noon + timedelta(hours=3))
    assert before == pytest.approx(after, abs=0.3)


def test_elevation_stays_within_physical_bounds() -> None:
    """No coordinate or instant may drive the result outside [-90, 90]."""
    date = datetime(2026, 8, 5, 13, 47, tzinfo=UTC)
    for lat in (-90.0, -66.5, -23.44, 0.0, 23.44, 66.5, 90.0):
        for lon in (-180.0, -75.0, 0.0, 75.0, 180.0):
            assert -90.0 <= solar_elevation_deg(lat, lon, date) <= 90.0


def test_refraction_lifts_the_sun_and_never_lowers_it() -> None:
    """Refraction is ~0.5 degrees at the horizon, positive below 85, zero above."""
    assert _refraction_correction_deg(0.0) == pytest.approx(0.48, abs=0.02)
    assert _refraction_correction_deg(90.0) == 0.0
    assert _refraction_correction_deg(86.0) == 0.0
    for elevation in (-20.0, -5.0, -0.6, -0.5, 0.0, 4.0, 5.5, 30.0, 84.0):
        assert _refraction_correction_deg(elevation) > 0.0


@pytest.mark.parametrize("boundary", [85.0, 5.0, -0.575])
def test_refraction_is_continuous_across_its_piecewise_boundaries(boundary: float) -> None:
    """The three-branch formula must not step at the joins."""
    below = _refraction_correction_deg(boundary - 1e-6)
    above = _refraction_correction_deg(boundary + 1e-6)
    assert below == pytest.approx(above, abs=0.02)


def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        solar_elevation_deg(40.0, -100.0, datetime(2026, 6, 21, 16, 0))


def test_non_utc_tzinfo_is_normalized() -> None:
    """An aware non-UTC datetime names the same instant, so it gets the same answer."""
    utc = datetime(2026, 6, 21, 16, 0, tzinfo=UTC)
    elsewhere = utc.astimezone(timezone(timedelta(hours=-7)))
    assert solar_elevation_deg(40.0, -100.0, elsewhere) == pytest.approx(
        solar_elevation_deg(40.0, -100.0, utc), abs=1e-9
    )


def test_noon_higher_than_four_hours_later() -> None:
    """Sanity property: solar noon beats mid-afternoon, same place and day."""
    _, minute = _solar_noon(35.0, -80.0, datetime(2026, 7, 22))
    noon = datetime(2026, 7, 22, tzinfo=UTC) + timedelta(minutes=minute)
    assert solar_elevation_deg(35.0, -80.0, noon) > solar_elevation_deg(
        35.0, -80.0, noon + timedelta(hours=4)
    )


def test_golden_band_constants() -> None:
    assert GOLDEN_ELEVATION_MIN == -4.0
    assert GOLDEN_ELEVATION_MAX == 6.0


@pytest.mark.parametrize(
    "elevation, expected",
    [
        (-4.0, True),  # lower edge inclusive
        (6.0, True),  # upper edge inclusive
        (0.0, True),
        (-4.001, False),
        (6.001, False),
        (41.3, False),
        (-18.0, False),
    ],
)
def test_is_golden_elevation(elevation: float, expected: bool) -> None:
    assert is_golden_elevation(elevation) is expected


def test_the_seasonal_drift_quoted_in_the_docs_is_real() -> None:
    """Keep the worked example in the module docstring and README honest.

    Unlike the reference tests above, this one deliberately pins values this
    library produced — its job is not to check the physics but to check that
    the numbers printed in the documentation still match the code. If it
    fails, fix the docs in the same change.

    The quoted band is 55 degrees north **at longitude 0**, in UTC. The
    longitude is load-bearing and both docs say so: solar time moves four
    minutes per degree, so the same latitude at 8 degrees west gives
    08:21-09:54, not 07:49-09:22. The figures are also stable across years,
    leap or not, because the position terms are fits in day-of-year.
    """

    def morning_band(month: int, day: int) -> tuple[int, int]:
        """First and last UTC minute of the morning golden band at 55N, 0E."""
        midnight = datetime(2026, month, day, tzinfo=UTC)
        minutes = [
            m for m in range(12 * 60) if is_golden_at(55.0, 0.0, midnight + timedelta(minutes=m))
        ]
        # The docs describe one unbroken morning band, so assert it is one.
        assert minutes == list(range(minutes[0], minutes[-1] + 1))
        return minutes[0], minutes[-1]

    def clock(minute: int) -> str:
        return f"{minute // 60:02d}:{minute % 60:02d}"

    january, june = morning_band(1, 15), morning_band(6, 21)
    assert (clock(january[0]), clock(january[1])) == ("07:49", "09:22")
    assert (clock(june[0]), clock(june[1])) == ("02:46", "04:20")

    # Everything else the docs assert about these two bands is derived from
    # them, so derive it here rather than trusting the prose.
    # "about an hour and a half wide in both cases"
    for start, end in (january, june):
        assert 85 <= end - start + 1 <= 100
    # "the same band, five hours earlier"
    assert 4.5 * 60 <= january[0] - june[0] <= 5.5 * 60
    # "a fixed 07:00-08:00 rule overlaps January by some eleven minutes"
    overlap_min = min(january[1], 8 * 60) - max(january[0], 7 * 60)
    assert overlap_min == 11
    # "...and misses June entirely, by more than two and a half hours"
    assert june[1] < 7 * 60
    assert 7 * 60 - june[1] > 150


def test_golden_band_brackets_the_daily_elevation_curve() -> None:
    """The band picks out a contiguous run near dusk, not scattered minutes."""
    curve = _elevation_curve(40.0, 0.0, datetime(2026, 4, 15))
    evening = [m for m in range(12 * 60, 24 * 60) if is_golden_elevation(curve[m])]
    assert evening, "expected a golden window on the evening side"
    assert evening == list(range(evening[0], evening[-1] + 1))
    # A ten-degree band crossed at roughly a quarter-degree a minute is well
    # under two hours at this latitude, and never the whole afternoon.
    assert 10 <= len(evening) <= 120


def test_is_golden_at_composes_the_two_calls() -> None:
    """The convenience wrapper must agree with doing it by hand, both ways."""
    dusk = datetime(2026, 4, 15, 18, 40, tzinfo=UTC)
    midday = datetime(2026, 4, 15, 12, 0, tzinfo=UTC)
    for when in (dusk, midday):
        assert is_golden_at(40.0, 0.0, when) is is_golden_elevation(
            solar_elevation_deg(40.0, 0.0, when)
        )
    assert is_golden_at(40.0, 0.0, dusk) is True
    assert is_golden_at(40.0, 0.0, midday) is False
