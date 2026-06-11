# Changelog

All notable changes to Pocket Curator are documented here.

## [0.63.2] - 2026-06-11

Second field-test round (RG35xxSP, Smart Pro S, RG552).

### Fetch browser: full deletion-screen parity
- Screenshots now upscale to fill the panel exactly like the deletion
  screens (ImageCache grows small art with no cap; the fetch preview
  wrongly capped at 1x).
- Hold-A mass-marks by advancing then marking, identical to deletion;
  up at the top of the list wraps to the bottom on a tap (and stops at
  the ends while held), identical to deletion.
- Marked-for-fetch rows show a thick bright-green plus and the row
  text turns the same green - the mirror image of deletion's red X and
  grey - clearing when the copies are queued.
- Headers across both screens: MARK FOR DELETE on deletion, FETCH FROM
  WebDAV on fetch, so the look-alike screens are instantly tellable
  apart.

### Fetch flow
- The copy queue's counters and progress bar reset when a new batch
  starts on an idle queue - the second copy session no longer opens at
  "72/142" with a half-full bar.
- The confirmation now counts how many of the marked games already
  exist in the destination system folder and, if any do, asks:
  Overwrite Them / Skip Them / Cancel. Skip copies only what's missing
  and says how many it skipped.
- Backing out of the fetch browser after copying shows a one-line
  notice that EmulationStation's games list updates when Pocket
  Curator exits.

### System carousel legend
- Reordered and restyled per design: a d-pad glyph + "Navigate", then
  A Enter, B Exit, X Delete System, Y WebDAV, Sel Settings - Title
  Case throughout - and the whole line now shrinks to fit the screen
  width, so it can never run off the right edge regardless of
  resolution or font-size setting. (The "font size 52" on the Smart
  Pro S = font_size_base 33 from settings.json x the 1.5 resolution
  scale for its 1280x720 screen; lower Font Size in Settings to taste,
  and the legend now fits regardless.)

### AmberELEC display - root cause found, two fixes, one honest limit
- v0.63.1's log proved the real story: pygame's bundled SDL was built
  WITHOUT the kmsdrm driver ("kmsdrm not available" persists even with
  the display released first), and AmberELEC's system SDL (2.26.2) is
  rejected by pygame as a version downgrade. dArkOS only works because
  its system SDL (2.32) is an allowed upgrade.
- New probe candidates: any PortMaster-shipped libSDL2 found on the
  device (these are newer, kmsdrm-capable builds and the one
  remaining path to a real display on AmberELEC). The log will show
  "PortMaster SDL found:" lines if any exist.
- The no-driver abort now cleans our Python environment before calling
  PortMaster's message UI - v0.63.1's abort crashed pugwash on a
  missing libffi.so.7 (it inherited our PYTHONHOME) and wedged the
  device instead of returning to ES. It also kills gptokeyb before the
  dialog so input can't ghost.
- If no PortMaster SDL exists or none works, AmberELEC now cleanly
  returns to ES with a message. Actually displaying on that device
  would then require shipping our own kmsdrm-enabled SDL build - a
  scope decision to make deliberately, not a bug to patch.

## [0.63.1] - 2026-06-11

Field-test fixes for the WebDAV fetch feature plus two launcher-level
display fixes, from R36S/dArkOS, Smart Pro S/Knulli, RG552/AmberELEC,
and RG35xxSP/ROCKNIX logs.

### Crash fix: Y press on dArkOS and ROCKNIX
- webdav.py imported `ssl` at module load; the bundled runtime on
  dArkOS/ROCKNIX lacks libssl.so.1.1, so pressing Y crashed the whole
  app with ImportError. ssl is now imported lazily and only for
  https:// URLs (with a clear "use http:// instead" message when the
  runtime can't do HTTPS), and the Y handler is guarded so no import
  failure can ever crash the app again.

### The folder decides the destination
- Copies now target the device system matching the remote folder
  you're browsing (amiga folder -> the handheld's amiga folder), not
  the system you launched from - fixing the bug where an atari2600
  ROM copied from the atari2600 folder landed in gba/. The extension
  filter follows the same mapping, so browsing other systems' folders
  shows their games instead of "nothing here matches". Folders that
  match no system on the device are browseable but copying is blocked
  with a clear message. (The mis-filed ROM appearing in the GBA list
  was ES scanning the file we put in the wrong place - nothing ever
  wrote to a gamelist.xml; deleting the stray file fully cleans it.)
- Navigation is now an explicit path stack: B always goes exactly one
  level back, and only backing out of the top listing leaves the
  browser - no more surprise disconnect to the server picker.

### Remote browser parity with the deletion screens
- Layout, fonts, and screenshot sizing now mirror the game list
  exactly (same list width, same image area at 70% of the panel, same
  description font); Y jumps to a letter and Select opens Settings,
  same as there.
- Listings load in a background thread with a readable "Opening
  connection..." / "Loading folder..." state; a slow server can no
  longer freeze the UI.
