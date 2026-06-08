# Build notes

## Bundled pygame wheel

The launcher mounts PortMaster's Python 3.11 runtime (the Pyxel
squashfs) and prepends `libs.aarch64/` (or `libs.armhf/`) to
`PYTHONPATH`. We rely on those directories containing the `pygame`
package so the Python in the runtime can `import pygame`.

To populate `libs.aarch64/` for a release:

1. Download an aarch64 manylinux wheel for Python 3.11 from PyPI, e.g.
   ```
   pygame-2.5.2-cp311-cp311-manylinux_2_17_aarch64.manylinux2014_aarch64.whl
   ```
   Source: <https://pypi.org/project/pygame/2.5.2/#files>

2. A wheel is a zip - unpack it:
   ```
   unzip pygame-2.5.2-cp311-cp311-manylinux_2_17_aarch64.manylinux2014_aarch64.whl \
         -d /tmp/pygame_wheel
   ```

3. Copy just the `pygame/` directory (and its `pygame-*.dist-info/`
   sibling if you want metadata) into the port's `libs.aarch64/`:
   ```
   cp -r /tmp/pygame_wheel/pygame                          pocketcurator/libs.aarch64/
   cp -r /tmp/pygame_wheel/pygame-2.5.2.dist-info          pocketcurator/libs.aarch64/
   ```

4. The `pygame.libs/` directory packed alongside the wheel (containing
   extra `.so` files like libSDL2) should also be copied if present:
   ```
   cp -r /tmp/pygame_wheel/pygame.libs                     pocketcurator/libs.aarch64/ 2>/dev/null
   ```

5. Test by running, on the device:
   ```
   /home/$USER/pyxel/bin/python3 -c "import pygame; print(pygame.version.ver)"
   ```
   It should print the version with no traceback.

For `libs.armhf/`, pygame does not publish armhf wheels on PyPI. You
will need to build from source inside a 32-bit ARM chroot, or wait for
a community build. Once you have an armhf pygame, the same directory
layout applies.

## Fonts

Pocket Curator bundles **Oxanium** (Severin Meyer, SIL OFL v1.1) at
`pocketcurator/assets/fonts/Oxanium-Medium.ttf` and `Oxanium-Bold.ttf`.
The license travels with the fonts in `pocketcurator/licenses/`.

If you want to swap fonts: drop replacement TTFs with the same filenames
into `assets/fonts/`. The app accepts any TTF; the bold weight is used
for headings on the system carousel.

## Cover, screenshots, and video

Pocket Curator's own gamelist entry (`gameinfo.xml`, and what
`PocketCuratorMetadataInstall.sh` writes) references the bundled assets in
`pocketcurator/assets/`:

- `Screenshot-GamesList.jpg` - `<image>` and `<thumbnail>`
- `Screenshot-Systems.jpg` - `<titleshot>`
- `splash.jpg` - `<marquee>` (logo)
- `PocketCurator.mp4` - `<video>` preview (converted from a GIF; H.264 /
  yuv420p so EmulationStation can play it)

These are captured on a real device at 640x480. If the PortMaster store
ever picks this up, that submission additionally expects a `screenshot.png`
at the port root (640x480, 4:3); it isn't needed for GitHub distribution.

## System logos

Pocket Curator does NOT bundle system logos. At runtime it detects the
active Emulation Station theme and reads logos from its directory. The
detection lives in `pocketcurator/curator/theme.py`. Theme path
templates currently understood:

- Knulli: `_inc/logos/<system>/logo.png`
- Art Book Next, Canvas: `<system>/art/system.png` / `logo.png`
- es-theme-basic and derivatives: `<system>/logo.png`
- A few less common patterns

If a popular theme isn't recognised, add its convention to
`LOGO_PATH_TEMPLATES` in `theme.py` and submit a PR.

## Sanity check

To run on a desktop (Linux or Windows with WSL) for fast iteration:

```
set POCKETCURATOR_ROMS_DIR=C:\path\to\fake\roms
set POCKETCURATOR_FULLSCREEN=0
python pocketcurator\main.py
```

`POCKETCURATOR_ROMS_DIR` overrides the firmware detection.
`POCKETCURATOR_FULLSCREEN=0` runs in a window so you can keep your IDE
visible.
