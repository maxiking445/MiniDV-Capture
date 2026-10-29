<p align="center">
  <img src="assets/minidv-capture.svg" alt="MiniDV Capture logo" width="192">
</p>

<h1 align="center">MiniDV Capture</h1>

<p align="center">
  <a href="https://github.com/maxiking445/MiniDV-Capture/actions/workflows/ci.yml">
    <img src="https://github.com/maxiking445/MiniDV-Capture/actions/workflows/ci.yml/badge.svg" alt="CI status">
  </a>
  <a href="https://github.com/maxiking445/MiniDV-Capture/actions/workflows/release.yml">
    <img src="https://github.com/maxiking445/MiniDV-Capture/actions/workflows/release.yml/badge.svg" alt="Release workflow status">
  </a>
  <br>
  <img src="https://img.shields.io/github/license/maxiking445/MiniDV-Capture" alt="License">
  <img src="https://img.shields.io/github/v/release/maxiking445/MiniDV-Capture" alt="Latest release">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10 or newer">
  <img src="https://img.shields.io/badge/Linux-FireWire-FCC624?logo=linux&logoColor=black" alt="Linux FireWire">
</p>

A native Linux desktop application for capturing MiniDV tapes over FireWire,
with a live preview and a background conversion queue. Built with Python,
PySide6, dvgrab and FFmpeg. No web server or Docker is required.

## Launch and setup

Run `./start.sh` from the project directory. The included desktop entry
resolves the checkout path when launched, so the project can be cloned or moved.

Use **Setup** in the top-right corner to install missing components and enable
FireWire access. A graphical administrator authorization prompt appears;
the application itself runs as your normal user.

### Required system packages

The app needs **Python 3.10+, PySide6/Qt, dvgrab, FFmpeg (`ffmpeg` and
`ffprobe`)**, and the Qt platform libraries. `dvgrab` captures DV from the
FireWire camera; FFmpeg and ffprobe handle preview, conversion and verification.
Install them yourself with the commands below, or open **Setup** in the app to
install the system packages and configure camera access. On a fresh system,
install Python and a graphical desktop first so the app and its setup window can
run. The Setup button can then install dvgrab, FFmpeg/ffprobe and Qt system
libraries, and grant camera access. For source development, Git and Python's
venv support must also be installed before cloning and building.

| Distribution | Packages installed by Setup | Notes |
| --- | --- | --- |
| Ubuntu / Debian | `python3`, `python3-venv`, `dvgrab`, `ffmpeg`, `qt6-wayland`, `libxcb-cursor0`, `libegl1`; native PySide6 when available | Otherwise Setup's launcher installs PySide6 into a virtual environment in your user data directory. |
| Arch / CachyOS | `python`, `pyside6`, `qt6-svg`, `qt6-wayland`, `dvgrab`, `ffmpeg` | Uses pacman without a separate database refresh. |
| Fedora / DNF | `python3`, `python3-pyside6`, `qt6-qtsvg`, `qt6-qtwayland`, `dvgrab`, `ffmpeg` or `ffmpeg-free` | `ffmpeg-free` may not provide H.264/H.265 encoders; install a full FFmpeg build for those formats. |

Setup also writes and reloads the udev rule needed to grant the active desktop
user FireWire access. It asks for administrator authorization; the application
itself runs as your normal user. Setup does **not** install Git or developer
tools. For a source build, install Git and Python first as described below;
the `pip install --editable .` command installs the Python package dependencies
inside `.venv/`.

The launcher requires `pkexec` and either `kdialog` or `zenity` for graphical
first-time installation. If these are unavailable, install packages manually
using the table above, or run `sudo bash scripts/setup-system.sh` from the
project directory. Add `--access-only` to configure FireWire permissions
without installing packages. Internet access is needed to download packages
and, on Ubuntu releases without native PySide6, the PySide6 wheel.

