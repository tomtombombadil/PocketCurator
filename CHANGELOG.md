# Changelog

All notable changes to Pocket Curator are documented here.

## [0.62.2] - 2026-06-10

### Update flow
- "Check For Updates" now opens a Software Update dialog that runs the
  whole pipeline unattended - no second confirmation between "found"
  and "download". Progress reads as a checklist: Checking for update...
  / Update found: vX / Downloading update... NN% / Verifying update... /
  Update ready! Restart Pocket Curator to complete the update. Closing
  the dialog mid-download is safe; the download continues and the
  Settings row reflects it.
- The updater now logs every step (check, found+size, download URL,
  verify, staged) so the launcher log answers "what did the update do"
  by itself.

### Startup timing instrumentation
- Always-on [timing] log marks across startup: settings/db load, display
  init, theme resolution, and the ROM scan (with system and ROM counts).
  Investigation of the reported slow splash on a large library points at
  the discovery ROM walk - which v0.62.x never touched - but the next
  slow-splash log will now say definitively which phase ate the time,
  and how it scales with library size.

### Status dialog
- Row values now word-wrap to the panel width (over-long single tokens
  like paths are middle-ellipsized), fixing the Version line overflow.
  Latest-version wording shortened to wrap cleanly.


## [0.62.1] - 2026-06-10

### Settings
- "Check For Updates" moved to the top of the list; its idle row no
  longer shows placeholder text.
- New "Status" dialog (modal, like the delete confirmation): Pocket
  Curator version with a latest/update-available indicator, detected OS,
  ROMs location, active theme, internet reachability, and whether the
  clock is synced well enough for secure connections. Network rows are
  probed in the background and read "No Internet Connection" when
  offline. The OS/ROMs/Theme block at the bottom of Settings moved into
  this dialog.
- Settings menu item names are now Title Case.

### Metadata installer relocated (ports-menu decluttering)
- PocketCuratorMetadataInstall.sh no longer ships in the ports root, so
  EmulationStation no longer lists it as a launchable entry. The logic
  moved to pocketcurator/tools/install_metadata.sh, invoked
  automatically by the one-file installer and by the launcher.
- Self-registration: on exit, the app checks whether its own entry is
  missing or incomplete in the ports gamelist (e.g. after a manual zip
  install) and, if so, has the launcher run the metadata installer -
  whose refresh also covers that session's deletions. Manual installs
  now register themselves on first exit; no user action needed.
- Updating from an earlier release deletes the stray script from the
  ports root.
- Verified: the metadata writer sets only Pocket Curator's descriptive
  fields. It does not set 'favorite' or any other user-preference flag.


## [0.62.0] - 2026-06-10

### One-file installer (new)
- New release asset `PocketCurator.Installer.sh`: copy this single file
  into the ports folder, launch it from EmulationStation with WiFi on, and
  it downloads the latest release from GitHub, verifies it (SHA256 +
  zip integrity), installs it, runs the metadata install, and refreshes
  ES so Pocket Curator appears immediately. Always fetches the latest
  release, so the installer never goes stale. Re-running it later
  reinstalls/repairs without touching user settings.
- Installer preflights the classic failure modes: missing curl/unzip,
  low disk space (<60 MB), and the no-RTC wrong-clock TLS trap (warns
  the user to stay on WiFi a minute and retry instead of failing
  cryptically).

### In-app updater (new)
- Settings now has "Check for updates": queries GitHub's latest release,
  and on confirmation downloads (~5 MB, live progress), verifies SHA256 +
  zip integrity, and stages the update. The launcher applies it at the
  start of the next launch and relaunches straight into the new version.
- Staged-apply design: nothing touches the live install until the next
  launch; the READY flag is written only after a verified stage; a power
  cut mid-apply re-runs the apply on the following launch; the launcher
  self-replacement runs from a /tmp helper (bash reads scripts
  incrementally, so a script must never overwrite itself in place);
  settings.json is pruned from staged trees so updates can never clobber
  user settings.
- All network I/O uses the system curl (firmware CA store) rather than
  the bundled python's ssl, and failures map to human-readable causes:
  no WiFi, GitHub rate limit, and the no-RTC wrong-clock TLS failure.

### Release process
- Every release now publishes a `pocketcurator_port-vX.XX.X.zip.sha256`
  alongside the zip; updater and installer verify against it.


## [0.61.13] - 2026-06-09

### EmulationStation refresh (ArkOS family / dArkOS / R36S)
- Fixed the ~90-second frozen "Refreshing your games list..." screen after a
  v0.61.12 refresh. ES only processes SIGTERM in its main UI loop, which is
  suspended while ES waits on a launched port; if `systemctl stop` lands in
  that window, systemd waits out its default `TimeoutStopSec` (90s) before
  SIGKILLing. The transient unit now sleeps 3s (letting ES return to its
  loop), runs the stop in the background, and SIGKILLs the unit if the stop
  hasn't completed within 5s - the in-flight stop job then finishes
  immediately, and `Restart=on-failure` doesn't re-trigger on an intentional
  stop. Typical refresh is now a few seconds; worst case ~8s. SIGKILL is
  also safer for us: ES can't flush a stale in-RAM gamelist over our edits.

