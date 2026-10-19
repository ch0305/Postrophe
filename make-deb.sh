#!/bin/sh
# Rebuild the Postrophe .deb from this source tree.
#
#   ./make-deb.sh
#   sudo apt install ./postrophe_<version>_amd64.deb
#
# The package replaces the distribution "apostrophe" package and the local
# "apostrophe-devel" development package (Conflicts/Replaces/Provides).
# To go back:
#   sudo apt remove postrophe && sudo apt install apostrophe
#
# VERSION can be overridden, otherwise the version from meson.build is used.

set -e
cd "$(dirname "$0")"

VERSION="${VERSION:-$(sed -n "s/^  version: '\([^']*\)',/\1/p" meson.build | head -n1)}"
if [ -z "$VERSION" ]; then
    echo "Could not read the version from meson.build" >&2
    exit 1
fi
DEB="postrophe_${VERSION}_amd64.deb"

# Always configure a clean release build (no .Devel suffix, release app id).
rm -rf builddir
PATH=/usr/bin:/bin meson setup builddir --prefix=/usr
PATH=/usr/bin:/bin ninja -C builddir

# Never ship the local-run config.py or stale bytecode.
rm -f postrophe/config.py
find postrophe -name __pycache__ -type d -prune -exec rm -rf {} +

ROOT=$(mktemp -d "${TMPDIR:-/tmp}/postrophe-deb.XXXXXX")
trap 'rm -rf "$ROOT"' EXIT

DESTDIR="$ROOT" PATH=/usr/bin:/bin ninja -C builddir install >/dev/null
sed -i '1s|.*|#!/usr/bin/python3|' "$ROOT/usr/bin/postrophe"
find "$ROOT" -name __pycache__ -type d -prune -exec rm -rf {} +

mkdir -p "$ROOT/DEBIAN"
cat > "$ROOT/DEBIAN/control" <<EOF
Package: postrophe
Version: $VERSION
Section: editors
Priority: optional
Architecture: amd64
Installed-Size: INSTALL_SIZE
Maintainer: ch0305 <ch0305@users.noreply.github.com>
Depends: python3 (>= 3.8), python3-gi, python3-cairo, python3-setuptools, python3-pypandoc, python3-chardet, gir1.2-gtk-3.0, gir1.2-handy-1, gir1.2-gspell-1, gir1.2-webkit2-4.1 | gir1.2-webkit2-4.0, pandoc, libgtk-3-0t64 | libgtk-3-0, libhandy-1-0, libgspell-1-2, libwebkit2gtk-4.1-0 | libwebkit2gtk-4.0-37, dconf-gsettings-backend | gsettings-backend
Conflicts: apostrophe, apostrophe-devel
Replaces: apostrophe, apostrophe-devel
Provides: apostrophe
Homepage: https://github.com/ch0305/Postrophe
Description: Postrophe Markdown editor
 Postrophe is a fork of Apostrophe, the distraction-free GTK Markdown
 editor. Compared to Apostrophe it adds task list editing, clickable
 preview checkboxes, more stable scrolling and a preview that updates
 without reloading the whole page.
EOF
cat > "$ROOT/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = configure ]; then
    glib-compile-schemas /usr/share/glib-2.0/schemas || true
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    update-desktop-database -q /usr/share/applications || true
fi
exit 0
EOF
cat > "$ROOT/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = remove ] || [ "$1" = purge ]; then
    glib-compile-schemas /usr/share/glib-2.0/schemas || true
fi
exit 0
EOF
chmod 755 "$ROOT/DEBIAN/postinst" "$ROOT/DEBIAN/postrm"
SIZE=$(du -sk --exclude=DEBIAN "$ROOT" | cut -f1)
sed -i "s|INSTALL_SIZE|$SIZE|" "$ROOT/DEBIAN/control"
( cd "$ROOT" && find usr -type f -print0 | sort -z | xargs -0 md5sum > DEBIAN/md5sums )

dpkg-deb --build --root-owner-group "$ROOT" "$DEB"
echo "已生成: $(pwd)/$DEB"
