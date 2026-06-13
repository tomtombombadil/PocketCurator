# Changelog

All notable changes to Pocket Curator are documented here.

## [1.0.6] - 2026-06-13

### CRITICAL: fetch destination resolution (Batocera/Knulli)
- Fetched games were landing in roms/ports/pocketcurator (the app's
  own folder) instead of the system's roms folder. Cause: Batocera and
  Knulli write es_systems.cfg <path> entries as "%ROMPATH%/amiga500"
  or "./snes", which Pocket Curator left relative - so they resolved
  against the working directory (the port dir). Pocket Curator now
  expands %ROMPATH% and anchors any relative path to the device's roms
  directory, so destinations are always absolute and correct.
- Added a hard safety guard: Pocket Curator will REFUSE to copy if a
  destination doesn't resolve to a real, absolute folder outside its
  own port directory, rather than scatter files into itself. This also
  removes the most likely cause of a boot-loop seen after fetching on
  one device - writing into the running app's directory.
- Amiga family aliases added (amiga <-> amiga500/amiga1200/amigacdtv),
  so a remote "amiga" folder resolves to whichever Amiga system the
  device actually has. Fixes the fetch screen showing "/amiga/ ->
  Amiga" against a non-existent roms/amiga folder on Batocera/Knulli.

### Ghost systems (Batocera)
- Batocera ships a few stock gamelist entries whose ROM files don't
  exist (Megadrive "Old Towers", PCEngine "Reflectron"/"Santatlanean",
  and single-game ports). They made empty systems look populated, then
  showed nothing on entry. gamelist.xml remains the source of truth for
  normal systems, but a SMALL system (<=5 games) is now confirmed by
  checking that at least one listed ROM exists on disk; if none do, the
  system is treated as empty and not shown. Large libraries skip the
  check (no per-file cost).

### Fetch confirmation
- The "calculating file sizes" prompt no longer sticks: once sizing
  finishes, pressing A starts the copy immediately - you no longer have
  to move off the menu item and back. Message reworded to "Please wait
  while calculating file sizes...".

### Fetch logging
- The log now records the server, system, and destination at the start
  of a copy, then each job and each file copied (source -> destination,
  size), so fetch issues can actually be diagnosed.

### Updated
- Pocket Curator's own store description now reflects the fetch feature
  (copy as well as delete, WebDAV). Installs with the old description
  are updated automatically on the next metadata write.

### Notes
- dArkOS logos confirmed fixed in 1.0.5 (SNES/NES/Genesis correct).
- A boot-loop after fetching was reported on one ROCKNIX device; its
  most likely cause (files written into the port dir) is addressed by
  the destination fix + guard above, but couldn't be reproduced from a
  log. Please report if it recurs with 1.0.6.

## [1.0.5] - 2026-06-13

### Fixed: theme logos (dArkOS + Batocera)
- Pocket Curator was showing the Super Famicom logo for SNES (and
  Family Computer for NES, and the wrong one for PC Engine / TG16) -
  different from what the user's themed EmulationStation shows. Cause:
  an alias logo file (sfc.png) in a theme template we preferred could
  beat the primary-name file (snes.png) in another template. Now the
  PRIMARY system name is tried across ALL of a theme's logo templates
  before any alias, so Pocket Curator matches ES. Aliases still cover
  themes that genuinely only ship the alternate name.

### Fixed: runaway font size (Batocera)
- The auto-scale wrote its scaled result back into the same setting it
  read from, so each launch re-scaled the already-scaled value
  (22 -> 53 -> 127...). The user's chosen size is now stored
  separately and the per-screen scale is computed fresh each launch,
  so it stays put. An install that already inflated recovers to a sane
  size on next launch.

### Fixed: fetch screenshot clipping (Batocera)
- The preview image could overflow its reserved area and clip down
  into the stars/region line. It's now clamped to the current area
  every frame, like the deletion screen.

### Fixed: phantom "systems"
- Single-game port engines that present themselves as ES systems
  (Half-Life and ~30 others on Batocera/Knulli) are no longer listed
  as game systems.

### Faster: copy confirmation
- The confirm dialog now opens IMMEDIATELY and shows "Calculating File
  Sizes..." while it totals scraped-media sizes in the background
  (previously it stalled after pressing X on large selections). The
  scrapings copy waits until sizing finishes; ROMs-only is available
  at once.

### New: live transfer rate
- The "Copying ##/##" line now shows a right-justified download speed
  (1 decimal, KB/s or MB/s), smoothed so it doesn't jitter.