### Console cleanup on exit (ArkOS family)
- Reset tty1 (`\033c`, as dArkOS's own scripts do) before the refresh
  messaging, clearing the control-character garbage (`^]` etc.) shown
  between the app releasing the display and harbourmaster's message.
- Silenced our own bash "Killed" job notices (wait-after-kill) and stopped
  `pkill -f gptokeyb` from matching - and killing - its own `sudo pkill`
  cmdline (bracket pattern `[g]ptokeyb`). PortMaster's pm_finish prints two
  similar notices from funcs.txt that are outside our tree and may still
  flash briefly.


## [0.61.12] - 2026-06-09

### EmulationStation refresh (ArkOS family / dArkOS / R36S)
- Added an ArkOS-family branch to the exit-refresh fallback. These firmwares
  have no `reloadgames` API, so the launcher restarts the ES systemd service
  after the app exits. The stop -> (metadata re-write) -> start sequence runs
  via `systemd-run` as a transient unit *outside* the ES cgroup, because the
  launcher itself is a descendant of the ES service: a normally-forked
  sequence (even setsid'd) is SIGTERM'd by its own `systemctl stop`, which
  would strand the device on a black screen with ES down.
- For `metadata`/`both` refreshes, Pocket Curator's gamelist write happens
  during the ES-down window (same clobber hazard as Batocera: ES's clean quit
  flushes dirty in-RAM gamelists over on-disk edits).
- Last-resort path when passwordless sudo/systemd is unavailable: the dArkOS
  ES wrapper's native RetroPie `/tmp/es-restart` sentinel + terminating the
  ES *binary* (identified via `/proc/PID/exe`, never the wrapper script);
  the wrapper loop relaunches ES, which re-reads gamelists from disk.
- Metadata installer: when the reload API never answers and an ES systemd
  service exists, queue one `systemctl restart emulationstation --no-block`
  so the written metadata actually appears (dArkOS).

## [0.61.11] - 2026-06-09 (test build - superseded, never released)

- First ArkOS-family ES restart attempt using the `/tmp/es-restart` sentinel.
  Hung dArkOS hard: ES was killed while the app still held DRM master on the
  kmsdrm display, and the wrapper loop relaunched ES instantly into a display
  it couldn't acquire, requiring a power cycle. Root-caused and replaced in
  0.61.12 (refresh now strictly after app exit + cgroup-escaped restart).

## [0.61.10] - 2026-06-09 (test build - folded into 0.61.12)

### Display
- AmberELEC (RG552) fix: added bundled-SDL (no preload) probes for kmsdrm and
  x11 ahead of the system-SDL preload variants. AmberELEC's system SDL
  (2.26.2) is older than the bundled pygame's SDL (2.28.4), so preloading it
  was rejected as a version downgrade and no driver worked. Wayland stays
  first, so ROCKNIX/Knulli are unaffected. (dArkOS confirmed working via
  kmsdrm + system-SDL preload, its SDL 2.32.10 being newer than bundled.)


## [0.61.9] - 2026-06-08

### Controls
- Reverted the v0.61.8 ROCKNIX A/B swap. ROCKNIX face buttons are back to the
  original, correct mapping; the swap would have broken correctly-configured
  devices (e.g. RG40xxV). The reversed A/B seen on one RG40xxH is device/config
  side (ES and gptokeyb use different input mappings), not the gptk file.
- Added a controller-mapping diagnostic to the launcher log (SDL face-button
  map + input device names) to compare units and pinpoint such cases.

## [0.61.8] - 2026-06-07

### Controls
- ROCKNIX: swapped the A/B (and X/Y) gptk mapping to match current ROCKNIX
  builds, which report face buttons in SDL-standard order (same as Knulli).
  Fixes A and B acting reversed. Knulli mapping unchanged.

### System logos
- Resolve the logo from the theme's entry file (theme.xml) instead of every
  XML in the theme folder, so dormant layout variants with broken relative
  paths can no longer outrank the real logo (fixes Pulse falling back to the
  default theme).
- Stopped treating a bare `art/` folder as backdrop artwork; many themes
  (e.g. Pulse) keep their real system logos there.

## [0.61.7] - 2026-06-07

Theme/logo overhaul and UI fixes — making system logos work across many themes,
region-correct, and resilient.

### System logos
- Read logos the way EmulationStation does: parse the active theme's declared
  `<image name="logo">` path and resolve `${system.theme}` per system, instead
  of guessing folder layouts.
- **Region-aware**: honor `ifSubset="artworkregion:US"`-style logo variants,
  choosing US vs EU/JP from the theme region setting, else EmulationStation
  `ScraperRegion`, else timezone.
- **Prefer real wordmark logos** over system backdrop/artwork when a theme
  exposes both as `<image name="logo">` (e.g. art-book-next, Knulli's default),
  scoring on logo path and `.svg` type.
- Ignore static logo paths that don't vary per system (generic icons).
- Fall back to the firmware's bundled default theme for any missing system logo
  rather than dropping to text.
- **Fixed active-theme detection**: read the live `ThemeSet` (incl. Knulli's
  settings path); never silently lock onto the first theme folder.

### UI
- Carousel wraps previous/next logos at the list ends.
- Restored previous/current/next names in the text fallback, wrapped per slot.
- Reworded exit-after-delete and metadata-installer messages; text fitted for
  1:1 screens (e.g. RGCubeXX).

### Performance
- Hard-coded fallback-theme locations instead of scanning/parsing every theme at
  startup.

## [0.60.0] - 2026-06-06

First packaged build: on-device browse-and-delete of ROMs and their scraped
media, Safe Mode dry run, automatic EmulationStation refresh, and a one-shot
metadata installer. aarch64; requires PortMaster.
