# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- `scripts/probe.py`: the cloud status step now goes through the library's `LanDevice.refresh` (correct `5A5A` envelope) and passes only on a fresh status payload; errors print only the exception class and a numeric code; the email prompt is hidden; `--save-keys` creates a 0600 file, refuses symlinks and existing files unless `--force`; a failed appliance list gives an undetermined verdict, not "no dehumidifier".
- README: HACS cannot install from a private repository, so manual copy is documented.

### Added

- `scripts/probe.py`, a read-only diagnostic: logs in to the Ariston Clima cloud
  on the EU and then the US server, lists the appliances, asks for the local
  token and key, and sends one status query. It prints a plain verdict.
- Repository scaffolding: README, AGENTS, SECURITY, LICENSE, `hacs.json`.
