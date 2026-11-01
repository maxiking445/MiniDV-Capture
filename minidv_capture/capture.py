from pathlib import Path
import os
import shutil
import time
import uuid
import sys
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal
from .devices import Device, discover
from .process import available, executable, interrupt
from .storage import Store


def capture_arguments(device: Device, manual: bool, directory: Path, rewind=False, broadcast=False,
                     output_name='capture'):
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
    return args + [str(directory / output_name)]


class CaptureSession(QObject):
    changed = Signal()
    log = Signal(str)
    completed = Signal(dict)
    failed = Signal(dict)

    def __init__(self, store: Store, job: dict, device: Device, parent=None, resume=False):
        super().__init__(parent)
        self.store, self.job, self.device = store, job, device
        self.resume = resume
        self.manual = True if resume else job['options']['manual']
        self.rewind = False if resume else job['options'].get('rewind', False)
        self.output_name = f'capture-resume-{uuid.uuid4().hex}' if resume else 'capture'
        self.process = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert('LC_ALL', 'C')
        self.process.setProcessEnvironment(env)
        self.process.setStandardOutputFile(QProcess.nullDevice())
        self.process.readyReadStandardError.connect(self.read_log)
        self.process.started.connect(self.process_started)
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
        self.process_started_ok = False
        self.stop_process = QProcess(self)
        self.stop_deadline = QTimer(self)
        self.stop_deadline.setSingleShot(True)
        self.stop_deadline.setInterval(3000)
        self.stop_deadline.timeout.connect(self.transport_stop_timeout)
        self.stop_process.finished.connect(self.transport_stopped)

    def stop_transport(self):
        if not self.process_started_ok:
            return
        args = [] if getattr(sys, 'frozen', False) else ['-m', 'minidv_capture']
        self._write_log('Requesting camcorder STOP via AV/C')
        self.stop_process.start(sys.executable, args + ['--transport-stop', self.device.guid])
        self.stop_deadline.start()

    def transport_stop_timeout(self):
        self.stop_process.kill()
        message = 'Camcorder STOP timed out. Stop playback on the camera if it is still running.'
        self._write_log(message)
        self.log.emit(message)

    def transport_stopped(self, code, status):
        self.stop_deadline.stop()
        result = bytes(self.stop_process.readAllStandardOutput()).decode(errors='replace').strip()
        message = ('Camcorder acknowledged STOP.' if code == 0 and result == 'stopped' else
                   'Camcorder STOP was not confirmed. Stop playback on the camera if it is still running.')
        self._write_log(message)
        self.log.emit(message)

    @property
    def active(self):
        return not self.finished_once

    def start(self):
        peers = [d for d in discover() if d.bus == self.device.bus]
        broadcast = self.device.card >= 0 and len(peers) == 1 and peers[0].guid == self.device.guid
        self.process.setProgram(executable('dvgrab'))
        self.process.setArguments(capture_arguments(self.device, self.manual,
                                 Path(self.job['directory']), self.rewind,
                                 broadcast=broadcast and not self.resume, output_name=self.output_name))
        self.log.emit('dvgrab ' + ' '.join(self.process.arguments()))
        self._write_log('Starting capture process')
        self.process.start()
        self.timer.start()

    def process_started(self):
        self.process_started_ok = True
        self._write_log('dvgrab process started successfully')
        self.log.emit('dvgrab started; waiting for DV data')
        self.changed.emit()

    def _write_log(self, message):
        """Keep lifecycle events beside dvgrab output for diagnosing hangs."""
        try:
            with self.logfile.open('a') as f:
                f.write(f'\n[{time.strftime("%Y-%m-%d %H:%M:%S")}] {message}\n')
        except OSError as exc:
            self.log.emit(f'Could not write capture lifecycle log: {exc}')

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
            segments = list(Path(self.job['directory']).glob(self.output_name + '*.dv'))
            size = sum(part.stat().st_size for part in segments if part.is_file())
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
            elif self.bytes and now - self.last_data >= self.job['options'].get('signal_timeout', 60):
                self.stop('complete', 'No DV data for 60 seconds; treating this as tape end and starting conversion.')
            elif self.first_data is not None and self.job['options'].get('duration', 0) and now - self.first_data >= self.job['options']['duration'] * 60:
                self.stop('complete')
        except OSError as exc:
            self.stop('error', str(exc))
        self.changed.emit()

    def stop(self, reason='complete', error=''):
        if self.finished_once or self.reason:
            return
        self.reason = reason
        self.stop_transport()
        self.job['error'] = error
        self.timer.stop()
        self._write_log(f'Stopping capture: reason={reason}; {error or "no additional error"}')
        self.log.emit(f'Stopping capture: {reason}' + (f' ({error})' if error else ''))
        interrupt(self.process)

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.job['error'] = 'Could not start dvgrab: ' + self.process.errorString()
            self.reason = 'error'
            self._write_log(self.job['error'])
            self.finished(-1, QProcess.ExitStatus.CrashExit)

    def finished(self, code, status):
        if self.finished_once:
            return
        if not self.reason:
            self.stop_transport()
        self.read_log()
        self._write_log(f'dvgrab exited: code={code}; status={status}; requested_stop={self.reason or "none"}')
        self.finished_once = True
        self.timer.stop()
        segments = list(Path(self.job['directory']).glob(self.output_name + '*.dv'))
        self.bytes = sum(part.stat().st_size for part in segments if part.is_file())
        regular = self.reason == 'complete' or (
            not self.reason and code == 0 and status == QProcess.ExitStatus.NormalExit
            and not self.job['options']['manual'])
        # Never accept a forced kill, empty file, extra segments or reported drops.
        regular = regular and code == 0 and status != QProcess.ExitStatus.CrashExit and self.bytes > 0 and not self.damaged
        regular = regular and len(segments) == 1
        if regular:
            try:
                if self.resume:
                    self.store.finish_resume_merge(self.job)
                else:
                    self.store.update(self.job, state='queued', bytes=self.bytes,
                                      capture_incomplete=False, error='')
                self.completed.emit(self.job)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.store.update(self.job, state='error', capture_incomplete=True,
                                  error=f'Could not safely append the resumed capture: {exc}')
                self.failed.emit(self.job)
        else:
            error = self.job.get('error') or ('Cancelled; raw footage kept.' if self.reason == 'cancel'
                    else 'Incomplete capture or damaged/dropped frames. Check the raw footage and capture.log.')
            self.store.update(self.job, state='cancelled' if self.reason == 'cancel' else 'error',
                              bytes=self.bytes, capture_incomplete=True, error=error)
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
        self.check_transport_stopped(device)
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

    def resume(self, job):
        self.check_transport_stopped(Device(**job['device']))
        if not job.get('capture_incomplete'):
            raise ValueError('This tape has no interrupted capture to continue.')
        if job['state'] not in {'interrupted', 'error', 'cancelled'}:
            raise ValueError('Only interrupted or incomplete captures can be continued.')
        raw = Path(job['raw'])
        if raw.is_symlink() or not raw.is_file() or raw.stat().st_size <= 0:
            raise ValueError('No partial DV capture is available to continue.')
        device = next((d for d in discover() if d.guid == job['device']['guid']), None)
        if device is None:
            raise RuntimeError('The original camera is not connected. Connect it over FireWire and rescan.')
        if not device.accessible:
            raise RuntimeError('No read/write access to ' + device.node + '. Enable device access through Setup.')
        if any(s.active and (s.device.guid == device.guid or s.device.bus == device.bus) for s in self.sessions.values()):
            raise RuntimeError('A capture is already running on this FireWire bus.')
        if shutil.disk_usage(job['directory']).free < 2 * 1024**3:
            raise RuntimeError('At least 2 GiB of free space is required to continue a capture.')
        self.store.update(job, state='capturing', capture_incomplete=True, error='')
        session = CaptureSession(self.store, job, device, self, resume=True)
        previous = self.sessions.get(device.guid)
        if previous:
            previous.deleteLater()
        self.sessions[device.guid] = session
        session.changed.connect(self.changed)
        session.log.connect(self.log)
        session.completed.connect(self.completed)
        session.failed.connect(self.failed)
        session.start()
        self.changed.emit()
        return session

    def check_transport_stopped(self, device):
        for session in self.sessions.values():
            if (session.device.bus == device.bus and
                    session.stop_process.state() != QProcess.ProcessState.NotRunning):
                raise RuntimeError('Waiting for camcorder STOP to finish. Please retry shortly.')
