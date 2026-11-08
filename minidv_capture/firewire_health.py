"""Passive kernel-log monitoring; never opens or resets a FireWire device."""
from pathlib import Path
import re
import json

from PySide6.QtCore import QObject, QProcess, QTimer, Signal


FAULT_PATTERN = r'firewire_ohci.*(IO_PAGE_FAULT|DMA context.*(still active|has stopped)|register access failure)'
FAULT = re.compile(r'firewire_ohci\s+([0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]):.*'
                   r'(IO_PAGE_FAULT|DMA context.*(?:still active|has stopped)|register access failure)', re.I)


class FireWireHealth(QObject):
    fault = Signal(str, str)
    unavailable = Signal(str)
    warning = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.faults = {}
        self.live_faults = set()
        self.fault_serials = {}
        self.dma_warnings = set()
        self.ready = False
        self.error = 'Checking the kernel log for FireWire faults. Please retry shortly.'
        self.stopping = False
        self.following = False
        self.cursor = ''
        self.snapshot_cursors = set()
        self.latest_timestamp = -1
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
        self.process.start('journalctl', ['-k', '-b', '--no-pager', '-o', 'json', '-n', '200',
                                         '--show-cursor', '--grep=' + FAULT_PATTERN])
        self.deadline.start(5000)

    def check(self, device):
        address = Path(device.bus).name.lower()
        if address in self.live_faults:
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
            # With --grep and -n, journalctl may scan backwards and report
            # a footer cursor older than the messages it actually printed.
            if not self.snapshot_cursors:
                self.cursor = line[len('-- cursor: '):]
            return
        if line.startswith('{'):
            try:
                entry = json.loads(line)
                cursor = entry['__CURSOR']
                timestamp = int(entry['__MONOTONIC_TIMESTAMP'])
                message = entry['MESSAGE']
                if not isinstance(cursor, str) or not isinstance(message, str):
                    return
            except (ValueError, KeyError, TypeError):
                return
            if self.following:
                if cursor in self.snapshot_cursors or timestamp < self.latest_timestamp:
                    return
            else:
                self.snapshot_cursors.add(cursor)
                if timestamp > self.latest_timestamp:
                    self.latest_timestamp = timestamp
                    self.cursor = cursor
            line = message
        match = FAULT.search(line)
        if match:
            address = match[1].lower()
            if self.following and 'IO_PAGE_FAULT' in line:
                # A rejected DMA access is diagnostic evidence, not proof that
                # capture has stalled. Do not abort a working/re-winding tape.
                if address not in self.dma_warnings:
                    self.dma_warnings.add(address)
                    self.warning.emit(
                        f'FireWire DMA warning on controller {address}. '
                        'Capture has not been stopped by this warning. '
                        'If the computer stutters or capture stalls, stop playback on the camera. '
                        'Kernel: ' + line[:2048])
            elif self.following:
                self.fault_serials[address] = self.fault_serials.get(address, 0) + 1
                # A historical warning must not suppress the first new fault.
                if address not in self.live_faults:
                    self.faults[address] = line[:2048]
                    self.live_faults.add(address)
                    self.fault.emit(address, self.fault_message(address))
            elif address not in self.faults:
                self.faults[address] = line[:2048]
                self.warning.emit(
                    f'Earlier kernel FireWire fault on controller {address}. '
                    'This historical entry does not block capture. '
                    'New faults will still stop capture. Kernel: ' + line[:2048])

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
        self.process.start('journalctl', ['-k', '-b', '--no-pager', '-o', 'json', '--follow',
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
