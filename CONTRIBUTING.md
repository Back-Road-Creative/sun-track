# Contributing to sun-track

Thanks for taking a look. This is a deliberately small library, so the bar for
new surface area is high and the bar for correctness is higher.

## Reporting

- **Bugs and feature requests:** open an issue. For a wrong number, include the
  latitude, longitude, UTC instant, what you got, what you expected, and where
  your expected value came from — that last part is the useful half.
- **Security vulnerabilities:** do not open a public issue. Follow
  [`SECURITY.md`](SECURITY.md).

## Development setup

Python 3.11 or newer. No runtime dependencies.

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## The gates (run before you push)

CI runs these on every push and pull request:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

## Things this project cares about

- **Test against the world, not against the code.** The solar suite checks the
  implementation against facts that are true independently of it — peak elevation
  equals `90 - |latitude - declination|`, solar noon at longitude 0 sits at 12:00
  UTC offset by the equation of time, the sun does not set at 80° north in June.
  Pinning a number this library happens to produce only proves it has not changed.
  If you add a reference case, say in a comment where the reference came from.
- **Never weaken a test to make a suite pass.** If a test is wrong, fix the test
  and say why in the commit message.
- **No dependencies.** Both modules are standard library only, which is much of
  the point of the package. A change that adds a runtime dependency needs to
  argue its way in first — open an issue before writing it.
- **No network calls, ever.** Neither module opens a socket, and neither should.
- **Never guess a timezone.** Every entry point takes an aware datetime and
  raises on a naive one. That is the design, not an oversight.
- **Docs land with the code.** A behaviour change updates the README, the
  docstring, and `CHANGELOG.md` in the same commit.

## Test fixtures

Every coordinate and track in the test suite is invented. Please keep it that
way — do not contribute a fixture built from your own photos or track logs, even
rounded. Synthetic tracks with round numbers are easier to read anyway.

## Commits and pull requests

- Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`, …).
- One logical change per pull request, with the gate output in the description.
- Pin GitHub Actions to a version, never a moving branch.

## Conduct

By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
