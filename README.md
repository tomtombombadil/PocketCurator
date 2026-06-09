# Pocket Curator

**An on-device ROM and scraped-media cleanup tool for retro handhelds.**
Browse your installed systems and games in an EmulationStation-style carousel,
then flag and delete ROMs together with their scraped artwork — no PC, no SSH,
no WiFi, and without pulling the SD card. (* installation requires WiFi and may require a PC)

![Splash](pocketcurator/assets/splash.jpg)
![Systems carousel](pocketcurator/assets/Screenshot-Systems.jpg)
![Games list](pocketcurator/assets/Screenshot-GamesList.jpg)

> **Status:** beta (v0.61.9). Extensively tested on Rocknix and Knulli. Other PortMaster
capable firmwares **may** work but are untested.

## Why This Exists

Most handheld firmwares let you delete a game from the menu. It's not a simple or quick
process. It usually involves holding a button, scrolling through a menu, and selecting
that item from the menu. That doesn't sound like a lot, and it isn't if you're only
deleting one game. But when you're trying to weed your collection, or trying to
make room for another large game, that's where Pocket Curator comes to the rescue!

Pocket Curator lets you scroll through your games lists just like Emulation Station.
Pocket Curator shows you the metadata including a screenshot, description, rating,
genre, and region. This lets you make an informed decision, rather than selecting
filenames on an SD card and hoping you got the right one - or worse not knowing
what that game even is. In a world where these handhelds ship with THOUSANDS of games
on them, this is a necessary tool to tidy up your games lists.

Pocket Curator lets you flag multiple files at a time! Delete them with two button presses.
One press of X and it shows you a list of what you're about to delete and how much space
you'll recover. Press X again to delete those games and all their scraped media. Press B
to cancel. It's intuitive and fast!

When Pocket Curator exits, it automatically updates your gameslist.xml files by making
Emulation Station refresh them. This removes the deleted games from the Emulation Station
lists, and saves you from the extra button pushing to go through the menus and refresh
the lists yourself.

Pocket Curator is a powerful deletion tool. You can even delete whole systems! Tired of
Game Boy Advance? One press of X at the systems carousel and a confirmation, and it will
delete all the games and scraped media for that game system! Be careful with this one.
There is no UNDELETE!

## What Gets Deleted

For each marked game, Pocket Curator removes the ROM/zip file plus the media its `gamelist.xml` entry explicitly references — `<image>`, `<thumbnail>`, `<marquee>`, `<video>`, and `<manual>`. Only files named in the gamelist entry are touched.

## Quick Install Instructions for Nerds Who Know What They're Doing

 1) Boot up your handheld and make sure you have:
     - up to date firmware
     - up to date PortMaster
     - at least ONE Port installed with PortMaster (or Ports won't show as a system in Rocknix)
     - a good WiFi connection to the Internet for your handheld
 2) Download the most recent release zip file from the link to the right
 3) Copy this zip file to your handheld's roms/ports folder (make sure you pick the right one, it can vary depending on if your ROMs are on the 'internal' sd card or the 'external' sd card). There's plenty of ways to do this. Feel free to use the samba connection, SSH, SCP, HTTP, or the old classic: remove the sd card and copy the file from your PC.
 4) SSH to the handheld and unzip the release zip file. It will create a pocketcurator folder (where all the goodies are) and two .sh scripts: Pocket Curator.sh (this is the one you use to start Pocket Curator) and PocketCuratorMetadataInstall.sh (this is the one you use to populate the Emulation Station metadata for Pocket Curator). You can delete the zip file after you unzip it. NOTE: It is recommended to SSH to the device and unzip the file there instead of unziping it on your PC and copying the files. (the console command is 'unzip' followed by the filename, ex: unzip pocketcurator_port-v0.61.9.zip) I've had trouble with Windows corrupting the python with CR/LF in places that should only be LF characters. You've been warned!
 5) On your handheld, go into the Emulation Station menu and refresh your games list (or reboot, or restart Emulation Station)
 6) Now in the Ports games list, you'll see Pocket Curator and the PocketCuratorMetadataInstall scripts as games. Start the PocketCuratorMetadataInstall one and give it a few seconds. You will see a message about it updating, then Emulation Station will refresh the gameslist. There may be a second or two pause between the message and ES refresh. Don't panic. ;) After the refresh, you can delete PocketCuratorMetadataInstall from your Ports games list (use the ES menu like you would normally)
 7) Now you're ready to start Pocket Curator. When you start it the first time it will stay on a blank screen for several seconds. This is normal. Don't panic! Pocket Curator is downloading resources via PortMaster (which is why it needs wifi for the first run).
 8) Then it will show the Pocket Curator splash screen. It will stay here for a few seconds as it scans your ROM collection. Depending on the size of your collection, it may take longer. When it's done, you're taken to a system selection carousel that should look very familiar.
 9) Use the typical dpad directions and buttons to navigate, just like in Emulation Station.
 10) When you exit, if you deleted any games, it will have Emulation Station refresh the games list.
     