### New: progress that follows you
- The copy progress (title + speed + bar) now persists as a strip at
  the bottom of whatever screen you're on, so leaving the fetch UI no
  longer hides an in-progress copy.

## [1.0.4] - 2026-06-12

### Restored
- The Status dialog's Internet and Clock rows are back. They were
  removed by mistake in v1.0.1 while removing the update check; only
  the update check should have gone. The update check stays removed
  (Check For Updates owns that); Internet reachability and clock-sanity
  are reported again, alongside the Refresh Games List On Exit line.

### Fixed
- Fetch screen: with Auto-Scroll Description on (or scrolling with
  R1/L2), the description text scrolled up over the image, stars, and
  region line. The fetch screen was faking the scroll by moving an
  oversized rectangle and setting its own clip, which the text drawer
  then overwrote. It now scrolls exactly like the deletion screen -
  same clip rectangle, scroll handled by the drawer's own offset - so
  the text stays inside the description area. Affected all firmwares.

## [1.0.3] - 2026-06-12

### Fixed: doubled input on Knulli and dArkOS (the v1.0.2 fix didn't reach them)
v1.0.2 exported the PC_PAD_INPUT gate inside the display-probe block -
but the system-python firmwares (Knulli, Batocera) never enter that
block, so the variable stayed unset there and the app fell back to its
driver heuristic, doubling every press again. dArkOS was hit by the
same class of bug since v1.0.0 (its kmsdrm driver tripped the old
heuristic), which is why v0.63.2 worked there and v1.0.0 didn't.

- PC_PAD_INPUT is now defaulted to 0 EARLY, on every launch path,
  before any branch. Only our own pcSDL kmsdrm path (AmberELEC, where
  SDL genuinely can't see gptokeyb's keyboard) flips it to 1 after the
  probe.
- Result: Knulli, ROCKNIX, dArkOS, and Batocera all keep their normal
  single keyboard input; AmberELEC keeps its gamepad translation.

Firmware matrix now verified end to end: AmberELEC translation ON; all
others OFF.

## [1.0.2] - 2026-06-12

### Fixed: doubled controller input on Knulli (and any system-keyboard firmware)
v0.64.4/v0.64.5 added gamepad-to-key translation for AmberELEC, gated
on "any non-wayland/x11 SDL driver." That was too broad: Knulli's
system pygame reports its driver as kmsdrm but DOES deliver gptokeyb's
keyboard to SDL, so both the real key AND the translated key fired -
doubling every press. Symptoms: the d-pad skipped every other item,
Left/Right jumped two systems, A entered a list and immediately exited,
Status was skipped in Settings, and the app couldn't be exited
normally.

- The launcher now sets PC_PAD_INPUT explicitly, and only enables
  gamepad translation on our own pcSDL kmsdrm path (AmberELEC), where
  SDL genuinely cannot see the keyboard. Every other firmware
  (Knulli/ROCKNIX via the compositor, dArkOS via system-SDL) keeps its
  normal single keyboard input. The app honors the flag, falling back
  to the old driver heuristic only when launched without it (dev runs).

This restores correct single-step navigation on Knulli and ROCKNIX
while keeping AmberELEC's controller support working.

## [1.0.1] - 2026-06-12

### Settings menu
- Removed Safe Mode (no longer useful now that the workflow is proven).
- "Delete Scraped Media" renamed to "Delete Scraped Files with ROMs"
  and moved above Auto-Scroll Description.
- Restore Gamelist Backup moved to the bottom of the list.
- Rows are now compact (same height as the delete/fetch game lists),
  fitting more settings on screen.
- The list scrolls when it doesn't fit, with up/down arrow indicators
  showing there's more in that direction; L1/R1 jump to the top/bottom.
- The bottom hint and legend lines are now pinned and reserved, so they
  never clip into the list no matter how large the font is set.
- Legend is in Title Case and now documents L1/R1 Jump.

### New settings
- **Font Color** - 7 bright colors (white, red, orange, yellow, green,
  blue, purple) plus Theme Default. Left/Right scroll through swatches
  (shown as a small color box on the right), wrapping infinitely.
- **Highlight Color** - 7 darker selection colors (grey, red, orange,
  yellow, green, blue, purple) plus Theme Default, chosen to keep the
  bright font colors readable on top. Same swatch + scroll UX.
- **Swap Games List Side** - Left (current) or Right, which mirrors the
  whole games-list layout (list on one side, preview/details on the
  other). Built on a modular split-layout so more arrangements can be
  added later.

