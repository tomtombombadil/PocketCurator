# Changelog

All notable changes to Pocket Curator are documented here.

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