Package references: [Ubuntu PySide packages](https://packages.ubuntu.com/search?keywords=python3-pyside),
[Fedora PySide6](https://packages.fedoraproject.org/pkgs/python-pyside6/python3-pyside6/),
[Fedora FFmpeg](https://packages.fedoraproject.org/pkgs/ffmpeg/ffmpeg-free/).
Installer branches are tested with mocked package managers; real installation
on each distribution has not been verified.

## Capture a tape

1. Connect the camera over FireWire and select **PLAYER / VCR** mode.
2. Choose the camera, output folder, tape name and conversion settings.
3. In **Manual** mode, click **Start capture**, then press PLAY on the camera.
   In **Automatic · AV/C**, the app starts playback and can rewind first.
4. Watch the preview and the tape's row in the job table.
5. Use **Stop & convert** at the end to finish the capture and queue conversion.
   **Cancel capture** keeps the raw footage without converting it.

The capture buttons are centered at the bottom of the window. Right-click the
tray icon for **Open** or **Quit**. Quitting during active work asks before
stopping processes; partial recordings are kept.

In **2 · Capture**, enable **Start next capture automatically after changing the
tape** to use automatic AV/C playback and cassette-change detection. After a
successful capture, leave the completion popup open, remove the cassette and
insert the next one. The app requires an explicit no-cassette status followed
by two consecutive cassette-present readings before starting. Closing the popup
or unchecking the option cancels automatic waiting. Without the option, use
**Start next tape**. Conversion of the previous tape continues in the background.

This requires camera support for AV/C MEDIUM INFO. The connected Canon rejected
the status query during testing, so automatic detection is not confirmed for
that camera; the popup falls back to **Start next tape** when unsupported.
Camera disconnection and missing responses never count as cassette removal.

**Clear history** removes finished, failed and interrupted entries from the job
list. Video files and per-tape logs remain on disk; active and queued jobs stay
in the list.

A tape is stored in its own numbered folder, such as `Tape-001/capture001.dv`.
Each folder also contains `job.json`, `capture.log` and `conversion.log`.

## Progress and preview

Every job has its own progress bar and **Details** column:

- Capture progress estimates elapsed capture time against **90 minutes**,
  beginning with the first received data. It excludes initial waiting/rewinding,
  stays below 100% while capture is active, and does not impose a time limit.
- Details show the current step, capture speed in MB/s, recorded size in GB,
  and elapsed time.
- A shorter completed tape moves directly to its own **Conversion** progress
  bar, starting at zero. Conversion includes encoding and output verification.
- Multiple tapes can show capture and conversion progress independently.

The live preview follows the selected camera, is muted, and updates at up to
five frames per second. It reads the newest complete frame from the growing
DV file. Recording retains its full frame rate. A stalled preview shows its
last frame with a notice; preview failures do not stop capture.

## Tape end and capture safety

In automatic mode, dvgrab can report tape end through AV/C transport status.
In manual mode, loss of incoming data cannot reliably distinguish tape end,
a blank section or a connection failure. After 30 seconds without new data,
the capture is marked as an error and the raw file is kept. The 90-minute
progress estimate does not change this behavior. An optional capture duration
can be set separately; it begins when the first data arrives.

A single camera on a known controller uses broadcast reception on channel 63,
including in automatic mode. This avoids CMP connection failures on cameras
without online plugs while retaining AV/C playback control. With multiple
cameras on one bus, automatic mode retains GUID selection. Manual mode requires
one camera per bus, and parallel captures require separate controllers.

## Conversion and originals

Available formats: MP4/H.264, MKV/H.265, MOV/ProRes and lossless DV-in-AVI.
Quality levels are High, Standard and Compact. Optional BWDIF deinterlacing
produces 50p or 59.94p. AVI/DV copies the original video without re-encoding.

Originals are kept by default. Automatic deletion must be explicitly enabled
and is reset to off on each application launch. Before deletion, the app checks
video duration, resolution, aspect ratio, audio streams, full output decoding,
and unchanged source/output file fingerprints. Errors always preserve originals.

The persistent queue resumes pending jobs after restart. Interrupted captures
are kept for manual review; **Retry selected conversion** disables automatic
source deletion. Preferences saved by the former German interface remain readable.

## Development

### Build and run from source

Build on Ubuntu 22.04 or newer, Debian 12 or newer, Arch/CachyOS or Fedora with
Python **3.10 or newer** and Git. The app's Python dependencies go into an
isolated virtual environment. Ubuntu releases without a packaged PySide6 use
the PyPI wheel in that environment. The app's Setup window can install system
`dvgrab`, `ffmpeg` and `ffprobe`; alternatively install those tools manually as
described above. A C/C++ compiler is not needed for the normal source install.

For a fully manual Ubuntu/Debian install, install the system tools and Qt
runtime libraries:

```bash
sudo apt update
sudo apt install git python3 python3-venv \
  dvgrab ffmpeg libxcb-cursor0 libegl1 qt6-wayland
```

On Arch/CachyOS, install `git python base-devel pyside6 qt6-svg qt6-wayland
dvgrab ffmpeg`. On Fedora, install `git python3 python3-devel gcc gcc-c++ make
python3-pyside6 qt6-qtsvg qt6-qtwayland dvgrab ffmpeg-free` and any FFmpeg
codec packages your output format requires. Fedora's `ffmpeg-free` may not
include H.264/H.265 encoders; lossless DV/AVI remains available.

Clone the repository, create a virtual environment and install the project in
editable mode:

```bash
git clone <repository-url> minidv-capture
cd minidv-capture
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --editable .
.venv/bin/python -m minidv_capture
```

Pip installs PySide6 in the virtual environment. Keep `dvgrab`, `ffmpeg` and
`ffprobe` installed as system programs so the app can find them. If your
distribution supplies PySide6 but pip cannot install it, create the venv with
`python3 -m venv --system-site-packages .venv` after installing PySide6 with
the system package manager. Enable FireWire access once with
`sudo bash scripts/setup-system.sh --access-only`; reconnect the camera or
refresh your login session if the device permissions do not update.

To check that the GUI starts without a connected camera:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m minidv_capture --smoke-test
```

### Build a distributable AppImage

The release script currently targets x86_64 Linux. It needs Python 3.10+, pip,
the system `dvgrab`, `ffmpeg` and `ffprobe` executables, `curl`, and internet
access to download appimagetool if it is not already available. From the
repository root, run:

```bash
./packaging/build-appimage.sh
```

The script creates `.build-venv/`, intermediate files in `build/` and `dist/`,
and `dist/MiniDV-Capture-x86_64.AppImage`. Set `APPIMAGETOOL` to an existing
appimagetool executable to skip its download. Generated build output is
ignored by Git. Smoke-test the image on each target distribution; an image
built on a newer Linux base may not run on older systems.

To build the optional Arch package, run `makepkg` from `packaging/`. The
generated package archive is local build output and should not be committed.

### Publish a GitHub release

Open **Actions → Publish Release → Run workflow**. Enter
`auto` to create `1.0.0` for the first release and increment the patch version
for each later release (`1.0.1`, `1.0.2`, …), or enter a higher semantic version
such as `1.2.0` yourself. The workflow runs the CI suite, builds the x86_64
AppImage, updates the displayed/package version, commits that version bump,
creates a matching `vX.Y.Z` tag, and publishes a GitHub Release with the single
`MiniDV-Capture-x86_64.AppImage` executable. GitHub automatically provides the
tagged source as ZIP and tar archives on the release page. The version badge
shows the latest published release; the CI and Release badges show their
respective workflow runs. In the repository's **Settings → Actions → General**,
allow GitHub Actions to create and approve commits (read/write contents
permission), so the release job can push its version commit and tag.

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Tests use synthetic DV, real FFmpeg conversions, simulated capture processes,
GUI interaction, growing PAL/NTSC preview files, and mocked installer commands.
No camera or administrator access is needed for the test suite.

`packaging/build-appimage.sh` builds an AppImage with Python, Qt, dvgrab and FFmpeg.
`packaging/PKGBUILD` provides an Arch package. No completed AppImage release is
included; compatibility must be checked on the intended target systems.

## Hardware validation

On 2026-10-29, two short captures using automatic playback and broadcast
reception received about five seconds of DV with audio from the connected camera.
The first reported a damaged frame; the second had no dvgrab frame warning, but
FFmpeg still reported bitstream and timecode errors. Reception is confirmed;
error-free picture quality is not. Preview and conversion do not repair damaged
source footage. Long captures and multiple controllers still need hardware tests.

## AI disclosure

This project was created with AI assistance. The maintainers are responsible for
reviewing, testing and maintaining the code.
