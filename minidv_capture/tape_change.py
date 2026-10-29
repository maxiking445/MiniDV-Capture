"""Read-only AV/C medium queries, isolated from the GUI in a timed process."""
import ctypes as c
import sys

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from .devices import discover


def decode_medium(response):
    if response & 0xff000000 in (0x08000000, 0x0a000000):
        return 'unsupported'
    if response & 0xffffff00 != 0x0c20da00:
        return 'unknown'
    medium = response & 0xff
    if medium == 0x60:
        return 'absent'
    if medium in (0x31, 0x32, 0x33, 0x22, 0x23, 0x12, 0x41):
        return 'present'
    return 'unknown'


def query_medium(guid):
    device = next((d for d in discover() if d.guid == guid), None)
    if not device or device.card < 0 or not device.accessible:
        return 'disconnected'
    raw = c.CDLL('libraw1394.so.11')
    rom = c.CDLL('librom1394.so.0')
    avc = c.CDLL('libavc1394.so.0')
    raw.raw1394_new_handle_on_port.argtypes = [c.c_int]
    raw.raw1394_new_handle_on_port.restype = c.c_void_p
    raw.raw1394_destroy_handle.argtypes = [c.c_void_p]
    raw.raw1394_get_nodecount.argtypes = [c.c_void_p]
    rom.rom1394_get_guid.argtypes = [c.c_void_p, c.c_uint16]
    rom.rom1394_get_guid.restype = c.c_uint64
    avc.avc1394_transaction_block2.argtypes = [c.c_void_p, c.c_uint16, c.POINTER(c.c_uint32),
                                               c.c_int, c.POINTER(c.c_uint), c.c_int]
    avc.avc1394_transaction_block2.restype = c.POINTER(c.c_uint32)
    avc.avc1394_transaction_block_close.argtypes = [c.c_void_p]
    handle = raw.raw1394_new_handle_on_port(device.card)
    if not handle:
        return 'unknown'
    try:
        for node in range(raw.raw1394_get_nodecount(handle)):
            if rom.rom1394_get_guid(handle, node) != int(guid, 16):
                continue
            # STATUS, VCR subunit 0, MEDIUM_INFO. No transport/control command.
            # MEDIUM INFO uses 0x7f for both operands (not the usual 0xff).
            request = (c.c_uint32 * 2)(0x0120da7f, 0x7fffffff)
            length = c.c_uint()
            response = avc.avc1394_transaction_block2(handle, node, request, 2, c.byref(length), 1)
            try:
                return decode_medium(response[0]) if response and length.value else 'unknown'
            finally:
                avc.avc1394_transaction_block_close(handle)
        return 'disconnected'
    finally:
        raw.raw1394_destroy_handle(handle)


class TapeChangeWatcher(QObject):
    ready = Signal()
    message = Signal(str)

    def __init__(self, guid, parent=None):
        super().__init__(parent)
        self.guid = guid
        self.removed = False
        self.present_count = 0
        self.enabled = False
        self.process = QProcess(self)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.poll)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.setInterval(3000)
        self.deadline.timeout.connect(self.process.kill)

    def start(self):
        self.enabled = True
        self.timer.start()
        self.poll()

    def poll(self):
        if not self.enabled or self.process.state() != QProcess.ProcessState.NotRunning:
            return
        args = [] if getattr(sys, 'frozen', False) else ['-m', 'minidv_capture']
        self.process.start(sys.executable, args + ['--media-status', self.guid])
        self.deadline.start()

    def finished(self, code, status):
        self.deadline.stop()
        result = bytes(self.process.readAllStandardOutput()).decode(errors='replace').strip()
        self.process.readAllStandardError()
        if self.enabled:
            self.observe(result if code == 0 and status == QProcess.ExitStatus.NormalExit else 'unknown')

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.observe('unsupported')

    def observe(self, result):
        if not self.enabled:
            return
        if result == 'unsupported':
            self.stop()
            self.message.emit('Automatic tape detection is unavailable. Use Start next tape after changing the cassette.')
        elif result == 'absent':
            self.removed = True
            self.present_count = 0
            self.message.emit('Cassette removed. Insert the next tape; capture will start automatically.')
        elif result == 'present':
            if self.removed:
                self.present_count += 1
                if self.present_count >= 2:
                    self.stop()
                    self.ready.emit()
            else:
                self.message.emit('Automatic mode: remove this cassette, then insert the next tape.')
        else:
            self.present_count = 0
            if result == 'disconnected':
                self.removed = False
            self.message.emit('Waiting for a reliable cassette status. You can also use Start next tape.')

    def stop(self):
        self.enabled = False
        self.timer.stop()
        self.deadline.stop()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)