### Marked-row badges (so they survive any color choice)
- Marked rows now keep the normal text color; a small inverted badge
  carries the signal: black + on a green chip (fetch, new), black ? on
  a yellow chip (fetch, already on device), black X on a light-grey
  chip (delete). These stay legible whatever font/highlight color is
  selected.

### Status dialog
- No longer checks for updates itself (Check For Updates already does
  that). It shows the running version and, if a check has run this
  session, whether you're up to date / an update is available.
- Added "Refresh Games List On Exit: Pending / Not Necessary" so you
  can see at a glance whether your deletions/fetches will be reflected
  after exit.

## [1.0.0] - 2026-06-12

First stable release. Everything from the 0.62-0.64 development line
is consolidated here, and AmberELEC is now a fully supported firmware.

### Headline
- **AmberELEC support, for real.** The RG552 now runs Pocket Curator
  end to end: upright display via our own KMSDRM-enabled SDL build
  (libs.aarch64/pcsdl, SDL 2.28.4 built against an old-enough glibc),
  correctly-mapped controls through SDL's GameController API, and
  working fetch/delete/metadata. The earlier belief that AmberELEC
  "never worked and likely never would" has been overtaken by events.
- **Fetch from WebDAV.** Press Y on a system to browse a WebDAV server
  (saved, scanned on the LAN, or entered by address), mark games the
  same way you mark deletions, and copy them - with scrapings and full
  gamelist metadata injected into the destination, under strict
  backup-first / sorted-insertion / atomic-write rules with a Settings
  restore option.

### Display & input
- Own KMSDRM SDL build for firmwares whose system SDL is too old to
  preload and whose pygame SDL lacks kmsdrm; probed AmberELEC-first.
- Portrait-framebuffer auto-rotation (RG552 -> 270deg; PC_ROTATE
  overrides).
