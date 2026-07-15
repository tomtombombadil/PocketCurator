# Pocket Curator

**An on-device ROM and scraped-media cleanup and download tool for retro handhelds.**
That's right! It says DOWNLOAD. Pocket Curator not only helps you clean up your ROMs collection, now you can download ROMs direct from your device! (WebDAV support added for v1.0)
Curate your device's ROMs in an Emulation Station-style interface. See the screenshots, read the description, see the stars rating and genre and region info. Make decisions based on more than just the game title. You can mark and delete ROMs in an easy to use familiar interface. No extra button pushes. No menus to scroll through. You can also connect to a WebDAV server and copy ROMs from it to your device... WITH scraped media, manuals, and metadata! All directly on your device. No removing the SD card. No console commands. No Samba share. No hassles.
   - Initial installation requires you to get the install file onto your device's SD card. This will likely involve another device (PC or phone with a card reader).
   - After you install, Internet connectivity is unnecessary
   - Built-in online updater requires Internet connectivity to update Pocket Curator (you CAN update manually instead)
   - Copying ROMs from a WebDAV server obviously requires WiFi

![Splash](pocketcurator/assets/splash.jpg)
![Systems carousel](pocketcurator/assets/Screenshot-Systems.jpg)
![Games list](pocketcurator/assets/Screenshot-GamesList.jpg)

## Why This Exists

Because weeding your ROMs collection on your device is a pain in the rear. And getting ROMs onto your device can be a challenge too. Pocket Curator makes it MUCH easier.

You probably have THOUSANDS of ROMs. No one can remember what they all are by filename. (and don't get me started on those MAME filenames!) Making decisions about ROMs needs metadata, screenshots, visuals. Pocket Curator gives you that. Whether you're deleting unneeded ROMs from your device or copying more ROMs to your device, Pocket Curator has you covered.

Pocket Curator as TWO 'modes': Delete and Fetch

Delete Mode helps you:
   - Trim the fat from your collection right on the device
   - Gives you a visual way to remove ROMs you don't want
   - Shows the ROM's screenshot and description and details letting you make an informed decision
   - Deletes not only the ROM files, but also the scraped files associated with the ROM, giving you precious space back
   - Multiple deletes are EASY! No faffing about through menus. No wearing your thumbs out.
   - Mark as many ROMs for deletion as you want, then with two button presses delete the all the marked ROMs and their scraped files.

Fetch Mode helps you:
   - Connect to a server with ROMs and copy them to your device (WebDAV only)
   - Shows you the screenshot and metadata of the ROMs you're looking to copy (assuming the server you connect to has the ROMs properly scraped!)
   - Copies the metadata and screenshot along with the ROMs (Pocket Curator calls them 'scrapings')
   - Finds the right folder for you, no scrolling through that long systems list, placing ROMs where they belong
   - Lets you copy 1 or a thousand files at once, showing a progress bar and a count
   - Copies files quickly at full HTTP speeds - no Samba overhead
   - Refreshes the games list for you, saving you faffing about in menus
   - Works on a freshly-installed device with no ROMs yet - connect to your server and pull your first games; the systems show up as soon as you copy games into them, no restart needed

**How does deleting ROMs work in Pocket Curator?**
Simple. You're in a visual interface that looks just like Emulation Station. (sorry, your themes aren't implemented) You scroll through the games list, just like you do in Emulation Station. Press A to mark a game to be deleted. Keep scrolling and marking. When you're done marking, press X to view a list of what you're about to delete and how much space you'll get back. Press X again to confirm the delete and the games and their scraped files are deleted. When you exit Pocket Curator, it automatically refreshes your games list. Easy, fast, and efficient!

**How does fetching ROMs work in Pocket Curator?**
Simple. From the System Selection screen, scroll to the system you want to copy ROMs to, then press the Y button. That opens a dialog allowing you to search the network for a WebDAV server or to enter your own server address. It even has some extra buttons to help you enter common IP addresses, like 1 button for 192.168. and 1 button for :5005 (common WebDAV port). Once you either select the server from the search or enter your own, it takes you right into the correct folder for the system you're looking to copy ROMs for. For example: if you're on the Game Boy Advance system on the system selection screen, press Y, enter your server, it connects and takes you into the roms\gba folder. When you mark games and copy them, it places those games in your device's roms/gba folder. When you exit Pocket Curator, it automatically runs Emulation Station's games list refresh routine, updating your games list and your new ROMs show up scraped and ready to go. (assuming the ROMs had scraped files on the WebDAV server).

