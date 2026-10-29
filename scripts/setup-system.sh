#!/usr/bin/env bash
set -euo pipefail

install_components() {
    if command -v pacman >/dev/null; then
        # No -Sy: avoid partial system upgrades.
        pacman -S --needed --noconfirm python pyside6 qt6-svg qt6-wayland dvgrab ffmpeg
    elif command -v apt-get >/dev/null; then
        apt-get update
        apt-get install -y python3 python3-venv dvgrab ffmpeg qt6-wayland libxcb-cursor0 libegl1
        if apt-cache show python3-pyside6.qtwidgets >/dev/null 2>&1; then
            apt-get install -y python3-pyside6.qtwidgets python3-pyside6.qtsvg
        else
            echo 'System PySide6 is unavailable. The launcher will install it in a user-owned virtual environment.'
        fi
    elif command -v dnf >/dev/null; then
        dnf install -y python3 python3-pyside6 qt6-qtsvg qt6-qtwayland dvgrab
        if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
            # Prefer full FFmpeg if already available from configured repositories.
            if dnf list --available ffmpeg >/dev/null 2>&1; then
                dnf install -y ffmpeg
            else
                dnf install -y ffmpeg-free
            fi
        fi
        echo 'Fedora ffmpeg-free may lack H.264/H.265 encoders. Use DV/AVI or install full FFmpeg from your preferred repository.'
    else
        echo 'Unsupported package manager. Install Python 3, PySide6, dvgrab and FFmpeg manually.' >&2
        return 1
    fi
}

main() {
    if [[ $(id -u) != 0 ]]; then
        echo 'Setup requires administrator authorization.' >&2
        return 1
    fi
    if [[ "${1:-}" != --access-only ]]; then
        install_components
    fi
    install -d -m 0755 /etc/udev/rules.d
    cat > /etc/udev/rules.d/70-minidv-capture.rules <<'RULES'
# FireWire devices accessible to the active local desktop user via logind ACL.
SUBSYSTEM=="firewire", KERNEL=="fw[0-9]*", TAG+="uaccess"
RULES
    udevadm control --reload-rules
    udevadm trigger --subsystem-match=firewire --action=add
    udevadm settle --timeout=10
    printf '\nMiniDV Capture setup complete.\n'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
