pcsdl: Pocket Curator's own SDL2 build
======================================
libSDL2-2.0.so.0 here is SDL 2.28.4 cross-compiled for aarch64 with
the KMSDRM video driver enabled in dynamic (dlopen) mode. It exists
because the pygame wheel's bundled SDL contains only wayland/dummy/
offscreen drivers, and some firmwares (AmberELEC) have a system SDL
too old (2.26.x) for pygame to accept as a preload.

- Version 2.28.4 exactly matches the bundled pygame's SDL, so
  LD_PRELOADing it passes pygame's version check everywhere.
- KMSDRM, EGL, and GLES are resolved at runtime via dlopen of the
  device's own /usr/lib libraries (libdrm.so.2, libgbm.so.1,
  libEGL.so.1, libGLESv2.so.2) - nothing else is bundled.
- It lives in this subdirectory ON PURPOSE: libs.aarch64 itself is on
  LD_LIBRARY_PATH, and a libSDL2 directly there would shadow pygame's
  vendored SDL on every firmware. Here it loads only when a probe
  explicitly LD_PRELOADs it.

Rebuild recipe: tools/build_pcsdl.sh
