# Pocket Curator v0.62.2 (beta)

## Which file do I want?

- If you CAN connect your handheld to the Internet: the only file you need is the **`PocketCurator.Installer.sh`** listed below. Place it in your roms/ports folder and run it from within Emulation Station's Ports games list. Pocket Curator's installer will connect here and download and install the package for you. (see the repo page's README for more on how to install)
- If you CANNOT connect your device to the Internet: you want the .zip file below. The **`PocketCurator.Installer.sh`** will NOT work without an Internet connection. To install without Internet, unzip the .zip file to your roms/ports folder on your SD card. (see the repo page's README for more on how to install)
- If you have Pocket Curator v0.62.0 or v0.62.1 installed: just open **Settings -> Check For Updates** inside Pocket Curator.
- If you have a version previous to v0.62.0 installed: delete it! (Delete **`Pocket Curator.sh`**, **`PocketCuratorMetadataInstall.sh`**, and the **`pocketcurator`** folder from your roms/ports folder on your SD card)
- Ignore the "Source code" links below, unless you like reading code.

## What's new

- **One-press updates.** Check For Updates now opens a Software Update dialog that does everything itself: it checks, and if a new version exists it downloads, verifies, and prepares it with no further button presses - then tells you to restart Pocket Curator to finish. You can close the dialog mid-download; it keeps going.
- **The log now tells the story.** Every update step is logged, and new startup timing lines show exactly how long each phase of launch took - so "it sat at the splash screen for a minute" becomes "the ROM scan of 14,000 games took 58 seconds," which is something we can actually act on.
- **Status dialog fits the screen.** Long lines (like the version row) now wrap instead of running off the panel.