- While copying, the legend shows only "Copying 4/10: Title" over a
  thicker progress bar measuring the WHOLE queue in bytes - no
  per-file counters - and when the queue finishes the normal help
  text simply returns (no completion banner).

### Display: firmware-aware probing, cache, and no more headless runs
- The display is released (pm_platform_helper) BEFORE probing. On
  AmberELEC, ES still held DRM master during the probes, so every
  real driver failed and v0.62.x ran headless on a black screen -
  this ordering was the missing piece of the original v0.61.10 fix.
- The firmware name now picks the first probe (ROCKNIX->wayland,
  dArkOS->kmsdrm+system SDL, AmberELEC->bundled kmsdrm), and the
  winning probe is cached per firmware+device and tried first on
  every later launch - dArkOS launches skip four failed probes
  (~10s), and a cache hit also skips the standalone pygame import
  test (one fewer Python boot).
- If no real driver works, Pocket Curator now tells the user and
  returns to EmulationStation instead of running invisibly on the
  dummy driver.

### Exit speed
- The instant in-place ES reload (API) now runs first and silently;
  the "Refreshing your games list..." message - whose harbourmaster
  boot was most of the slow exit on ROCKNIX - only appears when the
  slow restart fallback is actually needed.

### Carousel
- The legend now shows "Y WebDAV".

## [0.63.0] - 2026-06-11

### Fetch from WebDAV (new feature)
- Press Y on a system in the carousel to fetch ROMs into it from a
  WebDAV or plain-HTTP server on the local network. The highlighted
  system IS the destination - the flow never asks where files go.
- Flow: saved sources (or straight to Find New when there are none) ->
  scan the local /24 for servers / enter an address -> connect ->
  remote browser. Servers requiring login prompt for username/password;
  passwords are kept for the session only, never written to
  settings.json.
- Remote browser: smart-jumps to the folder named after the system
  (gba for Game Boy Advance; one level of roms/ indirection followed),
  falls back to the listing otherwise. Folders draw a folder glyph;
  files filter to the system's extensions; A marks like the deletion
  list; pausing on a game pulls description/rating/image from the
  server's gamelist.xml. X opens the copy confirmation: Copy w/
  Scrapings (default), Copy (ROMs only), Cancel.
- Scrapings resolve from the remote gamelist.xml when present (exact
  media paths) or by filename match under images/videos/manuals/media.
- Copies run as a background queue: each file streams to .part and
  renames on completion (cancel/power-cut safe, resumable), free space
  is preflighted for the whole queue, and the legend bar shows
  "Copying 4/10: <title> NN%" - a game and its scrapings count as one.
  Fetched games trigger the normal ES refresh on exit.
- Protocol layer is read-only by construction (only OPTIONS, PROPFIND,
  HEAD, GET exist) and pure stdlib. WebDAV preferred, plain-HTTP
  autoindex (python -m http.server, nginx) auto-detected as fallback.
  Self-signed HTTPS accepted. Verified against live rclone and
  python http.server instances, including auth, resume, and integrity.

### On-screen keyboard (new component)
- D-pad keyboard with two layouts (X toggles): a numeric keypad for
  addresses with chord keys for '192.168.' '172.16.' '10.' and ports
  ':5005' ':8080' ':80', and a full qwerty (Y cycles shift/symbols).
  Masked entry for passwords. B backspaces, Start confirms.

### Design deviations from the spec (flagged for review)
- B remains "back" everywhere; the Scan/Enter and Copy confirmations
  are d-pad+A option lists rather than binding actions to B, so a
  reflexive B-press can never trigger a mass download.
- The copy confirmation defaults its highlight to Copy w/ Scrapings.


## [0.62.3] - 2026-06-10

### First-launch performance (slow-splash follow-up)
- Investigation of the ~2-minute first launch on a large library: the
  v0.62.2 timing marks show the in-app startup took 4.0s on that very
  launch (29 systems / 17,381 ROMs scanned in 3.75s, gamelist-only) -
  the wait lived in the launcher phase, which uniquely runs the update
  apply (18 MB copy to SD), cold bytecode compilation, and three cold
  Python boots on a first launch of a new version. Discovery was
  verified gamelist-only (no folder crawl, no per-entry stat), and the
  only gamelist.xml writer in the codebase remains Pocket Curator's own
  metadata entry - deletions are pure file unlinks; ES owns all other
  gamelist edits.
- Releases now ship precompiled Python bytecode (3.11, hash-based
  unchecked invalidation, valid regardless of extraction timestamps),
  removing the recompile cost from first launches entirely.
- Launcher log lines now carry elapsed-time stamps
  ("[Pocket Curator +12s] ...") at each phase: log start, update
  applied, runtime ready, python boot/pygame import, display probe,
  app launch, app exit - so a slow first launch is attributable from
  the log alone.

### Housekeeping
- The one-file installer's log no longer lingers in the ports root: the
  installer moves it into pocketcurator/install.log when it finishes,
  and the launcher adopts any stray copy from older installs on launch.


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
