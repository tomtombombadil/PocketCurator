# Pocket Curator

**An on-device ROM and scraped-media cleanup tool for retro handhelds.**
Browse your installed systems and games in an EmulationStation-style carousel,
then flag and delete ROMs together with their scraped artwork — no PC, no SSH,
and without pulling the SD card.

![Systems carousel](pocketcurator/assets/Screenshot-Systems.jpg)
![Games list](pocketcurator/assets/Screenshot-GamesList.jpg)

> **Status:** beta (v0.61.x). Tested on ROCKNIX and Knulli. Other PortMaster
> aarch64 firmwares should work but are unverified — reports welcome.

## Why this exists

Most handheld firmwares let you *hide* a game from the menu, but the ROM and the
images, videos, and manuals a scraper downloaded stay on the card. Reclaiming
that space has meant pulling the SD card and hunting files on a PC. Pocket
Curator does it on the device: it shows each game's screenshot, description,
rating, genre, and region, then removes the ROM and its media together and
refreshes EmulationStation for you.

## Supported firmware

| Firmware | Status |
|----------|--------|
| **ROCKNIX** | Primary target — tested |
| **Knulli** | Tested |
| muOS, ArkOS, JELOS, AmberELEC | Should work (any PortMaster aarch64 firmware); unverified |

Architecture: **aarch64** only. Requires [PortMaster](https://portmaster.games/).

## Installation

Pocket Curator is **not** in the PortMaster store, so it's installed manually —
a one-time copy, after which everything happens on the device.

1. Download `pocketcurator_port.zip` from the
   [latest release](../../releases/latest) and unzip it.
2. Copy `Pocket Curator.sh`, `PocketCuratorMetadataInstall.sh`, and the
   `pocketcurator/` folder into your **ports** folder:
   - ROCKNIX / JELOS / AmberELEC: `/roms/ports/` (or `/roms2/ports/`)
   - Knulli / Batocera: `/userdata/roms/ports/`

   Over the network is easiest — both ROCKNIX and Knulli expose a Samba share
   and SSH/SFTP over Wi-Fi, so you can drop the files in without removing the
   card.
3. Refresh your Ports list (restart EmulationStation, or "Update Gamelists"
   once) and launch **Pocket Curator** from Ports.

On first run, Pocket Curator downloads the Python runtime through PortMaster.
**This needs Wi-Fi the first time only** — afterwards it runs fully offline.

## Controls

**Systems carousel:** Left/Right choose (wraps) · A enter · X delete whole
system · Select settings · B exit.

**Games list:** Up/Down move · L1/R1 page · A mark/unmark · X delete marked ·
Y jump · L2/R2 scroll description · Select settings · B back.

## What gets deleted

For each marked game, Pocket Curator removes the ROM plus the media its
`gamelist.xml` entry explicitly references — `<image>`, `<thumbnail>`,
`<marquee>`, `<video>`, and `<manual>`. Only files named in the gamelist entry
are touched.

- **Safe Mode** (Settings) is a dry run: it logs what it *would* delete without
  touching a file.
- **Delete scraped media** (Settings) can be turned off to remove ROMs only.

After deletion, Pocket Curator asks the running EmulationStation to reload its
gamelists, so deleted games drop out of the menu on exit — no manual rescan.

## System logos

Pocket Curator ships **no** logos of its own; it reads them from your installed
themes the way EmulationStation does:

- It detects your **active theme** (from EmulationStation's live theme setting)
  and reads that theme's declared system-logo path.
- It prefers a theme's real **wordmark** logos over decorative system
  backdrop/artwork when a theme provides both (e.g. art-book-next), using the
  logo path and image type as signals.
- **Region artwork** is honored: themes that ship US vs EU/JP logo variants
  (TurboGrafx-16/PC Engine, Genesis/Mega Drive) are resolved using your region —
  the theme's region setting if present, otherwise EmulationStation's
  `ScraperRegion`, otherwise your timezone.
- When the active theme has no usable logo for a system, Pocket Curator falls
  back to the firmware's bundled default theme so you still get a real logo.
- If nothing can be found, the carousel shows the system name (previous /
  current / next), wrapped to fit.

No theme configuration is required; switch themes in EmulationStation and Pocket
Curator follows.

## Pocket Curator's own icon and description

Out of the box, EmulationStation lists Pocket Curator as a plain name. To give
its entry a screenshot, description, logo, and preview video, launch
**PocketCuratorMetadataInstall** from Ports once and wait at the menu ~15–20
seconds; the entry fills in and stays.

<details>
<summary>Why a separate installer?</summary>

EmulationStation rewrites each gamelist from memory whenever you return from a
"game" (a port counts), so metadata written while a port runs gets overwritten.
The only moment a write survives is when ES is idle at its menu, so the
installer schedules the write and an in-place gamelist reload to run a few
seconds after it exits.
</details>

## Settings

Reachable with **Select**: font size, description auto-scroll, **Safe Mode**,
**Delete scraped media**, and rating display. The screen also shows the detected
firmware, ROMs location, active theme, and artwork region. Settings persist in
`pocketcurator/settings.json`.

## Troubleshooting

- **First launch errors about a runtime/download** — needs Wi-Fi once; get
  online and relaunch.
- **Wrong theme's logos** — Pocket Curator follows ES's live theme; check the
  log line `[theme] active theme name '...'`.
- **Wrong region logos** — set the theme's region or ES's Scraper region; the
  log line `[app] artwork region: ...` shows what was detected.
- **Own icon didn't appear** — run `PocketCuratorMetadataInstall` once and let
  ES sit idle ~20s.
- **`xkbcommon ... Compose ... UTF-8` log lines** are harmless input-teardown
  noise, unrelated to Pocket Curator.

A fresh log is written to `pocketcurator/pocketcurator.log` each launch.

## Building / packaging

This port bundles the `pygame` wheel for aarch64. See
[`pocketcurator/BUILD.md`](pocketcurator/BUILD.md).

## Credits and license

Released under the **MIT License** — see [`LICENSE`](LICENSE). Thanks to the
**PortMaster** team. Bundled **Oxanium** font under SIL OFL 1.1; `pygame` under
the LGPL (see `pocketcurator/licenses/`).
