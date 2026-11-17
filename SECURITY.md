# 🔒 Security Policy

## Reporting a vulnerability

This repository is private. Report a problem to the owner directly, not in a
public issue.

## Data handling

- The integration is meant to keep the Ariston Clima email and password in the
  Home Assistant config entry and send them only to the Midea cloud servers
  behind the Ariston Clima app (`mapp-eu.appsmb.com` or `mapp.appsmb.com`).
- `scripts/probe.py` reads the login from `ARISTON_EMAIL` and `ARISTON_PASSWORD`
  or hidden prompts (email and password), never from the command line. It does
  not print or store it, and its errors show only an exception class and a
  numeric code.
- With `--save-keys PATH` the probe writes the device's local token and key to
  PATH with mode 600 (a new file; symlinks and existing files are refused unless `--force`). Such files match `*.keys` in `.gitignore`; keep them out of
  git and delete them once the keys are in Home Assistant.
- The probe never sends a set command to the device.

## Supported versions

Only the latest commit on `main`.
