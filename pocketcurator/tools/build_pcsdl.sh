#!/bin/bash
# Reproduces libs.aarch64/pcsdl/libSDL2-2.0.so.0: SDL 2.28.4 for
# aarch64 with KMSDRM in dlopen mode, built against an OLD glibc so it
# loads on AmberELEC's runtime.
#
# The critical lesson (v0.64.1 -> v0.64.2): Ubuntu's stock
# gcc-aarch64-linux-gnu links its OWN modern glibc (2.38) regardless
# of --sysroot, so the .so demanded GLIBC_2.38 and the device's loader
# refused it before kmsdrm could even be tried. The fix is a toolchain
# whose glibc baseline is old. Bootlin's 2018.11 aarch64 toolchain
# ships glibc 2.27 - low enough for every AmberELEC/ROCKNIX/dArkOS
# build in the wild (the bundled pygame SDL itself needs only 2.17).
set -e
cd /tmp && rm -rf sdlbuild && mkdir sdlbuild && cd sdlbuild

# 1. old-glibc cross toolchain
curl -sfLO https://toolchains.bootlin.com/downloads/releases/toolchains/aarch64/tarballs/aarch64--glibc--stable-2018.11-1.tar.bz2
tar xjf aarch64--glibc--stable-2018.11-1.tar.bz2
BL=$PWD/aarch64--glibc--stable-2018.11-1
export PATH="$BL/bin:$PATH"
BLSYS="$BL/aarch64-buildroot-linux-gnu/sysroot"

# 2. libdrm + libgbm headers/stub-libs from Ubuntu's arm64 port (the
#    driver dlopens them at runtime; we only need them to link)
B=http://ports.ubuntu.com/pool/main
for u in $B/libd/libdrm/libdrm-dev_2.4.120-2build1_arm64.deb \
         $B/libd/libdrm/libdrm2_2.4.120-2build1_arm64.deb \
         $B/m/mesa/libgbm-dev_24.0.5-1ubuntu1_arm64.deb \
         $B/m/mesa/libgbm1_24.0.5-1ubuntu1_arm64.deb; do curl -sfLO "$u"; done
mkdir sr && for d in *.deb; do dpkg -x "$d" sr; done
cp -a sr/usr/include/libdrm "$BLSYS/usr/include/"
cp sr/usr/include/libdrm/*.h "$BLSYS/usr/include/"        # SDL includes them flat
cp sr/usr/include/gbm.h "$BLSYS/usr/include/"
cp -a sr/usr/include/EGL sr/usr/include/KHR "$BLSYS/usr/include/" 2>/dev/null || true
cp -a sr/usr/lib/aarch64-linux-gnu/libdrm.so* "$BLSYS/usr/lib/"
cp -a sr/usr/lib/aarch64-linux-gnu/libgbm.so* "$BLSYS/usr/lib/"
mkdir -p "$BLSYS/usr/lib/pkgconfig"
printf 'prefix=/usr\nlibdir=/usr/lib\nincludedir=/usr/include\nName: libdrm\nVersion: 2.4.120\nLibs: -L${libdir} -ldrm\nCflags: -I${includedir} -I${includedir}/libdrm\n' > "$BLSYS/usr/lib/pkgconfig/libdrm.pc"
printf 'prefix=/usr\nlibdir=/usr/lib\nincludedir=/usr/include\nName: gbm\nVersion: 24.0.5\nLibs: -L${libdir} -lgbm\nCflags: -I${includedir}\n' > "$BLSYS/usr/lib/pkgconfig/gbm.pc"

# 3. SDL
curl -sfLO https://github.com/libsdl-org/SDL/releases/download/release-2.28.4/SDL2-2.28.4.tar.gz
tar xzf SDL2-2.28.4.tar.gz && cd SDL2-2.28.4
export PKG_CONFIG_PATH="$BLSYS/usr/lib/pkgconfig" PKG_CONFIG_LIBDIR="$BLSYS/usr/lib/pkgconfig" PKG_CONFIG_SYSROOT_DIR="$BLSYS"
./configure --host=aarch64-linux-gnu CC=aarch64-linux-gcc \
  --enable-video-kmsdrm --enable-kmsdrm-shared \
  --disable-video-wayland --disable-video-x11 --disable-video-vulkan \
  --disable-pulseaudio --disable-pipewire --disable-jack --disable-sndio \
  --enable-alsa --enable-alsa-shared --disable-oss \
  --disable-libudev --disable-dbus --disable-ibus --disable-fcitx \
  CFLAGS="-O2 -I$BLSYS/usr/include/libdrm"
make -j4
aarch64-linux-gcc-strip build/.libs/libSDL2-2.0.so.0.2800.4 || \
  aarch64-linux-gnu-strip build/.libs/libSDL2-2.0.so.0.2800.4
echo "artifact: build/.libs/libSDL2-2.0.so.0.2800.4"
echo "verify  : aarch64-linux-gnu-objdump -T <artifact> | grep GLIBC | sort -V | tail -1   # expect <= 2.27"
