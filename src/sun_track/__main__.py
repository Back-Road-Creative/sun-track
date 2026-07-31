"""``python -m sun_track <command>`` — a thin shell over the two modules.

Argument handling lives here and nowhere else, so :mod:`sun_track.solar` and
:mod:`sun_track.gpx` stay pure libraries with no argv or printing in them.
"""

from __future__ import annotations

from pathlib import Path

from sun_track.gpx import DEFAULT_MAX_GAP_MIN, load_track_index, parse_gpx_time
from sun_track.solar import is_golden_elevation, solar_elevation_deg

USAGE = """usage: python -m sun_track <command> [args]

commands:
  sun LAT LON ISO_UTC                    apparent solar elevation, and whether
                                         it falls inside the golden band
  where GPX_DIR ISO_UTC [MAX_GAP_MIN]    interpolated "lat,lon" from the *.gpx
                                         files in GPX_DIR, or NONE (exit 1)

Times are ISO-8601; a value with no offset is read as UTC."""


def _sun(argv: list[str]) -> int:
    if len(argv) != 3:
        print(USAGE)
        return 2
    try:
        lat, lon = float(argv[0]), float(argv[1])
    except ValueError:
        print(f"lat and lon must be numbers, got {argv[0]!r} and {argv[1]!r}")
        return 2
    when = parse_gpx_time(argv[2])
    if when is None:
        print(f"unparseable ISO time: {argv[2]}")
        return 2
    elevation = solar_elevation_deg(lat, lon, when)
    print(f"{elevation:.3f} {'golden' if is_golden_elevation(elevation) else 'not-golden'}")
    return 0


def _where(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print(USAGE)
        return 2
    when = parse_gpx_time(argv[1])
    if when is None:
        print(f"unparseable ISO time: {argv[1]}")
        return 2
    try:
        max_gap_min = float(argv[2]) if len(argv) == 3 else DEFAULT_MAX_GAP_MIN
    except ValueError:
        print(f"MAX_GAP_MIN must be a number, got {argv[2]!r}")
        return 2
    position = load_track_index(Path(argv[0])).position_at(when, max_gap_min)
    if position is None:
        print("NONE")
        return 1
    print(f"{position[0]:.6f},{position[1]:.6f}")
    return 0


COMMANDS = {"sun": _sun, "where": _where}


def main(argv: list[str]) -> int:
    """Dispatch ``argv`` (without the program name); returns a process exit code."""
    if not argv:
        print(USAGE)
        return 2
    if argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    command = COMMANDS.get(argv[0])
    if command is None:
        print(f"unknown command: {argv[0]}\n\n{USAGE}")
        return 2
    return command(argv[1:])


if __name__ == "__main__":  # pragma: no cover - thin argv shim
    import sys

    raise SystemExit(main(sys.argv[1:]))
