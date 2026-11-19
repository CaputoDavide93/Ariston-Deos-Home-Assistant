# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- `button` platform: four one-button presets (Laundry, Everyday, Boost, Switch Off), defined in `PRESETS` in `api.py`. Mode numbers are unverified on a live Deos.
- `scripts/probe.py`, a read-only diagnostic: logs in to the Ariston Clima cloud on the EU and then the US server, lists the appliances, asks for the local token and key, and sends one status query. It prints a plain verdict.
- README: why the integration exists, that it covers the Deos range, an architecture diagram and an entities diagram (`tools/gen_diagram.py`), a brand icon and a social preview image.
- Marketplace readiness: brand icons in `custom_components/ariston_deos/brand/`, `icons.json` for the preset buttons, a code owner and `integration_type` in the manifest, and hassfest, HACS validation and test workflows.
- Repository scaffolding: README, AGENTS, SECURITY, LICENSE, `hacs.json`.

### Changed

- The device is called "Deos", not "Deos 16S NET": the integration offers every Deos on the account.

### Fixed

- `scripts/probe.py`: the cloud status step goes through the library's `LanDevice.refresh` (correct `5A5A` envelope) and passes only on a fresh status payload; errors print only the exception class and a numeric code; the email prompt is hidden; `--save-keys` creates a 0600 file, refuses symlinks and existing files unless `--force`; a failed appliance list gives an undetermined verdict, not "no dehumidifier".
- README: HACS cannot install from a private repository, so manual copy is documented.
