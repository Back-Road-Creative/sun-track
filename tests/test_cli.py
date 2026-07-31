"""The ``python -m sun_track`` shell: argument handling and exit codes.

Exit codes are part of the contract, because the point of a shell entry is
being usable from a script: 0 answered, 1 no position, 2 called wrongly.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sun_track.__main__ import main
from sun_track.solar import solar_elevation_deg

UTC = timezone.utc

GPX = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<gpx version="1.1" creator="example-logger"\n'
    '     xmlns="http://www.topografix.com/GPX/1/1">\n'
    "<trk><trkseg>\n"
    '<trkpt lat="40.0" lon="-100.0"><time>2026-07-30T12:00:00Z</time></trkpt>\n'
    '<trkpt lat="40.2" lon="-100.4"><time>2026-07-30T12:10:00Z</time></trkpt>\n'
    "</trkseg></trk></gpx>\n"
)


@pytest.fixture
def track_dir(tmp_path: Path) -> Path:
    (tmp_path / "day.gpx").write_text(GPX)
    return tmp_path


class TestSunCommand:
    def test_prints_elevation_and_band(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["sun", "40.0", "0.0", "2026-04-15T12:00:00Z"]) == 0
        elevation, band = capsys.readouterr().out.split()
        assert float(elevation) == pytest.approx(
            solar_elevation_deg(40.0, 0.0, datetime(2026, 4, 15, 12, 0, tzinfo=UTC)), abs=1e-3
        )
        assert band == "not-golden"

    def test_reports_golden_light_at_dusk(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["sun", "40.0", "0.0", "2026-04-15T18:40:00Z"]) == 0
        assert capsys.readouterr().out.split()[1] == "golden"

    def test_offsetless_time_is_read_as_utc(self, capsys: pytest.CaptureFixture[str]) -> None:
        main(["sun", "40.0", "0.0", "2026-04-15T12:00:00"])
        with_zone = capsys.readouterr().out
        main(["sun", "40.0", "0.0", "2026-04-15T12:00:00Z"])
        assert capsys.readouterr().out == with_zone

    @pytest.mark.parametrize(
        "argv",
        [
            ["sun"],
            ["sun", "40.0", "0.0"],
            ["sun", "north", "0.0", "2026-04-15T12:00:00Z"],
            ["sun", "40.0", "0.0", "not-a-time"],
        ],
    )
    def test_bad_invocation_exits_two(self, argv: list[str]) -> None:
        assert main(argv) == 2


class TestWhereCommand:
    def test_prints_interpolated_position(
        self, track_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["where", str(track_dir), "2026-07-30T12:05:00Z"]) == 0
        assert capsys.readouterr().out.strip() == "40.100000,-100.200000"

    def test_prints_none_and_exits_one_when_unmatched(
        self, track_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["where", str(track_dir), "2026-07-30T20:00:00Z"]) == 1
        assert capsys.readouterr().out.strip() == "NONE"

    def test_max_gap_argument_widens_the_match(
        self, track_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["where", str(track_dir), "2026-07-30T20:00:00Z", "600"]) == 0
        assert capsys.readouterr().out.strip() == "40.200000,-100.400000"

    def test_missing_directory_is_not_a_crash(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["where", str(tmp_path / "nope"), "2026-07-30T12:05:00Z"]) == 1
        assert capsys.readouterr().out.strip() == "NONE"

    @pytest.mark.parametrize(
        "argv",
        [
            ["where"],
            ["where", "DIR"],
            ["where", "DIR", "not-a-time"],
            ["where", "DIR", "2026-07-30T12:00:00Z", "soon"],
        ],
    )
    def test_bad_invocation_exits_two(self, argv: list[str], track_dir: Path) -> None:
        assert main([str(track_dir) if a == "DIR" else a for a in argv]) == 2


class TestDispatch:
    @pytest.mark.parametrize("flag", ["-h", "--help", "help"])
    def test_help_exits_zero(self, flag: str, capsys: pytest.CaptureFixture[str]) -> None:
        assert main([flag]) == 0
        assert "usage:" in capsys.readouterr().out

    def test_no_arguments_prints_usage_and_exits_two(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main([]) == 2
        assert "usage:" in capsys.readouterr().out

    def test_unknown_command_exits_two(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["moon", "40.0"]) == 2
        assert "unknown command: moon" in capsys.readouterr().out

    def test_module_runs_as_a_real_process_without_warnings(self) -> None:
        """``python -m sun_track`` must be clean — no runpy double-import warning."""
        result = subprocess.run(
            [
                sys.executable,
                "-W",
                "error",
                "-m",
                "sun_track",
                "sun",
                "40.0",
                "0.0",
                "2026-04-15T12:00:00Z",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        assert result.stdout.split()[1] == "not-golden"
