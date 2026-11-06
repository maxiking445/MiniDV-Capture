"""Passive kernel-log monitoring; never opens or resets a FireWire device."""
from pathlib import Path
import re

from PySide6.QtCore import QObject, QProcess, QTimer, Signal


FAULT_PATTERN = r'firewire_ohci.*(IO_PAGE_FAULT|DMA context.*(still active|has stopped)|register access failure)'
FAULT = re.compile(r'firewire_ohci\s+([0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]):.*'
                   r'(IO_PAGE_FAULT|DMA context.*(?:still active|has stopped)|register access failure)', re.I)


class FireWireHealth(QObject):
    fault = Signal(str, str)
    unavailable = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.faults = {}
        self.ready = False
        self.error = 'Checking the kernel log for FireWire faults. Please retry shortly.'
        self.stopping = False
        self.following = False
        self.cursor = ''
        self.buffer = bytearray()
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.process.readAllStandardError)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(self.timed_out)

    def start(self):
        self.process.start('journalctl', ['-k', '-b', '--no-pager', '-o', 'cat', '-n', '200',
                                         '--show-cursor', '--grep=' + FAULT_PATTERN])
        self.deadline.start(5000)

    def check(self, device):
        address = Path(device.bus).name.lower()
        if address in self.faults:
            raise RuntimeError(self.fault_message(address))
        if not self.ready or self.error:
            raise RuntimeError(self.error or 'FireWire health monitoring is not ready.')

    def fault_message(self, address):
        return (f'FireWire controller {address} reported a kernel DMA/driver fault. '
                'Further capture on this controller is blocked to protect the computer. '
                'Stop playback and power off the camera. Check the controller/kernel before retrying. '
                'Recordings are kept. Kernel: ' + self.faults[address])

    def observe(self, line):
        if line.startswith('-- cursor: '):
            self.cursor = line[len('-- cursor: '):]
            return
        match = FAULT.search(line)
        if match:
            address = match[1].lower()
            if address not in self.faults:
                self.faults[address] = line[:2048]
                self.fault.emit(address, self.fault_message(address))

    def read_output(self):
        self.buffer.extend(bytes(self.process.readAllStandardOutput()))
        while b'\n' in self.buffer:
            line, _, rest = self.buffer.partition(b'\n')
            self.buffer = bytearray(rest)
            self.observe(line[:8192].decode(errors='replace'))
        if len(self.buffer) > 8192:
            del self.buffer[:-8192]

    def finished(self, code, status):
        self.deadline.stop()
        self.read_output()
        if self.buffer:
            self.observe(self.buffer.decode(errors='replace'))
            self.buffer.clear()
        if self.stopping:
            return
        if self.following or status != QProcess.ExitStatus.NormalExit or not self.cursor or code not in (0, 1):
            self.disable('Kernel log monitoring is unavailable. Check journalctl access before starting capture.')
            return
        # The cursor closes the gap between the initial snapshot and live stream.
        # No polling, rescanning of the entire journal, or privileged helper.
        self.following = True
        self.error = ''
        self.ready = True
        self.process.start('journalctl', ['-k', '-b', '--no-pager', '-o', 'cat', '--follow',
                                         '--after-cursor=' + self.cursor, '--grep=' + FAULT_PATTERN])

    def disable(self, message):
        self.ready = False
        self.error = message
        self.unavailable.emit(message)

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart and not self.stopping:
            self.deadline.stop()
            self.disable('Kernel log monitoring could not start. Install journalctl and check kernel-log access.')

    def timed_out(self):
        self.disable('Kernel log check timed out. No new capture was started.')
        self.stop()

    def stop(self):
        self.stopping = True
        self.ready = False
        self.deadline.stop()
        self.process.kill()
