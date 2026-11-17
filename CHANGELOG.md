# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- `scripts/probe.py`, a read-only diagnostic: logs in to the Ariston Clima cloud
  on the EU and then the US server, lists the appliances, asks for the local
  token and key, and sends one status query. It prints a plain verdict.
- Repository scaffolding: README, AGENTS, SECURITY, LICENSE, `hacs.json`.
