# Bundled components

The application source is MIT licensed. A packaged application also contains:

- CPython (PSF license): https://www.python.org/downloads/source/
- PySide6 / Qt (LGPL/GPL/commercial terms depending on modules): https://www.qt.io/qt-for-python
- dvgrab (GPL-2.0-or-later): https://github.com/ddennedy/dvgrab
- FFmpeg and codecs (license depends on the build): https://ffmpeg.org/legal.html
- PyInstaller bootloader (GPL with distribution exception): https://pyinstaller.org/en/stable/license.html

The build script includes available Arch package license files and exact package
versions. Before publishing binary releases, provide the corresponding source
and license notices for the exact included builds, including transitively bundled
libraries; this file alone is not a replacement for those distribution obligations.
System graphics drivers, the Linux kernel/FireWire modules and device permissions
remain host responsibilities. The GUI configures device access via polkit/udev.
