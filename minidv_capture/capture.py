from pathlib import Path
import os
import shutil
import time
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal
from .devices import Device, discover
from .process import available, executable, interrupt
from .storage import Store


def capture_arguments(device: Device, manual: bool, directory: Path, rewind=False, broadcast=False):
    args = ['-format', 'raw', '-size', '0', '-buffers', '500']
    if manual or broadcast:
        if device.card < 0:
            raise ValueError('FireWire controller not mapped. Rescan devices.')
        # -guid also forces CMP, which fails on cameras without online plugs.
        # A single camera on a known controller can use broadcast reception
        # while retaining AV/C transport control in automatic mode.
        args += ['-card', str(device.card), '-channel', '63']
        if manual:
            args += ['-noavc', '-nostop']
    else:
        args += ['-guid', '0x' + device.guid]
    if not manual and rewind:
        args += ['-rewind']
    return args + [str(directory / 'capture')]


class CaptureSession(QObject):
    changed = Signal()
    log = Signal(str)
    completed = Signal(dict)
    failed = Signal(dict)

    def __init__(self, store: Store, job: dict, device: Device, parent=None):
        super().__init__(parent)
        self.store, self.job, self.device = store, job, device
        self.process = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert('LC_ALL', 'C')
        self.process.setProcessEnvironment(env)
        self.process.setStandardOutputFile(QProcess.nullDevice())
        self.process.readyReadStandardError.connect(self.read_log)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.poll)
        self.started = self.last_data = time.monotonic()
        self.bytes = 0
        self.first_data = None
        self.rate = 0
        self.reason = ''
        self.finished_once = False
        self.damaged = False
        self.log_tail = ''
        self.logfile = Path(job['directory']) / 'capture.log'

    @property
    def active(self):
        return not self.finished_once

    def start(self):
        peers = [d for d in discover() if d.bus == self.device.bus]
        broadcast = self.device.card >= 0 and len(peers) == 1 and peers[0].guid == self.device.guid
        self.process.setProgram(executable('dvgrab'))
        self.process.setArguments(capture_arguments(self.device, self.job['options']['manual'],
                                 Path(self.job['directory']), self.job['options'].get('rewind', False),
                                 broadcast=broadcast))
        self.log.emit('dvgrab ' + ' '.join(self.process.arguments()))
        self.process.start()
        self.timer.start()

    def read_log(self):
        text = bytes(self.process.readAllStandardError()).decode(errors='replace')
        if not text:
            return
        try:
            with self.logfile.open('a') as f:
                f.write(text)
        except OSError as exc:
            self.stop('error', f'Cannot write log: {exc}')
        self.log.emit(text.strip())
        combined = (self.log_tail + text).lower()
        if 'dropped' in combined or 'bad frame' in combined or 'damaged frame' in combined:
            self.damaged = True
        self.log_tail = combined[-200:]

    def poll(self):
        now = time.monotonic()
        try:
            raw = Path(self.job['raw'])
            size = raw.stat().st_size if raw.exists() else 0
            self.rate = max(0, size - self.bytes)
            if size > self.bytes:
                self.last_data = now
                if self.first_data is None:
                    self.first_data = now
            self.bytes = size
            if not any(d.guid == self.device.guid for d in discover()):
                self.stop('error', 'Camera disconnected. Partial capture is kept.')
            elif shutil.disk_usage(self.job['directory']).free < 512 * 1024**2:
                self.stop('error', 'Less than 512 MiB free. Capture stopped to protect your data.')
            elif not self.bytes and now - self.started > (900 if self.job['options'].get('rewind') else 180):
                self.stop('error', 'No DV data received. Check PLAYER/VCR mode and PLAY.')
            elif self.bytes and now - self.last_data > self.job['options'].get('signal_timeout', 30):
                self.stop('error', 'Signal lost: no new DV data for 30 seconds. Check manually whether the tape has ended.')
            elif self.first_data is not None and self.job['options'].get('duration', 0) and now - self.first_data >= self.job['options']['duration'] * 60:
                self.stop('complete')
        except OSError as exc:
            self.stop('error', str(exc))
        self.changed.emit()

    def stop(self, reason='complete', error=''):
        if self.finished_once or self.reason:
            return
        self.reason = reason
        self.job['error'] = error
        self.timer.stop()
        interrupt(self.process)

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.job['error'] = 'Could not start dvgrab: ' + self.process.errorString()
            self.reason = 'error'
            self.finished(-1, QProcess.ExitStatus.CrashExit)

    def finished(self, code, status):
        if self.finished_once:
            return
        self.read_log()
        self.finished_once = True
        self.timer.stop()
        raw = Path(self.job['raw'])
        self.bytes = raw.stat().st_size if raw.exists() else 0
        regular = self.reason == 'complete' or (
            not self.reason and code == 0 and status == QProcess.ExitStatus.NormalExit
            and not self.job['options']['manual'])
        # Never accept a forced kill, empty file, extra segments or reported drops.
        regular = regular and code == 0 and status != QProcess.ExitStatus.CrashExit and self.bytes > 0 and not self.damaged
        segments = list(Path(self.job['directory']).glob('capture*.dv'))
        regular = regular and len(segments) == 1
        if regular:
            self.store.update(self.job, state='queued', bytes=self.bytes, error='')
            self.completed.emit(self.job)
        else:
            error = self.job.get('error') or ('Cancelled; raw footage kept.' if self.reason == 'cancel'
                    else 'Incomplete capture or damaged/dropped frames. Check the raw footage and capture.log.')
            self.store.update(self.job, state='cancelled' if self.reason == 'cancel' else 'error',
                              bytes=self.bytes, error=error)
            self.failed.emit(self.job)
        self.changed.emit()


class CaptureManager(QObject):
    changed = Signal()
    log = Signal(str)
    completed = Signal(dict)
    failed = Signal(dict)

    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self.store = store
        self.sessions = {}

    def active(self):
        return [s for s in self.sessions.values() if s.active]

    def start(self, device: Device, folder: Path, label: str, options: dict):
        if not available('dvgrab'):
            raise RuntimeError('dvgrab is missing. Install it through Setup.')
        fresh = {d.guid: d for d in discover()}.get(device.guid)
        if fresh is None:
            raise RuntimeError('Camera disconnected.')
        if not fresh.accessible:
            raise RuntimeError('No read/write access to ' + fresh.node + '. Enable device access through Setup.')
        # Manual broadcast reception cannot isolate two senders on the same bus.
        peers = [d for d in discover() if d.bus == fresh.bus]
        if options['manual'] and len(peers) > 1:
            raise RuntimeError('Connect only one camera per FireWire bus in manual mode.')
        for session in self.active():
            if session.device.guid == fresh.guid or session.device.bus == fresh.bus:
                raise RuntimeError('A capture is already running on this FireWire bus. Parallel capture requires separate controllers.')
        folder = folder.expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(folder).free < 2 * 1024**3:
            raise RuntimeError('At least 2 GiB of free space is required (DV uses about 13 GB/hour).')
        job = self.store.create(folder, label, fresh.to_dict(), dict(options))
        session = CaptureSession(self.store, job, fresh, self)
        previous = self.sessions.get(fresh.guid)
        if previous:
            previous.deleteLater()
        self.sessions[fresh.guid] = session
        session.changed.connect(self.changed)
        session.log.connect(self.log)
        session.completed.connect(self.completed)
        session.failed.connect(self.failed)
        session.start()
        self.changed.emit()
        return session
