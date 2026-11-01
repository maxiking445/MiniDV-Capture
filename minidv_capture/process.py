from pathlib import Path
import os
import signal
import shutil
import sys
import threading
from PySide6.QtCore import QProcess, QTimer


def start_shutdown_watchdog(pids, timeout=10):
    """Bound application shutdown even if the Qt event loop or driver stalls.

    Linux pidfds retain process identity, so a recycled PID is never killed.
    This is armed only by the application entry point after confirmed exit.
    """
    handles = []
    for pid in set(pids):
        if pid > 0:
            try:
                handles.append(os.pidfd_open(pid))
            except (OSError, AttributeError):
                pass

    def shutdown():
        threading.Event().wait(timeout)
        for handle in handles:
            try:
                signal.pidfd_send_signal(handle, signal.SIGKILL)
            except (OSError, AttributeError):
                pass
            finally:
                os.close(handle)
        # Skip Qt destructors: QProcess destruction may wait on a stuck driver.
        # Store changes are written synchronously; interrupted jobs recover at startup.
        os._exit(0)

    threading.Thread(target=shutdown, name='shutdown-watchdog', daemon=True).start()


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
