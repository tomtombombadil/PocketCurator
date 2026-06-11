# Pocket Curator v0.63.0 (beta)

## Which file do I want?

- If you CAN connect your handheld to the Internet: the only file you need is the **`PocketCurator.Installer.sh`** listed below. Place it in your roms/ports folder and run it from within Emulation Station's Ports games list. Pocket Curator's installer will connect here and download and install the package for you. (see the repo page's README for more on how to install)
- If you CANNOT connect your device to the Internet: you want the .zip file below. To install without Internet, unzip the .zip file to your roms/ports folder on your SD card. (see the repo page's README for more on how to install)
- If you have Pocket Curator v0.62.0 or later installed: just open **Settings -> Check For Updates** inside Pocket Curator.
- Ignore the "Source code" links below, unless you like reading code.

## What's new

- **Fetch ROMs over WiFi.** Highlight a system and press **Y** to copy games onto your handheld from a WebDAV or plain-HTTP server on your network - your NAS, or any computer running a one-line file server. Pocket Curator finds servers on your network (or you type an address on the new on-screen keyboard, which has one-press keys for things like '192.168.' and ':5005'), jumps straight to that system's folder on the server, and lets you mark games exactly the way you mark them for deletion. Press X, choose **Copy w/ Scrapings**, and the games arrive with their box art, videos, and manuals - pulled precisely, using the server's own gamelist.xml when it has one. Copies run in the background with a progress line ("Copying 4/10"), survive cancels and power cuts cleanly, and resume if interrupted.
- **Read-only by design.** Pocket Curator can only ever download from your server - the code physically contains no way to change, move, or delete anything on it.
- **Your settings stay yours.** Server addresses and usernames are remembered; passwords are never saved to disk.

Serving ROMs is a one-time setup on the other end: tick "Enable WebDAV" on a Synology/QNAP/TrueNAS box, or run `rclone serve webdav /path/to/roms --read-only` (or even `python -m http.server`) on any computer.
