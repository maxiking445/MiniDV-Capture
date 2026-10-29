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
  <img src="https://img.shields.io/badge/Linux-FireWire-FCC624?logo=linux&logoColor=black" alt="Linux FireWire">
</p>

## Quick start

1. Connect your MiniDV camera to your Linux computer with **FireWire** and
   switch the camera to **PLAYER / VCR** mode.
2. Open the [latest release](https://github.com/maxiking445/MiniDV-Capture/releases/latest)
   and download **one** of these files from **Assets**:
   - **AppImage:** download `MiniDV-Capture-x86_64.AppImage`, then run:

     ```bash
     chmod +x MiniDV-Capture-x86_64.AppImage
     ./MiniDV-Capture-x86_64.AppImage
     ```

   - **Ubuntu/Debian `.deb`:** download the `.deb`, then install it from the
     download folder:

     ```bash
     sudo apt install ./MiniDV-Capture_*_amd64.deb
     ```

3. On first launch, click **Setup** and allow it to enable FireWire camera
   access. Then choose your camera and click **Start capture**.

The AppImage can be run directly. The `.deb` installs the app and its required
packages. Both formats are available from the [latest release page](https://github.com/maxiking445/MiniDV-Capture/releases/latest).

Capture MiniDV tapes over FireWire, preview video while recording, and convert
your tapes with FFmpeg. Original DV recordings are kept by default.

## Use

1. Connect the camera over FireWire and select **PLAYER / VCR** mode.
2. Choose the camera, output folder, tape name and conversion format.
3. Click **Start capture**. In Manual mode, press PLAY on the camera; Automatic
   mode can control playback when the camera supports AV/C.
4. Watch the preview and progress in the job table. Click **Stop & convert**
   when the tape is finished.

The **Setup** button installs missing tools and configures FireWire permissions.
It supports APT (Ubuntu/Debian), pacman (Arch/CachyOS) and DNF (Fedora). It may
ask for administrator authorization; the app itself runs as your normal user.
Right-click the tray icon to open or quit the app.

The optional **Start next capture automatically after changing the tape**
setting waits for a tape change after capture. This requires camera support for
AV/C media status; it was not confirmed on the tested Canon camera. Otherwise,
use **Start next tape** in the completion popup.

Captures are stored as numbered tape folders. Original DV files are preserved
by default. Conversion supports MP4/H.264, MKV/H.265, MOV/ProRes and lossless
DV-in-AVI. MP4 and MKV automatically try NVIDIA NVENC or Intel/AMD VAAPI when
FFmpeg, the GPU driver and device access support it, then retry with CPU
encoding if hardware encoding fails. ProRes uses CPU; DV-in-AVI is a stream
copy. Final file verification still decodes on the CPU.

## Build from source

Requirements: Linux, Python 3.10+, Git, FFmpeg and dvgrab. Install the system
packages, then clone and run the app:

Ubuntu/Debian:

```bash
sudo apt install git python3 python3-venv dvgrab ffmpeg qt6-wayland libegl1 libxcb-cursor0
```

Arch/CachyOS:

```bash
sudo pacman -S --needed git python pyside6 qt6-svg qt6-wayland dvgrab ffmpeg
```

Then, on either distribution:

```bash
git clone https://github.com/maxiking445/MiniDV-Capture.git
cd MiniDV-Capture
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --editable .
.venv/bin/python -m minidv_capture
```

To configure FireWire access, run `sudo bash scripts/setup-system.sh --access-only`.
Run the test suite with `.venv/bin/python -m unittest discover -s tests -v`.

### Build packages

On x86_64, install `curl`, `dpkg`, `dvgrab`, `ffmpeg` and `ffprobe`, then run:

```bash
./packaging/build-appimage.sh
./packaging/build-deb.sh
```

The AppImage build creates the shared PyInstaller output used by the `.deb`
build. Both downloadable packages are attached to each GitHub release.

## Releases and CI

CI runs the test suite on pushes and pull requests. To publish a release, open
**Actions → Publish Release → Run workflow** and enter `auto` or a higher
semantic version. The first automatic version is `1.0.0`; later automatic
releases increment the patch number. The workflow attaches the AppImage and
`.deb` to the release; GitHub also provides source ZIP and tar archives. Enable
read/write contents permission for Actions in the repository settings so it
can push the version commit and tag.

## AI disclosure

This project was created with AI assistance. The maintainers are responsible
for reviewing, testing and maintaining the code.