Pocket Curator tries to be smart when you're copying games. When you mark a game to be copied, it checks your device to see if you already have it. If you do, it marks it with a ? and makes it yellow. If you don't already have it, it marks it with a + and makes it green. When you go ahead and tell it to copy (press X) it tells you if you've got duplicates selected and asks if you want to skip them. It also shows how much space you're going to take up with these copied games and how much you have left on your device, smartly not letting you try to copy more than your card can take.

Pocket Curator makes a couple assumptions about you and your ROM collection:
   - You already scraped all your ROMs (you might have gotten them that way from a vendor)
   - You have a bunch of ROMs that are just cluttering up your games lists preventing you from focusing on and playing the real gems
   - You just can't be bothered swapping your sd card back to your PC and installing/configuring programs to weed the collection over there
   - You just want an easier way to delete ROMs right from Emulation Station
   - You have a collection of ROMs on a PC or a NAS somewhere, and they are already scraped and sitting in folders just like you would have them on your device

## What Gets Deleted

For each marked game, Pocket Curator removes the ROM/zip file plus the media its `gamelist.xml` entry explicitly references — `<image>`, `<thumbnail>`, `<marquee>`, `<video>`, and `<manual>`. Only files named in the gamelist entry are touched.

## What Gets Copied (Fetched)

For each copied ROM, Pocket Curator checks the WebDAV server for gameslist.xml files. If it finds one in the system folder you're copying from, it will use the information there to find the scraped files that go with that ROM, and it will include the metadata that goes with that ROM. Including: screenshots, descriptions, ratings, region, genres, manuals, and probably more I can't think of right now.

## Targeted Firmwares

Pocket Curator was made for Rocknix, plain and simple. But I have enough other handhelds that I made it work with Knulli, dArkOS, Batocera, and AmberELEC as well.

   - Rocknix 2026-06-01 or later - RECOMMENDED
   - Knulli Scarab 2026-05-11 or later - RECOMMENDED
   - dArkOS 06072026 or later (only tested on R36S)
   - Batocera v39 2024-03-05 (only tested on RG552)
   - AmberELEC 2023-02-03 (last version, no updates since, only tested on RG552)
   
**Be sure to update your PortMaster installation as well as install the latest version of your firmware.** Without a recent version of both (firmware and PortMaster) Pocket Curator will likely fail. Previous versions of firmwares listed above are untested.

## Unsupported Firmwares

