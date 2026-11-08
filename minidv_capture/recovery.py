"""Run privileged controller recovery without blocking the GUI event loop."""
import subprocess
import json
import os
from pathlib import Path
import tempfile
import threading
from PySide6.QtCore import QObject, Signal
from .setup import project_root


def installed_service(address):
    path = Path('/usr/local/lib/minidv-capture/recovery-service.json')
    try:
        info = path.stat()
        if path.is_symlink() or info.st_uid != 0 or info.st_mode & 0o022:
            return False
        config = json.loads(path.read_text())
        return config == {'address': address, 'uid': os.getuid()}
    except (OSError, ValueError):
        return False


class FireWireRecovery(QObject):
    finished = Signal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = False
        self.process = None
        self.cancelled = threading.Event()

    @property
    def busy(self):
        # A timeout ends the waiting thread, not necessarily the kernel call.
        return (self.running or Path('/run/minidv-firewire-restart.pending').exists()
                or (self.process is not None and self.process.poll() is None))

    def start(self, address):
        if self.running:
            return
        if self.process is not None and self.process.poll() is None:
            self.finished.emit(False, 'The previous restart helper has not exited. No second restart was started.')
            return
        self.running = True
        self.cancelled.clear()
        threading.Thread(target=self.run, args=(address,), daemon=True).start()

    def run(self, address):
        success = False
        message = ''
        try:
            with tempfile.TemporaryFile() as output:
                if self.cancelled.is_set():
                    self.running = False
                    return
                service = installed_service(address)
                command = (['systemctl', 'start', 'minidv-firewire-recover.service'] if service else
                           ['pkexec', '/usr/bin/python3', str(project_root() / 'scripts/recover-firewire.py'), address, '--restart'])
                process = subprocess.Popen(command, stdout=output, stderr=output)
                self.process = process
                # Once started, let detach/reset/bind finish even if the UI
                # cancels continuation; killing midway can leave it unbound.
                try:
                    success = process.wait(timeout=60 if service else 45) == 0
                except subprocess.TimeoutExpired:
                    process.kill()
                    message = 'Restart timed out. Kernel cleanup may still be pending; recovery was not confirmed. '
                    # Do not wait again: even the reset helper may be stuck in the kernel.
                output.seek(0)
                message += output.read().decode(errors='replace')
                if service:
                    try:
                        message += Path('/run/minidv-firewire-recovery.log').read_text()[-16000:]
                    except OSError as exc:
                        message += f' Controller log unavailable: {exc}'
        except OSError as exc:
            message = str(exc)
        self.running = False
        if not self.cancelled.is_set():
            self.finished.emit(success, message)

    def cancel(self):
        self.cancelled.set()
        # Cancel automatic continuation, not an in-flight privileged reset.
        # The worker's timeout still bounds waiting and reports no success.
