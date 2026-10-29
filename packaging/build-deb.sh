#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

if [[ $(uname -m) != x86_64 ]]; then
    echo 'The Debian package build currently targets x86_64.' >&2
    exit 1
fi
if ! command -v dpkg-deb >/dev/null; then
    echo 'Missing build dependency: dpkg-deb (install the dpkg package).' >&2
    exit 1
fi
if [[ ! -x dist/minidv-capture/minidv-capture ]]; then
    echo 'Missing PyInstaller build. Run packaging/build-appimage.sh first.' >&2
    exit 1
fi

version="$(python -c 'from minidv_capture import __version__; print(__version__)')"
package_root="$project_dir/build/debroot"
rm -rf -- "$package_root"
install -dm755 "$package_root/DEBIAN" \
    "$package_root/opt/minidv-capture" \
    "$package_root/usr/bin" \
    "$package_root/usr/share/applications" \
    "$package_root/usr/share/icons/hicolor/scalable/apps" \
    "$package_root/usr/share/doc/minidv-capture" \
    "$package_root/usr/share/licenses/minidv-capture"

cp -a dist/minidv-capture/. "$package_root/opt/minidv-capture/"
rm -rf -- "$package_root/opt/minidv-capture/_internal/bin"
cat > "$package_root/usr/bin/minidv-capture" <<'LAUNCHER'
#!/usr/bin/env bash
exec /opt/minidv-capture/minidv-capture "$@"
LAUNCHER
chmod 755 "$package_root/usr/bin/minidv-capture"
install -m644 packaging/minidv-capture.desktop "$package_root/usr/share/applications/minidv-capture.desktop"
install -m644 assets/minidv-capture.svg "$package_root/usr/share/icons/hicolor/scalable/apps/minidv-capture.svg"
install -m644 README.md "$package_root/usr/share/doc/minidv-capture/README.md"
install -m644 LICENSE "$package_root/usr/share/licenses/minidv-capture/LICENSE"
install -m644 packaging/THIRD-PARTY.md "$package_root/usr/share/doc/minidv-capture/THIRD-PARTY.md"

cat > "$package_root/DEBIAN/control" <<CONTROL
Package: minidv-capture
Version: $version
Section: video
Priority: optional
Architecture: amd64
Maintainer: MiniDV Capture contributors
Depends: dvgrab, ffmpeg, libc6, libstdc++6, libgcc-s1, libglib2.0-0, libdbus-1-3, libfontconfig1, libfreetype6, libgl1, libegl1, libx11-6, libx11-xcb1, libxcb1, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, libxcb-shape0, libxcb-xfixes0, libxcb-sync1, libxcb-xinerama0, libxext6, libxkbcommon0, libxkbcommon-x11-0, libxrender1
Description: Capture and convert MiniDV tapes over FireWire
 Native Linux desktop application with live preview and verified conversion.
 Bundles its Python and Qt runtime; depends on distro dvgrab and FFmpeg.
CONTROL

dpkg-deb --root-owner-group --build "$package_root" "dist/MiniDV-Capture_${version}_amd64.deb"
printf '\nBuilt: %s/dist/MiniDV-Capture_%s_amd64.deb\n' "$project_dir" "$version"