It is VERY unlikely that I will do any development for the below firmwares or any unlisted firmwares:

   - ArkOS - untested and unlikely to work. This OS is no longer in development.
   - EmuELEC - untested... it might work
   - GarlicOS - untested and unlikely to work
   - JELOS might work... (why haven't you upgraded to Rocknix? No plans to develop for or test on this firmware.)
   - MuOS - untested and unlikely to work
   - MinUI - untested and unlikely to work
   - OnionOS - untested and unlikely to work
   - PAN4ELEC - untested... it might work

(The number of untested/unsupported firmwares listed above are likely the reason this 'port' won't ever get picked up into the official
PortMaster repository. So Pocket Curator won't ever be downloadable through the PortMaster ports library)

## Requirements

   - Firmware that supports PortMaster
   - Retro Handheld with working Internet connection (obviously not all handhelds are supported, see list of tested handhelds below)
        - Caveat: you CAN manually install Pocket Curator without an Internet connection - just copy the release .zip file to your ports folder and unzip it
   - At least one other Port installed (often the Ports system won't show up on the systems carousel until you have an official PortMaster port installed, I recommend 2048. It's small and quick to install)
   - aarch64 libraries (don't worry, you probably won't know if you have these or not)

## Tested Handhelds (working!)

I have personally tested Pocket Curator on:

Anbernic:
   - RG CubeXX
   - RG 35xx H
   - RG 35xx SP
   - RG 40xx H & V
   - RG 552
   - BatleXP G350 (You will need a wifi dongle for installation!)

Powkiddy:
   - RGB10 MAX3
   - RGB20 Pro
   - RGB30
   - V10 (You will need a wifi dongle for installation!)
   - V90S (You will need a wifi dongle for installation!)
   - X35H (You will need a wifi dongle for installation!)
   - X55

TrimUI:
   - Brick
   - Brick Hammer
   - Smart Pro
   - Smart Pro S

Misc:
   - R36S (You will need a wifi dongle for installation!)
   - R36H (You will need a wifi dongle for installation!)
   - Kinhank K36 (You will need a wifi dongle for installation!)

I see no reason Pocket Curator would NOT work on any handheld that is supported by Rocknix or Knulli, so long as it uses the libs.aarch64 libraries and you can get the device connected to the Internet for the installation, it should work just fine. After installation, Pocket Curator operates without need for an Internet connection, a PC, or for you to remove your SD card. **You DO need an Internet connection for the update checker / update installer.**

## Quick Install Instructions

 1) Boot up your handheld and make sure you have:
     - up to date firmware
     - up to date PortMaster
     - at least ONE Port installed with PortMaster (or Ports won't show as a system in some firmwares)
     - a good connection to the Internet for your handheld (WiFi or even via USB tethering)
 2) Download the **`PocketCurator.Installer.sh`** from most recent release page. https://github.com/tomtombombadil/PocketCurator/releases
 3) Copy **`PocketCurator.Installer.sh`** to the **`roms/ports`** folder on your SD card. (You can do this via SSH, SCP, SAMBA, or simply remove the SD card and put it in your PC)
 4) From the Main Menu in Emulation Station, select GAME SETTINGS and UPDATE GAMESLISTS. This will refresh the list of your games, and make **`PocketCurator.Installer`** appear on your list of Ports.
 5) Go into the Ports system in Emulation Station, and highlight **`PocketCurator.Installer`** and press A to run it.
 6) PortMaster will connect to this github repository (via WiFi), show some installation messages, and install the latest release of Pocket Curator. When it finishes, Emulation Station will refresh your gameslist again.

That's it! Easy peasy lemon squeezy. ;)

## Controls

**Systems carousel:**
   - Left/Right - scroll through your game systems
   - A - Enter Delete Mode for the system you have selected
   - B - Exit Pocket Curator (offers a confirmation - press B again to exit any other button to not exit)
   - X - Delete that entire game system's ROMs!!! (it goes to a confirmation dialog, it won't delete anything on a first accidental press)
   - Y - Enter Fetch Mode - so you can copy ROMs to your device
   - Select - Settings Menu (you can auto-update Pocket Curator from here, change the font size, and more)

**Delete Mode Games list:**
   - Up/Down - scroll through your games
   - Left/Right - go to previous/next system's games list
   - A - mark/unmark a game for deletion (hold to mark lots of games at once!)
   - B - back to system selection / cancel action
   - X - delete marked games
   - Y - open alphabet, select letter to jump to that letter in your games list
   - L1/R1 - PgUp/PgDn in your games list
   - L2/R2 - scroll game description
   - Select - Settings
   - Start - Select All / Select None toggle

**Fetch Mode Games List**
   - Up/Down - scroll through your games
   - A - mark/unmark a game to be copied (hold to mark lots of games at once!)
   - B - move UP in WebDAV server's folder tree / cancel action
   - X - copy marked games
   - Y - open alphabet, select letter to jump to that letter in the games list
   - L1/R1 - PgUp/PgDn in your games list
   - L2/R2 - scroll game description
   - Select - Settings
   - Start - Select All / Select None toggle

## Settings

