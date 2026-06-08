# Pocket Curator

On-device ROM and scraped-media cleanup for retro handhelds. Browse your
systems and games in an EmulationStation-style interface and delete ROMs
together with their scraped artwork — no PC, no SSH, no pulling the card.

Full documentation, screenshots, and releases:
https://github.com/tomtombombadil/pocketcurator

## Controls

**Systems carousel:** Left/Right choose · A enter · X delete whole system ·
Select settings · B exit.

**Games list:** Up/Down move · L1/R1 page · A mark/unmark · X delete marked ·
Y jump · L2/R2 scroll description · Select settings · B back.

## What gets deleted

For each marked game: the ROM, plus the `<image>`, `<thumbnail>`,
`<marquee>`, `<video>`, and `<manual>` that the system's `gamelist.xml`
explicitly lists for it. Only files named in the gamelist entry are touched.
**Safe Mode** (Settings) logs what would be deleted without removing
anything; **Delete scraped media** (Settings) can be turned off to remove
ROMs only.

After deleting, Pocket Curator refreshes EmulationStation automatically on
exit, so removed games drop from the menu — no manual rescan.

## Pocket Curator's own icon/description

Run **PocketCuratorMetadataInstall** from your Ports menu once, then let
EmulationStation sit at its menu for ~20 seconds. Pocket Curator's entry
fills in with a screenshot, description, logo, and preview video.

## Firmware

Primary: ROCKNIX. Secondary: Knulli. Other PortMaster aarch64 firmwares
(muOS, ArkOS, JELOS, AmberELEC) should work but are unverified. Requires
PortMaster; the Python 3.11 runtime downloads on first launch (Wi-Fi needed
once).

## Credits / license

MIT licensed (see repository `LICENSE`). Thanks to the PortMaster team.
Bundled Oxanium font under SIL OFL 1.1 (`licenses/Oxanium-OFL.txt`); pygame
under LGPL (`licenses/pygame-LGPL.txt`).
