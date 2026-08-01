# Security Policy

## Supported versions

Only the latest released tag receives fixes. Pin a released `v*` tag; `main` is
unstable.

## Attack surface, honestly

sun-track is a small pure-Python library with no runtime dependencies. It opens no
network connections and holds no credentials. There are two places untrusted input
reaches it:

- **`load_track_index()` parses XML** with the standard library's
  `xml.etree.ElementTree`. That parser is not hardened against hostile XML — a
  crafted file can attempt entity-expansion ("billion laughs") and similar
  resource-exhaustion attacks. `load_track_index()` catches parse failures and
  skips the file, but it cannot prevent a parser from consuming memory or CPU
  before it fails. **Do not point it at GPX files you did not produce or do not
  trust.** If you must, parse them first with a hardened parser such as
  `defusedxml`, or run the load under a memory and time limit.
- **Filesystem reads.** The directory path you pass is used as given. Passing a
  path derived from untrusted input lets the caller choose which directory is
  read; validate it yourself before passing it in.

`sun_track.solar` performs arithmetic on floats and touches nothing outside the
process.

## Reporting a vulnerability

Please report privately. Do **not** open a public issue for a security report.

- Preferred: GitHub's **Security → Report a vulnerability** tab on this repository
  (Private Vulnerability Reporting).
- Fallback: email **backroadcreativeco@gmail.com** with `sun-track security` in the subject.

Please include the affected version or commit, a description of the impact, and
reproduction steps or a proof of concept.

## What to expect

- Acknowledgement within 5 business days.
- An initial assessment and severity triage within 10 business days.
- Coordinated disclosure: we will agree a timeline with you before any public
  write-up, and credit reporters who want it.