- Gamepad input via SDL GameController API on kmsdrm (standardized
  A/B/X/Y/d-pad from the firmware's own mapping), with raw-joystick
  fallback; Wayland/X11 keep compositor keyboard input.
- Firmware-preferred display probe ladder with a per-device probe
  cache; clean abort-to-ES (no wedge) when no driver works.

### Fetch experience
- Fetch screens mirror the deletion screens: same layout, headers
  (FETCH FROM WebDAV / MARK FOR DELETE), hold-A mass-mark, wrap-on-tap,
  upscaled previews, autoscrolling descriptions with L2/R2.
- Mark-time existence check (green + for new, yellow ? for already on
  device); Overwrite/Skip confirmation with per-option sizes, free
  space, and a fit check.
- One session queue with per-job destinations; enqueue more mid-copy.
- ~60-group cross-firmware folder alias matrix (megadrive/genesis,
  jaguar/atarijaguar, etc.) with exact-first two-pass resolution;
  empty-but-present system folders are valid destinations.
- After-copy ATTENTION notice; region shown in proper caps.

### Reliability
- WebDAV read-only client with one-retry reconnect and a 15s timeout.
- In-app updater, one-file installer, precompiled bytecode, startup
  timing logs.

## [0.64.5] - 2026-06-11

### AmberELEC controls mapped correctly
v0.64.4 got input flowing on the RG552 but mapped it from RAW joystick
indices, which are device-specific: A/B came out swapped, the d-pad
was dead (the RG552 doesn't report it as a hat), and the shoulders /
triggers landed on the wrong actions.

- Pocket Curator now drives gamepad input through SDL's GameController
  API instead of raw joystick indices. The launcher exports the
  device's own SDL controller mapping (SDL_GAMECONTROLLERCONFIG, taken
  from the firmware's sdl_controllerconfig), so A/B/X/Y, the d-pad,
  shoulders, and triggers are all STANDARDIZED by SDL regardless of the
  pad's raw evdev order. The RG552's GO-Super Gamepad - and any other
  pad the firmware has a mapping for - now maps right: A confirms, B
  backs out, d-pad navigates, L1/R1 page, L2/R2 scroll the
  description, Select opens settings.
- Raw-joystick translation (v0.64.4's approach) remains as a fallback
  for any pad the firmware has no SDL mapping for, so input still works
  even there - just with the generic index layout.
- Unchanged on Wayland/X11 firmwares (ROCKNIX, Knulli): their
  compositor delivers the keyboard and neither gamepad path runs.

### If a button is still wrong
That would mean the firmware's SDL mapping itself disagrees with the
hardware on that pad. Capture the line the log prints
("game controller input on ...") and which button misbehaves, and it
can be corrected with a per-device mapping override.

## [0.64.4] - 2026-06-11

### AmberELEC controls + rotation direction
Follow-up to v0.64.3's display work on the RG552.

- **Controls now work on kmsdrm.** v0.64.3's joystick init confirmed
  the gamepad is visible, but the buttons were still dead because of a
  known SDL limitation (libsdl-org #2418 / #15166): on kmsdrm SDL only
  grabs keyboard input when the app owns the active VT, which a
  PortMaster-launched child of EmulationStation does not - so SDL sees
  the GAMEPAD but never the keyboard, including gptokeyb's uinput keys.
  Pocket Curator now reads the gamepad directly as a joystick on
  kmsdrm and translates its buttons, d-pad/hat, and analog stick into
  the same key events the screens already use (A->Enter, B->Esc,
  X/Y, L1/R1->PgUp/PgDn, L2/R2->[/], Select->settings, Start, d-pad ->
  arrows). Wayland/X11 firmwares (ROCKNIX, Knulli) are untouched -
  their compositor still delivers the keyboard and the joystick path
  stays off, so there's no double input.
- **Rotation corrected.** v0.64.3 rotated the RG552 the wrong way
  (ended up 180deg off). The portrait-panel default is now 270deg,
  which brings the UI upright. PC_ROTATE still overrides per device if
  a particular panel differs.

### Note for AmberELEC testers
With this build the RG552 should be upright AND controllable. If the
angle is still off, set PC_ROTATE (0/90/180/270) in the launcher; if a
button is mismapped on a specific pad, that's the joystick button
index table in app.py.

## [0.64.3] - 2026-06-11

### AmberELEC display works - now upright, with working controls
The v0.64.2 pcsdl build got the RG552 to a picture at last
(`display.init(): OK (KMSDRM)`), exposing two follow-on issues that
this release fixes.

- **Rotation.** The RG552's panel is physically landscape but KMSDRM
  exposes it as a 1152x1920 PORTRAIT framebuffer, so the UI rendered
  sideways (90deg clockwise). Pocket Curator now draws into a logical
  LANDSCAPE surface and rotate-blits it onto the real display every
  frame, so nothing in the UI code has to know the panel is turned.
  Portrait framebuffers auto-rotate 90deg; a new PC_ROTATE env
  (0/90/180/270) overrides per device, and the launcher sets
  PC_ROTATE=90 for the RG552 by default. ROCKNIX/Knulli/dArkOS, whose
  framebuffers are already landscape, are unaffected (no rotation, the
  logical surface IS the display - zero overhead).
- **Dead controls on kmsdrm.** With no compositor to deliver key
  events (unlike wayland/x11), SDL must read the kernel input devices
  itself - including gptokeyb's uinput keyboard - through its evdev
  backend, which only starts once the joystick subsystem is
  initialized. Pocket Curator initialized only display and font (to
  avoid the heavy audio mixer the umbrella init pulls in), so on the
  kmsdrm path no input was ever read. It now brings up the joystick
  subsystem whenever the driver isn't wayland/x11, so the buttons work
  on AmberELEC. The mixer is still never loaded.

### Note for AmberELEC testers
This is the first build expected to be fully usable on the RG552:
upright display and working controls via Pocket Curator's own kmsdrm
SDL (libs.aarch64/pcsdl). If your panel comes up at a wrong angle,
set PC_ROTATE in the launcher.

## [0.64.2] - 2026-06-11

### AmberELEC: the SDL build now actually loads
- v0.64.1's `pcsdl` SDL was rejected by the RG552's loader before
  kmsdrm could even be tried: `GLIBC_2.38 not found in libm.so.6 /
  libc.so.6`. Root cause: Ubuntu's stock gcc-aarch64-linux-gnu links
  its OWN glibc (2.38) into every binary regardless of --sysroot, so
  the .so demanded a glibc newer than the device has.
- Fixed by rebuilding with Bootlin's 2018.11 aarch64 toolchain, whose
  glibc baseline is 2.27. The shipped `libs.aarch64/pcsdl/
  libSDL2-2.0.so.0` now tops out at GLIBC_2.27 (three `*f` math
  symbols) - comfortably below any AmberELEC/ROCKNIX/dArkOS runtime
  (the device already loads SDL 2.32 system libraries and the bundled
  pygame's own SDL, which needs only 2.17). KMSDRM is compiled in
  (dlopen mode); libdrm/libgbm/EGL/GLES resolve from the device's
  /usr/lib at runtime. tools/build_pcsdl.sh documents the toolchain
  requirement so this isn't relearned.

### Fetch destinations: empty system folders count
- Marking a Jaguar game and hitting Copy no longer says "can't copy
  here" when the device has an empty roms/atarijaguar folder. System
  discovery still needs >=1 ROM to SHOW a system, but a fetch
  DESTINATION only needs the folder to exist on disk - so empty,
  ready-to-fill system folders are now valid copy targets. Applied to
  both the EmulationStation and filesystem-fallback discovery paths.

### Free space
- The free-space figure is computed against the nearest existing
  ancestor of the destination, so an empty-but-new system folder
  reports the real roms-mount free space instead of misresolving.

### Region display
- Regions are shown in conventional caps on the fetch panel: US, EU,
  JP, Japan, Europe, World, etc., instead of lowercase us/eu/jp.
  Multi-region strings keep their separators (USA, Europe).

### After-copy notice
- Reworded to the agreed text, headed "ATTENTION": "The games you
  just downloaded are NOT in the games lists yet. Not in Emulation
  Station or Pocket Curator. They will appear after the games lists
  refresh, which happens when you exit Pocket Curator."

### WebDAV connection robustness
- A single transient socket failure was surfacing as "the server
  isn't answering" while the server was demonstrably up. Requests now
  retry once on a fresh connection after a short pause, and the
  default timeout is 15s (was 10s) to accommodate a handheld radio
  negotiating its first connection.

## [0.64.1] - 2026-06-11

### AmberELEC: we built the missing SDL
- Binary analysis settled the display mystery's mechanics: the pygame
  wheel's bundled SDL contains ONLY wayland/dummy/offscreen video
  drivers (verified with `strings` on the .so) - the bundled-kmsdrm
  probes could never pass on any device. dArkOS works because its
  system SDL (2.32) is accepted as an upgrade preload; AmberELEC's
  (2.26.2) is refused as a downgrade, leaving no viable combination.
  The eyewitness v0.61.13 success on the RG552 is fully consistent
  with the device having run an AmberELEC build with a newer system
  SDL at the time (nightly vs stable carry different SDL versions) -
  worth checking which build that card runs now.
- The fix removes the dependency on whatever the firmware ships:
  `libs.aarch64/pcsdl/libSDL2-2.0.so.0` is our own SDL **2.28.4**
  cross-compiled for aarch64 with KMSDRM enabled in dlopen mode. The
  version exactly matches the bundled pygame's SDL, so the preload
  passes pygame's check everywhere; libdrm/libgbm/EGL/GLES resolve at
  runtime from the device's own /usr/lib. It lives in a subdirectory
  deliberately, so it never shadows pygame's SDL on firmwares that
  don't need it. AmberELEC's preferred probe now tries it first; it's
  also a general ladder fallback. Rebuild recipe ships at
  tools/build_pcsdl.sh.

### Folder translation matrix, done properly
- ~60 alias groups grounded in the firmware naming families
  (Batocera/Knulli bare names vs ROCKNIX/AmberELEC/ArkOS atari-
  prefixed and region-variant names): jaguar=atarijaguar,
  lynx=atarilynx, nes=famicom, snes=sfc, megadrive=genesis=md,
  pcengine=tg16, psx=ps1, dos=msdos, amigacd32=cd32, gw=gameandwatch,
  channelf=fairchild, cdi=cdimono1, and the rest of the catalog.
- The lookup is now TWO-PASS: exact shortnames and folder leafs claim
  their names first, aliases only fill gaps - critical on ROCKNIX,
  which ships region variants as separate systems (both megadrive AND
  genesis): a remote genesis folder now maps to the device's genesis,
  never megadrive-by-alias.

### The silent mid-copy enqueue, fixed at the root
- There is now ONE fetch queue per session and every job carries its
  own destination system. Marking more games while a copy runs - same
  system or a different one - simply joins the live queue and grows
  the progress bar. The old per-destination queue refused cross-
  system enqueues with a toast that the progress bar was hiding.
- Toasts now REPLACE the progress text line for their few seconds
  instead of being drawn under it - refusals and notices are visible
  mid-copy, never silent again.

### Copy confirmation
- Short wrapped title ("Copy 302 games to Game Gear?"); the sizes
  moved onto the options themselves: "Copy w/ Scrapings (78.4 MB)" /
  "Copy (ROMs only) (52.3 MB)" - scrapings size is computed from the
  cached media listings up front.
- "Free space: X GB" along the bottom above the help text, with a
  warning when the scrapings copy won't fit - and a hard stop if a
  copy that doesn't fit is selected.

### Fetch right panel, reworked
- Filesize moved up to the header line (right-justified) - no longer
  costs a line under the image.
- Five stars ALWAYS draw (empty outlines when unrated), like the
  deletion screen.
- Image area trimmed 0.70 -> 0.64 of the panel: three description
  lines now visible.
- The description autoscrolls when idle and L2/R2 page it manually -
  the deletion screen's exact mechanism, including the pause-at-end /
  snap-to-top cycle and reset on selection change.

### Exit path
- On a successful connection the intermediate screens (network scan
  results) collapse, so the browser sits directly above the source
  picker: backing out lands on the live server list - which includes
  the server just used - with no stale scan dialog in between.

## [0.64.0] - 2026-06-11

### Gamelist metadata injection (new - the gamelist rule, amended)
- Copy w/ Scrapings now also injects the fetched games' metadata
  (name, description, image/video paths, rating, genre, region...)
  into the destination system's gamelist.xml, so games arrive fully
  described instead of waiting for a rescrape. This is the second
  sanctioned gamelist writer (after our own Ports entry) and follows
  the same proven machinery, under strict rules:
  - BACKUP FIRST: before the first merge touches a system in a
    session, its gamelist.xml is copied to
    pocketcurator/backups/gamelists/ (three most recent kept), and a
    new Settings -> Restore Gamelist Backup option puts one back.
  - ORDERED INSERTION, never a blind append: new entries land
    alphabetically by name among the existing entries; existing
    entries and non-game blocks are not moved or modified.
  - Overwrite replaces only that game's entry, in place; Skip leaves
    the user's entry untouched. Source-history fields (playcount,
    lastplayed, favorite) and unknown tags are dropped.
  - Atomic temp+rename writes; any failure logs and never disturbs
    the completed copy.

### Mark-time existence + visuals
- Whether a marked game already exists on the device is now checked
  when you MARK it: already-present games get a yellow ? and yellow
  text instead of the green plus, and the Overwrite/Skip question at
  copy time lists how many are affected.

### Dialogs and headers
- Screen headers are now large, centered, and color-coded: MARK FOR
  DELETE in white on red, FETCH FROM WebDAV in white on dark green.
- New NoticeScreen: full-reading-size body text with the OK bar
  pinned to the dialog bottom. The after-copy notice now says what it
  means: the copied games are NOT in any games list yet - not ES, not
  the delete lists - until the refresh on exit.
- X with no matching destination now opens a proper dialog ("Your
  device does not have a matching roms folder for this game system.
  These files can't be copied." / A Cancel) and clears the marks on
  dismissal, instead of a tiny legend toast.
- The fetch right panel now shows region and genre (gamelist tags,
  with the (USA)-style filename region as fallback).

### Folder-name translation layer
- Remote folders now map to local systems across firmware naming
  conventions: megadrive<->genesis, pcengine<->tg16, nes<->famicom,
  snes<->sfc, gb<->gameboy, lynx<->atarilynx, psx<->ps1,
  segacd<->megacd, arcade<->mame, wswan<->wonderswan, and ~20 more
  groups - applied to both destination mapping and smart-jump.

### Fetch flow
- The source picker is now always the entry screen, with known
  servers at the top, then Scan The Local Network and Enter An
  Address; the list rebuilds live, so a server you just used is on it
  when you back out of the browser.

### AmberELEC - the record, corrected
- Transcript review shows the v0.61.13 release notes overstated
  AmberELEC support: no log in the project's history shows a passing
  display preflight on the RG552, and no test ever confirmed a
  picture. The v0.61.10 probe-ordering change was a theory; v0.62.2+
  logs disproved it (the bundled pygame SDL contains no kmsdrm
  driver, and AmberELEC's system SDL 2.26.2 is a refused downgrade).
- Two new probe candidates that could genuinely light it up: a
  find-based scan for any PortMaster-shipped libSDL2 on the device
  (the previous fixed paths found none), and - the promising one -
  the Pyxel runtime's OWN pygame, which PortMaster builds per-device
  and which our bundled copy normally shadows via PYTHONPATH. Two
  ladder entries now probe kmsdrm/x11 with our libs dropped from
  PYTHONPATH so the runtime's pygame loads instead.

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
