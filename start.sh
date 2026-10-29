#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" && pwd)"
cd "$project_dir"
show_error() {
    if command -v kdialog >/dev/null; then
        kdialog --title 'MiniDV Capture' --error "$1"
    elif command -v zenity >/dev/null; then
        zenity --error --text="$1"
    else
        printf '%s\n' "$1" >&2
    fi
}
runtime_python=/usr/bin/python3
runtime_dir="${XDG_DATA_HOME:-$HOME/.local/share}/minidv-capture/runtime"
if [[ -x "$runtime_dir/bin/python" ]]; then
    runtime_python="$runtime_dir/bin/python"
fi
if ! "$runtime_python" -c 'from PySide6.QtWidgets import QApplication' >/dev/null 2>&1; then
    if command -v kdialog >/dev/null; then
        kdialog --title 'Set up MiniDV Capture' --yesno 'Install Python/Qt, dvgrab and FFmpeg now? Administrator authorization is required. If needed, PySide6 will be downloaded into a user-owned virtual environment.' || exit 0
    elif command -v zenity >/dev/null; then
        zenity --question --text='Set up MiniDV Capture with Python/Qt, dvgrab and FFmpeg? PySide6 may be downloaded into a user-owned virtual environment.' || exit 0
    else
        show_error 'Install kdialog or zenity for graphical first-time setup, or run scripts/setup-system.sh as administrator.'
        exit 1
    fi
    setup_log="$(mktemp -t minidv-setup.XXXXXX)"
    if ! pkexec /usr/bin/bash "$project_dir/scripts/setup-system.sh" >"$setup_log" 2>&1; then
        show_error "Setup failed: $(tail -c 4000 "$setup_log")"
        exit 1
    fi
fi
# Ubuntu releases without native PySide6 packages use an isolated user runtime.
if ! "$runtime_python" -c 'from PySide6.QtWidgets import QApplication' >/dev/null 2>&1; then
    if ! /usr/bin/python3 -m venv "$runtime_dir" || ! "$runtime_dir/bin/python" -m pip install 'PySide6>=6.6,<7'; then
        show_error 'Could not install the Python/Qt runtime. Check your internet connection and retry.'
        exit 1
    fi
    runtime_python="$runtime_dir/bin/python"
fi
exec "$runtime_python" -m minidv_capture "$@"