Pressing Select will take you to the Pocket Curator Settings screen. These settings are available:
   - Check For Updates - if you're connected to the Internet and your clock is set properly, it will check this GitHub repo for the latest version and install it for you
   - Status - shows your current version, the detected firmware version, where your ROMs are located, and free space on your SD card, the detected theme, if you're connected to the Internet, and your clock's status
   - Font Size - change the base font size in Pocket Curator's UI.
   - Font Color - change the text color in Pocket Curator's UI.
   - Highlight Color - change the color of the highlight bar in Pocket Curator's UI.
   - Swap Games List Side - Pocket Curator defaults to listing the games on the left ad showing the screenshot/metadata on the right. This has them swap places.
   - Delete Scraped Files with ROMs - this is enabled by default, turning it off will cause Pocket Curator to ONLY delete the game ROM/ZIP file. It will NOT delete the scraped files for that game.
   - Auto-Scroll Description - enabling this will cause the game descriptions on the games list to scroll automatically up and down
   - Rating Display - two options here Text or Stars. It controls which appears in games list display for the rating of the game: stars or a number.
   - Restore Games List Backup - any time Pocket Curator alters your games list (like when fetching ROMs and injecting metadata) it backs up the originals, just in case!

The Settings screen also shows a line of help text for the selected setting, and a line of help text for controls. Settings persist in `pocketcurator/settings.json`.

## System Logos

Pocket Curator ships **no** system logos of its own; it reads them from your installed themes the way EmulationStation does (at least MOST of the time!) If Pocket Curator can't find your theme's system logos it will fall back to the Rocknix/Knulli defaults. Pocket Curator also tries to determine your region so it can give you the correct system logos (for example: SNES for North America, and Super Famicom for Japan)

## WebDAV Servers

Pocket Curator now connects to WebDAV servers. Why WebDAV? Because its a simple protocol supported by just about everything. It's quick and easy, and it doesn't require complex authentication. I can't give instructions for every scenario out there, but here's what I see as THE most common situation: your ROM collection is stored on your computer. It doesn't matter if it is MacOS, Linux, or Windows. You can setup a WebDAV server with 1 simple command. First, go to the RCLONE repository here on github: https://github.com/rclone/rclone/releases and download RCLONE for your OS. Install it. (The install instructions are over there on that repository.) Once installed you start your server whenever you need to with one simple command. Here's the one I use for mine:

**`rclone serve webdav "C:\My\Folder\Where\My\ROMs\Are" --addr :5005 --read-only`**

That starts the WebDAV server and points it to my ROMs collection. I also does two VERY important things: it sets what port the WebDAV server communicates on, and it sets the server to READ-ONLY. That means no one can delete your ROMs or do nasty things to your PC. All they can do is copy files.

Next we have to talk about how to organize your ROMs in that folder you pointed to. Pocket Curator ASSUMES (I know, I know, ass-u-me...) that your ROMs are stored in the same type of folder tree as they are on your device. Some allowances are made for the slight differences between Batocera, Knulli, Rocknix, dArkOS, and AmberELEC. But the point is: you should have them stored in folders named like the system folders on your sd card. (In other words: gba for Game Boy Advance, nes for Nintendo Entertainment System, mame for MAME, etc.) Pocket Curator will try to guess when there are more than one option. For example: is it tg16 or pcengine? Is it genesis or megadrive? Pocket Curator looks at your set region and where you already have ROMs, and puts the games in the right places.

Chances are, you already have your ROMs sorted into folders like this with the scraped files and gameslist.xml files already because this is where you copy your files onto your sd card from. So if that's the case, you're ready to go! Point rclone at that roms folder and your WebDAV server is ready for Pocket Curator to copy games like a champ!

NOTE: for the scraped files that go with a ROM, Pocket Curator relies on the gameslist.xml file in that folder on your server. If there isn't one there, Pocket Curator won't know where to find the files and won't copy them.

## Troubleshooting

- **First launch errors about a runtime/download** — needs an Internet connection once; get your device connected and relaunch.

## Building / packaging

This port bundles the `pygame` wheel for aarch64. See
[`pocketcurator/BUILD.md`](pocketcurator/BUILD.md).

## Credits and license

Released under the **MIT License** — see [`LICENSE`](LICENSE). Thanks to the **PortMaster** team. Bundled **Oxanium** font under SIL OFL 1.1; `pygame` under the LGPL (see `pocketcurator/licenses/`).

Pocket Curator's code and development gratuitously used Claude.ai. I'm not a programmer, but using AI, I was able to put this together to fulfill a need I had. I hope you find it useful as well.
