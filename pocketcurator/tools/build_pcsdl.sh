#!/bin/bash
# Reproduces libs.aarch64/pcsdl/libSDL2-2.0.so.0 on an x86_64 Ubuntu
# host. SDL's kmsdrm driver dlopens libdrm/libgbm at runtime, so only
# their headers (plus stub libs for the configure link check) are
# needed at build time - taken from Ubuntu's arm64 port packages.
set -e
apt-get install -y gcc-aarch64-linux-gnu
mkdir -p /tmp/sdlbuild/sysroot && cd /tmp/sdlbuild
B=http://ports.ubuntu.com/pool/main
curl -sfLO $B/libd/libdrm/libdrm-dev_2.4.120-2build1_arm64.deb
curl -sfLO $B/libd/libdrm/libdrm2_2.4.120-2build1_arm64.deb
curl -sfLO $B/m/mesa/libgbm-dev_24.0.5-1ubuntu1_arm64.deb
curl -sfLO $B/m/mesa/libgbm1_24.0.5-1ubuntu1_arm64.deb
for d in *.deb; do dpkg -x "$d" sysroot; done
SYS=/tmp/sdlbuild/sysroot
mkdir -p $SYS/usr/lib/pkgconfig
printf 'prefix=%s/usr\nlibdir=%s/usr/lib/aarch64-linux-gnu\nincludedir=%s/usr/include\nName: libdrm\nDescription: drm\nVersion: 2.4.120\nLibs: -L${libdir} -ldrm\nCflags: -I${includedir} -I${includedir}/libdrm\n' $SYS $SYS $SYS > $SYS/usr/lib/pkgconfig/libdrm.pc
printf 'prefix=%s/usr\nlibdir=%s/usr/lib/aarch64-linux-gnu\nincludedir=%s/usr/include\nName: gbm\nDescription: gbm\nVersion: 24.0.5\nLibs: -L${libdir} -lgbm\nCflags: -I${includedir}\n' $SYS $SYS $SYS > $SYS/usr/lib/pkgconfig/gbm.pc
curl -sfLO https://github.com/libsdl-org/SDL/releases/download/release-2.28.4/SDL2-2.28.4.tar.gz
tar xzf SDL2-2.28.4.tar.gz && cd SDL2-2.28.4
PKG_CONFIG_PATH=$SYS/usr/lib/pkgconfig PKG_CONFIG_LIBDIR=$SYS/usr/lib/pkgconfig \
./configure --host=aarch64-linux-gnu \
  --enable-video-kmsdrm --enable-kmsdrm-shared \
  --disable-video-wayland --disable-video-x11 --disable-video-vulkan \
  --disable-pulseaudio --disable-pipewire --disable-jack --disable-sndio \
  --enable-alsa --enable-alsa-shared --disable-oss \
  --disable-libudev --disable-dbus --disable-ibus --disable-fcitx \
  CFLAGS="-O2 -I$SYS/usr/include -I$SYS/usr/include/libdrm" \
  LDFLAGS="-L$SYS/usr/lib/aarch64-linux-gnu"
make -j4
aarch64-linux-gnu-strip build/.libs/libSDL2-2.0.so.0.2800.4
echo "artifact: build/.libs/libSDL2-2.0.so.0.2800.4"
