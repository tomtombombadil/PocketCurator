# Pocket Curator v0.62.3 (beta)

## Which file do I want?

- If you CAN connect your handheld to the Internet: the only file you need is the **`PocketCurator.Installer.sh`** listed below. Place it in your roms/ports folder and run it from within Emulation Station's Ports games list. Pocket Curator's installer will connect here and download and install the package for you. (see the repo page's README for more on how to install)
- If you CANNOT connect your device to the Internet: you want the .zip file below. The **`PocketCurator.Installer.sh`** will NOT work without an Internet connection. To install without Internet, unzip the .zip file to your roms/ports folder on your SD card. (see the repo page's README for more on how to install)
- If you have Pocket Curator v0.62.0 or later installed: just open **Settings -> Check For Updates** inside Pocket Curator.
- If you have a version previous to v0.62.0 installed: delete it! (Delete **`Pocket Curator.sh`**, **`PocketCuratorMetadataInstall.sh`**, and the **`pocketcurator`** folder from your roms/ports folder on your SD card)
- Ignore the "Source code" links below, unless you like reading code.

## What's new

- **Faster first launches.** The first launch of a freshly installed or freshly updated version was doing extra one-time work (copying the update into place, compiling Python bytecode, cold SD reads) that could stretch into minutes on a big library and a slow card. Releases now ship precompiled bytecode, removing the compile step entirely, and the launcher log now timestamps every phase so any remaining slowness is measurable instead of mysterious. Day-to-day launches were already fast (the new timing lines clocked a 17,000-ROM library at 4 seconds) and are unchanged.
- **For the record:** Pocket Curator reads each system's gamelist.xml as the source of truth - it does not crawl your ROM folders - and it never writes to any gamelist.xml except to add its own entry to the Ports list. Deleting a game removes the game's files only; EmulationStation tidies its own lists.
- **Tidier ports folder.** The installer's log file now ends up inside the pocketcurator folder instead of loose in roms/ports.