## Supported firmware

   - Rocknix 2026-06-01 or later
   - Knulli Scarab 2026-05-11 or later
   
Recent versions of Rocknix and Knulli are tested and work great! Be sure to update your
PortMaster installation as well. Without a recent version of both (firmware and PortMaster)
Pocket Curator will fail.

   - Batocera (for handhelds) will likely work, but is untested.
   - AmberELEC will likely work, but it is untested.
   - JELOS might work... (why haven't you upgraded to Rocknix?)
   - dArkOS / ArkOS - untested and unlikely to work
   - MuOS - untested and unlikely to work

(All of the above are likely the reason this 'port' won't ever get picked up into the official
PortMaster repository. So Pocket Curator won't ever be downloadable through PortMaster)

## Supported Handhelds
Only **aarch64** handhelds! PortMaster is required!
This includes most of the handhelds released since 2024.

I have personally tested Pocket Curator on:

Anbernic:
   - RG CubeXX
   - RG 35xx H
   - RG 35xx SP
   - RG 40xx H & V
   - RG 552
   - BatleXP G350 (You will need a wifi dongle for the first run!)

Powkiddy:
   - RGB10 MAX3
   - RGB20 Pro
   - RGB30
   - V10 (You will need a wifi dongle for the first run!)
   - V90S (You will need a wifi dongle for the first run!)
   - X35H (You will need a wifi dongle for the first run!)
   - X55

TrimUI:
   - Brick
   - Brick Hammer
   - Smart Pro
   - Smart Pro S

Misc:
   - R36S (You will need a wifi dongle for the first run!)
   - R36H (You will need a wifi dongle for the first run!)
   - Kinhank K36 (You will need a wifi dongle for the first run!)

I see no reason Pocket Curator would NOT work on any handheld that is
   supported by Rocknix or Knulli, so long as it is a 64bit architecture
   and you can get the device on WiFi for the first run of Pocket Curator.
   After the first run, Pocket Curator operates without need for WiFi or
   a PC, or for you to remove your SD card.

## Installation

Pocket Curator is **not** in the PortMaster store, so it's installed manually —
a one-time copy. After the install and first run everything happens on the device.

   **Install instructions are still being written and tested!**
   **THANK YOU FOR YOUR PATIENCE!**

Multiple installation methods, depending on what you have at your disposal:

Method #1 - The SD Card Shuffle (we used to call it SneakerNet!)
   - Remove SD card and put in a PC with Internet
   - Download the Pocket Curator release zip file, unzip it to your roms/ports folder
   - Put SD card back in the handheld, make sure the handheld has a WiFi connection
   - Run Pocket Curator for the first time.
   - Don't panic! Pocket Curator will sit at a blank screen for a few moments the first time it runs. It has to download a couple resources via PortMaster.
   - After a few moments, you'll see the Pocket Curator splash screen.
   - It will scan your gameslists, then take you to a system selection carousel.

Method #2 - The USB Stick Shuffle
   - Download the Pocket Curator release zip file onto either your PC or your
   - Android phone or tablet. Even a Chromebook will work. (iPhone might work I'm not that familiar with Apple products)
   - Unzip the Pocket Curator on your PC/phone/tablet and copy the files to your USB stick.
   - Plug your USB stick into your handheld.
   - Use the built-in filemanager in the Tools section of your handheld to copy the files from your USB stick to your roms/ports folder.
   - Go to the Emulation Station menu and refresh your games list.
   - Pocket Curator will show up on your games list under the Ports system.
   - Run Pocket Curator. The first time you run it, you'll need a wifi and Internet connection so Pocket Curator can download some resources through PortMaster. It will sit at a blank screen for a few moments while it downloads.
   - Don't panic! The Pocket Curator splash screen will appear next while it scans your games lists. Then you'll be taken to a systems carousel, very similar to Emulation Station.

Method #3 - I'm a Nerd's Nerd! (SSH and SAMBA and CLI, oh my!)
   - Download the Pocket Curator release zip file on your PC.
   - Make sure your handheld is on and connected to your WiFi.
   - Make a note of your handheld's IP address in the Network Settings menu.
   - Make sure your handheld has SSH and SAMBA enabled in the settings.
   - On Windows, open a new File Explorer window and type \\ followed by your handheld's IP address. This will open the Samba share that is your handheld. Open the folders there, finding roms/ports folder.
   - Drag and drop the Pocket Curator zip file to the roms/ports folder.
   - Open an SSH client on your PC. (I prefer PuTTY!)
   - Connect to your handheld's IP address via SSH.
   - Login with your firmware's username and password. (Rocknix default is root and rocknix. Knulli default is root and linux.)
   - Change directory to the roms/ports folder. (This location will depend on whether you have one sd card or two and if you're running Rocknix or Knulli)
   - You'll see the Pocket Curator zip file there. Unzip it with this command:
            unzip pocketcurator_port-v0.61.9.zip <--- make sure to use the exact filename shown
                                                 in the directory. It likely includes the version.
   - Delete the zip file after it is done unzipping (rm pocketcurator_port-v0.61.9.zip)
   - Exit your SSH session. Close your file explorer window.
   - On your handheld, go to the Emulation Station Main Menu and select:
      Game Settings > Update Gameslist
   to refresh your handheld's games lists. The scroll through your systems to Ports, scroll down to Pocket Curator and select it to run it.
   - The first time it runs, it will sit at a blank screen for a long moment. Don't panic!
   - Pocket Curator is downloading resources via PortMaster so that it can run. This only happens on the first run of Pocket Curator, and you do not need WiFi after this to use Pocket Curator (and it won't take that long to load next time either!)
   

On Rocknix:
On first run, Pocket Curator downloads the Python runtime through PortMaster.
**This needs Wi-Fi the first time only** — afterwards it runs fully offline.

## Controls

**Systems carousel:**
   - Left/Right - scroll through your game systems
   - A - go to games list for that system
   - X - delete that game system (it goes to a confirmation dialog, it won't delete anything on an first accidental press)
   - B - exit Pocket Curator (offers a confirmation - press B again to exit)
   - Select - Settings

**Games list:**
   - Up/Down - scroll through your games
   - Left/Right - go to previous/next system's games list
   - A - mark/unmark a game for deletion (hold to mark lots of games at once!)
   - B - back to system selection / cancel action
   - X - delete marked games
   - Y - open alphabet, select letter to jump to that letter in your games list
   - L1/R1 - PgUp/PgDn in your games list
   - L2/R2 - scroll game description
   - Select - Settings

## Settings
Pressing Select will take you to the Pocket Curator Settings screen.
   - Font Size - changes the size of the font in Pocket Curator.
   - Auto-scroll description - enabling this will cause the game descriptions on the games list to scroll automatically up and down
   - Safe Mode - enabling this will cause Pocket Curator to NOT delete anything! You can use this to test it out without fear.
   - Delete Scraped Media - this is enabled by default, turning it off will cause Pocket Curator to ONLY delete the game ROM/ZIP file. It will NOT delete the scraped files for that game.
   - Rating Display - two options here Text & Stars. It controls which appears in games list display for the rating of the game: stars or a number.

The Settings screen also shows the running version of Pocket Curator (top right), the detected firmware (Rocknix, Knulli, etc.), the detected location/path to your games (ex: /storage/roms), the detected theme you're using with Emulation Station, a line of help text for the selected setting, and a line of help text for controls.

Settings persist in `pocketcurator/settings.json`.

## System Logos

Pocket Curator ships **no** logos of its own; it reads them from your installed themes the way EmulationStation does (at least MOST of the time!) If Pocket Curator can't find your theme's system logos it will fall back to the Rocknix/Knulli defaults. Pocket Curator also tries to determine your region so it can give you the correct system logos (for example: SNES for North America, and Super Famicom for Japan)

## Pocket Curator's Own Image & Description in Emulation Station

Out of the box, EmulationStation lists Pocket Curator without any metadata. <sad trombone noise> And typing in your own metadata (description, screenshot, splash screen, etc) is a real bummer. <another sad trombone noise> But fear not intrepid gamer! Pocket Curator has you covered. It has it's own **PocketCuratorMetadataInstall** script. You'll see it as another port in the Ports games list. Simply start it (press A) and it will update Pocket Curator's metadata with all the goodies (description, rating, genre, screenshots, etc.) then it will automagically tell Emulation Station to refresh the games list, cementing that metadata in place. After that, you can delete the **PocketCuratorMetadataInstall** entry in your games list using the boring old Emulation Station menu. 

   ## Nerd Knowledge
   
   - Why a separate metadata installer?
          EmulationStation rewrites each gamelist from memory whenever you return from a "game" (a port counts as a game), so metadata written while a port runs gets overwritten. The only moment a write survives is when ES is idle at its menu, so the installer schedules the write and an in-place gamelist reload to run a few seconds after it exits.
   - A fresh log is written to `pocketcurator/pocketcurator.log` each launch.
   - **`xkbcommon ... Compose ... UTF-8` lines in the log file** are harmless input-teardown noise, unrelated to Pocket Curator.
   
## Troubleshooting

- **First launch errors about a runtime/download** — needs Wi-Fi once; get
  online and relaunch.
- **No Screenshot or Video in the Games List** — run `PocketCuratorMetadataInstall` once and let it do it's thing, populating the metadata for Pocket Curator for you.

## Building / packaging

This port bundles the `pygame` wheel for aarch64. See
[`pocketcurator/BUILD.md`](pocketcurator/BUILD.md).

## Credits and license

Released under the **MIT License** — see [`LICENSE`](LICENSE). Thanks to the **PortMaster** team. Bundled **Oxanium** font under SIL OFL 1.1; `pygame` under the LGPL (see `pocketcurator/licenses/`).

Pocket Curator's code and development gratuitously used Claude.ai. I'm not a programmer, but using AI, I was able to put this together to fulfill a need I had. I hope you find it useful as well.
