from pathlib import Path
import os
import signal
import shutil
import sys
from PySide6.QtCore import QProcess, QTimer


def executable(name: str) -> str:
    if getattr(sys, 'frozen', False):
        bundled = Path(sys._MEIPASS) / 'bin' / name
        if bundled.is_file():
            return str(bundled)
    return shutil.which(name) or name


def available(name: str) -> bool:
    return Path(executable(name)).is_file()


def interrupt(process: QProcess):
    """SIGINT lets dvgrab/FFmpeg close files. Kill only this process on timeout."""
    if process.state() == QProcess.ProcessState.NotRunning:
        return
    pid = process.processId()
    if pid:
        try:
            os.kill(pid, signal.SIGINT)
        except ProcessLookupError:
            return
    timer = QTimer(process)
    timer.setSingleShot(True)
    timer.timeout.connect(lambda: process.kill() if process.state() != QProcess.ProcessState.NotRunning
                          and process.processId() == pid else None)
    process.finished.connect(timer.stop)
    timer.start(5000)
