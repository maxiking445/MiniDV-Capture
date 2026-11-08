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

1. Connect your MiniDV or Digital8 camera to your Linux computer with **FireWire** and
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

Capture MiniDV and Digital8 tapes over FireWire, preview video while recording,
and convert your tapes with FFmpeg. Digital8 works because the camera sends DV
video over FireWire. Some Digital8 cameras can also play analog Video8/Hi8 tapes
and output them as DV; support for those tapes depends on the camera. Original DV
recordings are kept by default.

## Use

1. Connect the camera over FireWire and select **PLAYER / VCR** mode.
2. Choose the camera, output folder, tape name and conversion format.
3. Click **Start capture**. In Manual mode, press PLAY on the camera; Automatic
   mode can control playback when the camera supports AV/C.
4. Watch the preview and progress in the job table. Click **Stop & convert**
   when the tape is finished.

If DV data stops arriving during capture, the app warns after 10 seconds and
requests a stop after 60 seconds. Silence alone does not confirm tape end.
**Recover stalled capture with 3-minute overlap** enables at most two recovery
attempts per recording: reinitialize the controller, confirm camera STOP, rewind
three minutes before the last saved frame using timecode, and resume into a new
DV segment. Segments are joined in a background process; overlap is preserved.
Missing timecode, unconfirmed camera control, or a blocked reset aborts recovery
and keeps the recorded footage. Stop the camera manually if recovery fails.

For unattended recovery, an administrator can install the fixed-controller
service (the controller and requesting user are detected automatically):

```sh
pkexec /usr/bin/python3 scripts/install-recovery-service.py
```

The unattended service requires systemd and polkit >= 0.106 (Ubuntu 24.04 or newer).
On Ubuntu 22.04, use the administrator-authorized fallback. Without this service,
recovery requires an administrator authorization dialog.
The service is not started at boot and only permits the specified active local
user to start recovery of the specified controller. A driver reset cannot
guarantee recovery from a kernel hang or prevent recurring DMA faults.
See [FireWire stability notes](docs/firewire-stability.md).

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
sudo apt install git python3 python3-venv dvgrab ffmpeg qt6-wayland libegl1 libxcb-cursor0 pkexec polkitd libraw1394-11 libavc1394-0
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


### FireWire fault protection

Capture now requires readable kernel logs through `journalctl`. Before capture,
the app checks recent FireWire DMA/driver errors from the current boot, then
monitors new errors asynchronously. Historical entries only produce a warning
and do not block capture. New DMA page faults are visible warnings; they do not by themselves abort or
block capture. A live stalled-DMA-context or controller-access failure blocks
that controller and stops its capture while keeping raw footage. Missing kernel-log access is shown
as an error and prevents capture; it is not treated as a healthy device.

This cannot repair a stuck kernel/controller or guarantee host stability. See
[the FireWire investigation](docs/firewire-stability.md) for evidence, limits,
and the next kernel/hardware comparisons. In manual mode, stop playback on the
camera itself. The app no longer launches a separate AV/C STOP helper.
