#!/usr/bin/env bash
# Developer/release build. End users launch the resulting AppImage directly.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
for tool in python dvgrab ffmpeg ffprobe curl; do
    command -v "$tool" >/dev/null || { printf 'Build-Abhängigkeit fehlt: %s\n' "$tool" >&2; exit 1; }
done
[[ $(uname -m) == x86_64 ]] || { echo 'Dieser Build ist für x86_64 vorgesehen.' >&2; exit 1; }
python -m venv --system-site-packages .build-venv
.build-venv/bin/python -m pip install 'pyinstaller>=6.16,<7' 'PySide6>=6.6,<7'
mkdir -p build/packaging
.build-venv/bin/python -m PyInstaller --noconfirm --clean --onedir --name minidv-capture \
    --paths "$project_dir" --specpath build/packaging \
    --add-data 'assets:assets' --add-data 'scripts:scripts' --add-data 'LICENSE:licenses' \
    --add-data 'packaging/THIRD-PARTY.md:licenses' \
    --add-binary "$(command -v dvgrab):bin" \
    --add-binary "$(command -v ffmpeg):bin" \
    --add-binary "$(command -v ffprobe):bin" \
    packaging/entrypoint.py
appdir="$project_dir/build/MiniDV-Capture.AppDir"
# Only remove generated build output, never user recordings.
if [[ -e "$appdir" ]]; then rm -rf -- "$appdir"; fi
mkdir -p "$appdir/usr/lib/minidv-capture" "$appdir/usr/share/licenses"
cp -a dist/minidv-capture/. "$appdir/usr/lib/minidv-capture/"
cp packaging/minidv-capture.desktop "$appdir/"
cp assets/minidv-capture.svg "$appdir/"
cp assets/minidv-capture.svg "$appdir/.DirIcon"
for package in python pyside6 python-pyside6 qt6-base qt6-svg qt6-wayland ffmpeg dvgrab; do
    if [[ -d "/usr/share/licenses/$package" ]]; then
        cp -a "/usr/share/licenses/$package" "$appdir/usr/share/licenses/"
    fi
done
if command -v pacman >/dev/null; then
    pacman -Q > "$appdir/usr/share/licenses/build-package-versions.txt"
fi
cp packaging/THIRD-PARTY.md "$appdir/usr/share/licenses/"
cat > "$appdir/AppRun" <<'RUN'
#!/usr/bin/env bash
app_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$app_dir/usr/lib/minidv-capture/minidv-capture" "$@"
RUN
chmod +x "$appdir/AppRun"
# Verify that bundled programs exist; PyInstaller collects linked ELF libraries.
for tool in dvgrab ffmpeg ffprobe; do
    test -x "$appdir/usr/lib/minidv-capture/_internal/bin/$tool"
done
QT_QPA_PLATFORM=offscreen XDG_DATA_HOME="$project_dir/build/smoke/data" \
    XDG_CONFIG_HOME="$project_dir/build/smoke/config" "$appdir/AppRun" --smoke-test
appimage_tool="${APPIMAGETOOL:-$project_dir/build/appimagetool-x86_64.AppImage}"
if [[ ! -x "$appimage_tool" ]]; then
    curl --fail --location --retry 2 --output "$appimage_tool" \
        https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x "$appimage_tool"
fi
ARCH=x86_64 "$appimage_tool" --appimage-extract-and-run "$appdir" "$project_dir/dist/MiniDV-Capture-x86_64.AppImage"
sha256sum dist/MiniDV-Capture-x86_64.AppImage > dist/MiniDV-Capture-x86_64.AppImage.sha256
printf '\nFertig: %s/dist/MiniDV-Capture-x86_64.AppImage\n' "$project_dir"
