# Polar AccessLink Sync (archived prototype)

> **Status: superseded — this repo is kept for reference only.**

This was an early prototype of an Obsidian plugin that pulled Polar
AccessLink data (exercises, sleep, nightly recharge) into vault notes. It
never reached a buildable state: there is no build tooling, the manifest
points at TypeScript source rather than a compiled `main.js`, credentials
were hardcoded placeholders, and the OAuth flow was never implemented.

## Use instead

- **[wombohealth](https://github.com/ultrapolar/wombohealth)** — the
  multi-source health hub. It already ingests Polar via a proper OAuth
  flow (`/connect/polar`), merges it with Ultrahuman, Withings, Fitbit,
  Samsung, and Wyze data, and writes a daily Health block into Obsidian
  through its exporter. This is where Polar → Obsidian lives now.
- **[ultrahumanxobsidian](https://github.com/ultrapolar/ultrahumanxobsidian)**
  — if you ever want a *standalone* Polar plugin, copy this repo's
  structure (esbuild config, settings tab, managed note sections,
  release workflow); it's the template a rewrite should follow.
