"""GPX track index: log files on disk -> a position at a capture time.

Every track in this file is invented. The coordinates are round numbers over
open country in the middle of nowhere, chosen so the interpolation arithmetic
is checkable by eye (a point halfway in time is halfway in degrees).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sun_track.gpx import DEFAULT_MAX_GAP_MIN, TrackIndex, load_track_index, parse_gpx_time

UTC = timezone.utc

GPX_11_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<gpx version="1.1" creator="example-logger"\n'
    '     xmlns="http://www.topografix.com/GPX/1/1"\n'
    '     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
    "<trk><name>track</name><trkseg>\n"
)
GPX_10_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<gpx version="1.0" creator="example-logger"\n'
    '     xmlns="http://www.topografix.com/GPX/1/0">\n'
    "<trk><name>track</name><trkseg>\n"
)
GPX_FOOTER = "</trkseg></trk></gpx>\n"


def _trkpt(lat: float, lon: float, iso: str) -> str:
    return f'<trkpt lat="{lat}" lon="{lon}"><ele>10.0</ele><time>{iso}</time></trkpt>\n'


def _write_gpx(path: Path, points: str, header: str = GPX_11_HEADER) -> None:
    path.write_text(header + points + GPX_FOOTER)


@pytest.fixture
def two_file_dir(tmp_path: Path) -> Path:
    """Morning + afternoon files, written afternoon-first to prove sorting.

    Morning leg: (40.0, -100.0) at 12:00Z travelling to (40.2, -100.4) at 12:10Z.
    Afternoon leg: (41.0, -99.0) at 16:00Z travelling to (41.2, -99.4) at 16:10Z.
    """
    _write_gpx(
        tmp_path / "a-afternoon.gpx",
        _trkpt(41.0, -99.0, "2026-07-30T16:00:00Z") + _trkpt(41.2, -99.4, "2026-07-30T16:10:00Z"),
    )
    _write_gpx(
        tmp_path / "b-morning.gpx",
        _trkpt(40.0, -100.0, "2026-07-30T12:00:00Z") + _trkpt(40.2, -100.4, "2026-07-30T12:10:00Z"),
    )
    return tmp_path


def test_two_files_merge_into_one_sorted_index(two_file_dir: Path) -> None:
    index = load_track_index(two_file_dir)
    times = [t for t, _, _ in index.points]
    assert len(times) == 4
    assert times == sorted(times)
    assert index.points[0][1:] == (40.0, -100.0)  # morning first despite file order


def test_gpx_10_namespace_parses_the_same(tmp_path: Path) -> None:
    """The namespace URI is versioned; matching is on the local tag name."""
    _write_gpx(
        tmp_path / "old.gpx", _trkpt(40.0, -100.0, "2026-07-30T12:00:00Z"), header=GPX_10_HEADER
    )
    assert load_track_index(tmp_path).points[0][1:] == (40.0, -100.0)


def test_interpolation_at_known_midpoint(two_file_dir: Path) -> None:
    index = load_track_index(two_file_dir)
    pos = index.position_at(datetime(2026, 7, 30, 12, 5, tzinfo=UTC))
    assert pos == pytest.approx((40.1, -100.2))


def test_gap_cutoff_both_sides(two_file_dir: Path) -> None:
    index = load_track_index(two_file_dir)
    # 14:05 is 115 min after the morning leg ends and 115 min before the
    # afternoon leg starts — both brackets beyond the default gap, no position.
    assert DEFAULT_MAX_GAP_MIN == 90.0
    assert index.position_at(datetime(2026, 7, 30, 14, 5, tzinfo=UTC)) is None
    # 13:00 is 50 min after the morning leg ends: the nearer bracket is inside
    # the gap, so the generous match interpolates across the break.
    pos = index.position_at(datetime(2026, 7, 30, 13, 0, tzinfo=UTC))
    assert pos is not None
    assert 40.2 < pos[0] < 41.0


def test_max_gap_min_is_caller_tunable(two_file_dir: Path) -> None:
    index = load_track_index(two_file_dir)
    across_the_break = datetime(2026, 7, 30, 13, 0, tzinfo=UTC)
    far_from_anything = datetime(2026, 7, 30, 14, 5, tzinfo=UTC)
    # Tighter than the default: the 50-minute reach is refused.
    assert index.position_at(across_the_break, max_gap_min=10) is None
    # Wider than the default: even the middle of the break interpolates.
    assert index.position_at(far_from_anything, max_gap_min=240) is not None
    # Zero means exact-or-nothing: even five minutes off a logged point is
    # refused, while a capture time landing exactly on one still resolves.
    assert index.position_at(across_the_break, max_gap_min=0) is None
    assert index.position_at(datetime(2026, 7, 30, 12, 5, tzinfo=UTC), max_gap_min=0) is None
    assert index.position_at(datetime(2026, 7, 30, 12, 0, tzinfo=UTC), max_gap_min=0) == (
        40.0,
        -100.0,
    )


def test_negative_max_gap_min_rejected(two_file_dir: Path) -> None:
    index = load_track_index(two_file_dir)
    with pytest.raises(ValueError, match="max_gap_min"):
        index.position_at(datetime(2026, 7, 30, 12, 5, tzinfo=UTC), max_gap_min=-1)


def test_no_extrapolation_beyond_track_ends(two_file_dir: Path) -> None:
    index = load_track_index(two_file_dir)
    # 60 min before the first point: the first point's own position, unchanged.
    assert index.position_at(datetime(2026, 7, 30, 11, 0, tzinfo=UTC)) == (40.0, -100.0)
    # 100 min before the first point: beyond the gap, no position.
    assert index.position_at(datetime(2026, 7, 30, 10, 20, tzinfo=UTC)) is None
    # Same rule after the last point.
    assert index.position_at(datetime(2026, 7, 30, 17, 0, tzinfo=UTC)) == (41.2, -99.4)
    assert index.position_at(datetime(2026, 7, 30, 18, 0, tzinfo=UTC)) is None


def test_duplicate_timestamps_across_files_do_not_divide_by_zero(tmp_path: Path) -> None:
    _write_gpx(tmp_path / "one.gpx", _trkpt(40.0, -100.0, "2026-07-30T12:00:00Z"))
    _write_gpx(tmp_path / "two.gpx", _trkpt(40.5, -100.5, "2026-07-30T12:00:00Z"))
    index = load_track_index(tmp_path)
    assert index.position_at(datetime(2026, 7, 30, 12, 0, tzinfo=UTC)) is not None


def test_offsetless_and_offset_times_normalize_to_utc(tmp_path: Path) -> None:
    """GPX times are UTC by spec; an explicit offset is converted, not rejected."""
    _write_gpx(
        tmp_path / "mixed.gpx",
        _trkpt(40.0, -100.0, "2026-07-30T12:00:00")  # no zone marker at all
        + _trkpt(40.2, -100.4, "2026-07-30T14:10:00+02:00"),  # == 12:10Z
    )
    index = load_track_index(tmp_path)
    assert [t.hour for t, _, _ in index.points] == [12, 12]
    assert index.position_at(datetime(2026, 7, 30, 12, 5, tzinfo=UTC)) == pytest.approx(
        (40.1, -100.2)
    )


def test_malformed_file_skipped_good_file_loads(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "broken.gpx").write_text("<gpx><trk><trkseg><trkpt")
    _write_gpx(tmp_path / "good.gpx", _trkpt(40.0, -100.0, "2026-07-30T12:00:00Z"))
    with caplog.at_level(logging.WARNING):
        index = load_track_index(tmp_path)
    assert len(index.points) == 1
    assert any("broken.gpx" in r.message for r in caplog.records)


def test_empty_and_missing_dir_yield_empty_index(tmp_path: Path) -> None:
    assert load_track_index(tmp_path).points == ()
    assert load_track_index(tmp_path / "nope").points == ()
    empty = TrackIndex(())
    assert empty.position_at(datetime(2026, 7, 30, 12, 0, tzinfo=UTC)) is None


def test_non_gpx_files_and_subdirectories_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("not a track")
    (tmp_path / "archive").mkdir()
    _write_gpx(tmp_path / "archive" / "old.gpx", _trkpt(0.0, 0.0, "2020-01-01T00:00:00Z"))
    _write_gpx(tmp_path / "today.gpx", _trkpt(40.0, -100.0, "2026-07-30T12:00:00Z"))
    assert len(load_track_index(tmp_path).points) == 1


def test_naive_datetime_rejected(two_file_dir: Path) -> None:
    index = load_track_index(two_file_dir)
    with pytest.raises(ValueError, match="naive"):
        index.position_at(datetime(2026, 7, 30, 12, 5))


def test_bad_points_dropped_individually(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    _write_gpx(
        tmp_path / "mixed.gpx",
        _trkpt(40.0, -100.0, "2026-07-30T12:00:00Z")
        + '<trkpt lat="40.1" lon="-100.1"><ele>10.0</ele></trkpt>\n'  # no <time>
        + _trkpt(40.2, -100.2, "not-a-time")
        + '<trkpt lon="-100.3"><time>2026-07-30T12:30:00Z</time></trkpt>\n'  # no lat
        + _trkpt(40.4, -100.4, "2026-07-30T12:40:00Z"),
    )
    with caplog.at_level(logging.WARNING):
        index = load_track_index(tmp_path)
    assert [p[1] for p in index.points] == [40.0, 40.4]
    warning = next(r.message for r in caplog.records if "mixed.gpx" in r.message)
    assert "3" in warning  # the drop count is in the parse warning


@pytest.mark.parametrize(
    "text, expected_hour",
    [
        ("2026-07-30T12:00:00Z", 12),  # the usual GPX spelling
        ("2026-07-30T12:00:00+00:00", 12),  # explicit zero offset
        ("2026-07-30T14:00:00+02:00", 12),  # converted, not rejected
        ("  2026-07-30T12:00:00Z  ", 12),  # surrounding whitespace tolerated
        ("2026-07-30T12:00:00", 12),  # offset-less is read as UTC per the spec
    ],
)
def test_parse_gpx_time_accepts_the_shapes_loggers_write(text: str, expected_hour: int) -> None:
    parsed = parse_gpx_time(text)
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert parsed.astimezone(UTC).hour == expected_hour


@pytest.mark.parametrize("text", ["", "not-a-time", "2026-13-45T99:99:99Z", "yesterday"])
def test_parse_gpx_time_returns_none_rather_than_raising(text: str) -> None:
    assert parse_gpx_time(text) is None
