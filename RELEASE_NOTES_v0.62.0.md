# Pocket Curator v0.62.0 (beta)

## Which file do I want?

- **New install?** Download **`PocketCurator.Installer.sh`** (the small
  one), copy it into your ports folder, and launch it from
  EmulationStation with WiFi connected. It downloads and installs
  everything else by itself.
- **Already installed (v0.62.0 or later)?** You don't need this page —
  open Pocket Curator's **Settings → Check for updates**.
- **`pocketcurator_port-v0.62.0.zip`** is the full port, for manual or
  offline installs only: extract it into your ports folder.
- Ignore the "Source code" links at the bottom — GitHub adds those
  automatically and they are not an installable build.

## What's new

This release is all about getting Pocket Curator on and off your device
without a PC in the loop.

- **One-file installer.** One small file in your ports folder, one
  launch, done — it fetches the latest release over WiFi, verifies it,
  installs it, and refreshes EmulationStation so Pocket Curator shows up
  immediately, icon and all. It always installs the *latest* release, so
  a copy you downloaded months ago still installs the current version.
  Re-running it repairs an install without touching your settings.
- **Built-in updates.** Settings → Check for updates finds new releases,
  downloads with a live progress display, verifies the download (SHA256
  and zip integrity), and installs itself on the next launch — your
  settings always survive. Designed to be power-cut-safe: an interrupted
  update simply resumes its install on the following launch.
- **Releases now ship a `.sha256` checksum** that the installer and
  updater verify downloads against.

Both features need WiFi; both speak human when something goes wrong (no
WiFi, GitHub rate limit, or the wrong-clock TLS failure that no-RTC
handhelds hit right after boot).

Supported firmwares unchanged: ROCKNIX, Knulli, dArkOS/ArkOS, and
limited AmberELEC.
