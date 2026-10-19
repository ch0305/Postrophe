#!/bin/sh
# Build and run Postrophe from this source tree (development profile).
#
# One-time dependencies (Ubuntu/Debian):
#   sudo apt install meson sassc libhandy-1-dev libgirepository1.0-dev gettext \
#       libgtk-3-dev gir1.2-webkit2-4.1 pandoc python3-gi
#
# Notes:
#  - The app must be started with the system Python (/usr/bin/python3):
#    the PATH python may be a uv/cpython build without PyGObject.
#  - postrophe/config.py is generated here (local run only). Delete it
#    before running `sudo ninja -C builddir install` or `./make-deb.sh`.

set -e
cd "$(dirname "$0")"

if ! command -v meson >/dev/null 2>&1; then
    echo "缺少 meson： sudo apt install meson" >&2
    exit 1
fi
if ! /usr/bin/python3 -c 'import gi' >/dev/null 2>&1; then
    echo "缺少 PyGObject： sudo apt install python3-gi" >&2
    exit 1
fi

if [ ! -f builddir/build.ninja ]; then
    if [ -d builddir ]; then
        rm -rf builddir
    fi
    meson setup builddir --prefix=/usr -Dprofile=development
fi

ninja -C builddir

# config.py is normally produced for installation only; copy it into the
# package so that `from postrophe import config` works when running from
# the source tree, and point PKGDATA_DIR at the source data dir so that
# lua/ and media/ are found there.
cp builddir/config.py postrophe/config.py
sed -i "s|^PKGDATA_DIR = .*|PKGDATA_DIR = \"$PWD/data\"|" postrophe/config.py

# The local launcher adds builddir/data to XDG_DATA_DIRS; the compiled
# schemas must exist there for GSettings.
mkdir -p builddir/data/glib-2.0/schemas
glib-compile-schemas data --targetdir=builddir/data/glib-2.0/schemas >/dev/null

exec /usr/bin/python3 ./builddir/local-postrophe "$@"
