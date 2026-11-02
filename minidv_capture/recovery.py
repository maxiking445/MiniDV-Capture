"""Run privileged controller recovery without blocking the GUI event loop."""
import subprocess
import tempfile
import threading
from PySide6.QtCore import QObject, Signal
from .setup import project_root


class FireWireRecovery(QObject):
    finished = Signal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = False
        self.process = None
        self.cancelled = threading.Event()

    def start(self, address):
        if self.running:
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
                    return
                process = subprocess.Popen(
                    ['pkexec', '/usr/bin/python3', str(project_root() / 'scripts/recover-firewire.py'), address],
                    stdout=output, stderr=output)
                self.process = process
                if self.cancelled.is_set():
                    process.kill()
                try:
                    success = process.wait(timeout=45) == 0
                except subprocess.TimeoutExpired:
                    process.kill()
                    message = 'Recovery timed out; the controller is still unavailable. '
                    # Do not wait again: even the reset helper may be stuck in the kernel.
                output.seek(0)
                message += output.read().decode(errors='replace')
        except OSError as exc:
            message = str(exc)
        self.running = False
        if not self.cancelled.is_set():
            self.finished.emit(success, message)

    def cancel(self):
        self.cancelled.set()
        if self.process and self.process.poll() is None:
            self.process.kill()
