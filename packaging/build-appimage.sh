#!/usr/bin/env bash
# Developer/release build. End users launch the resulting AppImage directly.
set -euo pipefail
if [[ $# -gt 1 || ($# -eq 1 && $1 != --onedir-only) ]]; then
    echo 'Usage: build-appimage.sh [--onedir-only]' >&2
    exit 2
fi
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
for tool in python dvgrab ffmpeg ffprobe curl timeout rsvg-convert; do
    command -v "$tool" >/dev/null || { printf 'Build-Abhängigkeit fehlt: %s\n' "$tool" >&2; exit 1; }
done
[[ $(uname -m) == x86_64 ]] || { echo 'Dieser Build ist für x86_64 vorgesehen.' >&2; exit 1; }
python -m venv --system-site-packages .build-venv
.build-venv/bin/python -m pip install 'pyinstaller>=6.16,<7' 'PySide6>=6.6,<7'
mkdir -p build/packaging
.build-venv/bin/python -m PyInstaller --noconfirm --clean --onedir --name minidv-capture \
    --paths "$project_dir" --specpath "$project_dir/build/packaging" \
    --collect-submodules minidv_capture.translations \
    --add-data "$project_dir/assets:assets" \
    --add-data "$project_dir/scripts:scripts" \
    --add-data "$project_dir/LICENSE:licenses" \
    --add-data "$project_dir/packaging/THIRD-PARTY.md:licenses" \
    --add-binary "$(command -v dvgrab):bin" \
    --add-binary "$(command -v ffmpeg):bin" \
    --add-binary "$(command -v ffprobe):bin" \
    "$project_dir/packaging/entrypoint.py"
appdir="$project_dir/build/MiniDV-Capture.AppDir"
# Only remove generated build output, never user recordings.
if [[ -e "$appdir" ]]; then rm -rf -- "$appdir"; fi
mkdir -p "$appdir/usr/lib/minidv-capture" "$appdir/usr/share/licenses"
cp -a dist/minidv-capture/. "$appdir/usr/lib/minidv-capture/"
cp packaging/minidv-capture.desktop "$appdir/"
cp assets/minidv-capture.svg "$appdir/"
rsvg-convert --format=png --width=256 --height=256 \
    --output="$appdir/minidv-capture.png" assets/minidv-capture.svg
cp "$appdir/minidv-capture.png" "$appdir/.DirIcon"
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
smoke_test() {
    local smoke_dir result
    smoke_dir="$(mktemp -d "$project_dir/build/smoke.XXXXXX")"
    echo "GUI smoke test: $*"
    if QT_QPA_PLATFORM=offscreen XDG_DATA_HOME="$smoke_dir/data" \
        XDG_CONFIG_HOME="$smoke_dir/config" timeout --kill-after=5s 30s "$@" --smoke-test; then
        echo 'GUI smoke test passed.'
    else
        result=$?
        printf 'GUI smoke test failed (exit %s). Logs: %s\n' "$result" "$smoke_dir" >&2
        find "$smoke_dir" -name application.log -exec cat {} \; >&2
        exit "$result"
    fi
}
smoke_test "$appdir/AppRun"
# CI exercises the same frozen application without downloading appimagetool.
if [[ ${1:-} == --onedir-only ]]; then exit 0; fi
appimage_tool="${APPIMAGETOOL:-$project_dir/build/appimagetool-x86_64.AppImage}"
if [[ ! -x "$appimage_tool" ]]; then
    download_tmp="$appimage_tool.part.$$"
    trap 'rm -f -- "${download_tmp:-}"' EXIT
    curl --fail --location --retry 5 --retry-all-errors --retry-delay 2 \
        --connect-timeout 15 --max-time 300 --output "$download_tmp" \
        https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    [[ $(head -c 4 "$download_tmp") == $'\x7fELF' ]] || {
        echo 'Downloaded appimagetool is not an ELF executable.' >&2
        exit 1
    }
    chmod +x "$download_tmp"
    mv -f -- "$download_tmp" "$appimage_tool"
    trap - EXIT
    chmod +x "$appimage_tool"
fi
runtime_file="${APPIMAGETOOL_RUNTIME_FILE:-$project_dir/build/runtime-x86_64}"
if [[ ! -s "$runtime_file" ]]; then
    runtime_tmp="$runtime_file.part.$$"
    trap 'rm -f -- "${runtime_tmp:-}"' EXIT
    curl --fail --location --retry 5 --retry-all-errors --retry-delay 2 \
        --connect-timeout 15 --max-time 300 --output "$runtime_tmp" \
        https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64
    [[ $(head -c 4 "$runtime_tmp") == $'\x7fELF' ]] || {
        echo 'Downloaded AppImage runtime is not an ELF executable.' >&2
        exit 1
    }
    chmod +x "$runtime_tmp"
    mv -f -- "$runtime_tmp" "$runtime_file"
    trap - EXIT
fi
[[ -x "$runtime_file" ]] || chmod +x "$runtime_file"
ARCH=x86_64 "$appimage_tool" --appimage-extract-and-run --runtime-file "$runtime_file" \
    "$appdir" "$project_dir/dist/MiniDV-Capture-x86_64.AppImage"
smoke_test "$project_dir/dist/MiniDV-Capture-x86_64.AppImage" --appimage-extract-and-run
sha256sum dist/MiniDV-Capture-x86_64.AppImage > dist/MiniDV-Capture-x86_64.AppImage.sha256
printf '\nFertig: %s/dist/MiniDV-Capture-x86_64.AppImage\n' "$project_dir"
