from pathlib import Path
import os
import shutil
import time
import uuid
import sys
import json
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal
from .devices import Device, discover, blocked_firewire_tasks
from .process import available, executable, interrupt, start_background
from .storage import Store, atomic_json
from .tape_change import pending_queries


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
    attention = Signal(dict, str)
    recovery_requested = Signal(object)

    def __init__(self, store: Store, job: dict, device: Device, parent=None, resume=False, automatic=False):
        super().__init__(parent)
        self.store, self.job, self.device = store, job, device
        self.resume = resume
        self.manual = (not automatic) if resume else job['options']['manual']
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
        self.merging = False
        self.damaged = False
        self.log_tail = ''
        self.stall_warned = False
        self.signal_interrupted = False
        self.want_recovery = False
        self.recovery_sent = False
        self.logfile = Path(job['directory']) / 'capture.log'
        self.process_started_ok = False
        self.stop_deadline = QTimer(self)
        self.stop_deadline.setSingleShot(True)
        self.stop_deadline.setInterval(7000)
        self.stop_deadline.timeout.connect(self.stop_timed_out)

    def stop_timed_out(self):
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return
        message = ('Capture process did not exit after interruption and forced termination. '
                   'FireWire may be blocked. No new capture will start on this bus. '
                   'Stop playback and power off the camera. Raw footage is kept; you can close the app.')
        if self.reason != 'cancel':
            self.reason = 'error'
        self._write_log(message)
        self.log.emit(message)
        # Keep the bus reserved and footage unavailable for conversion/deletion
        # until the child really exits. A timeout is not a completed capture.
        try:
            self.store.update(self.job, error=message, capture_incomplete=True)
        except OSError as exc:
            self.log.emit(f'Could not save capture error: {exc}')
        self.attention.emit(self.job, message)
        self.request_recovery()
        self.changed.emit()

    def request_recovery(self):
        if self.want_recovery and self.reason != 'cancel' and not self.recovery_sent:
            self.recovery_sent = True
            self.recovery_requested.emit(self)

    @property
    def active(self):
        return not self.finished_once or self.merging

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
        if self.reason or self.finished_once:
            return
        now = time.monotonic()
        try:
            segments = list(Path(self.job['directory']).glob(self.output_name + '*.dv'))
            size = sum(part.stat().st_size for part in segments if part.is_file())
            self.rate = max(0, size - self.bytes)
            if size > self.bytes:
                self.last_data = now
                if self.stall_warned:
                    self.signal_interrupted = True
                    message = 'DV data is arriving again. Check the recording for a gap before continuing.'
                    self._write_log(message)
                    self.log.emit(message)
                    self.attention.emit(self.job, message)
                self.stall_warned = False
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
                self.want_recovery = self.job['options'].get('auto_recover', False)
                timeout = self.job['options'].get('signal_timeout', 60)
                self.stop('error', f'No DV data for {timeout} seconds. Tape end is not confirmed. '
                          'Stop playback on the camera. Partial capture is kept; check the last saved footage '
                          'before resuming with at least one minute of overlap.')
            elif self.first_data is not None and self.job['options'].get('duration', 0) and now - self.first_data >= self.job['options']['duration'] * 60:
                self.stop('complete')
            elif self.bytes and now - self.last_data >= 10 and not self.stall_warned:
                self.stall_warned = True
                message = ('No DV data for 10 seconds. The tape may still be playing without being recorded. '
                           'Check the camera and stop playback if necessary. Waiting for data; '
                           'tape end has not been confirmed.')
                self._write_log(message)
                self.log.emit(message)
                self.attention.emit(self.job, message)
        except OSError as exc:
            self.stop('error', str(exc))
        self.changed.emit()

    def stop(self, reason='complete', error=''):
        if self.merging:
            if reason == 'cancel':
                self.reason = 'cancel'
                interrupt(self.merge_process)
            return
        if self.finished_once or self.reason:
            return
        self.reason = reason
        # dvgrab owns transport shutdown in automatic mode. Opening another
        # raw1394 handle here can wedge alongside its release in the kernel.
        if self.manual:
            self.log.emit('Stop playback on the camera; manual mode does not send AV/C STOP.')
        self.job['error'] = error
        self.timer.stop()
        # Schedule termination before persistence: even a full/unwritable disk
        # must not prevent sending the capture process its stop signal.
        interrupt(self.process)
        self.stop_deadline.start()
        if reason == 'error':
            try:
                self.store.update(self.job, error=error, bytes=self.bytes, capture_incomplete=True)
            except OSError as exc:
                self.log.emit(f'Could not save capture error: {exc}')
            self.attention.emit(self.job, error)
        self._write_log(f'Stopping capture: reason={reason}; {error or "no additional error"}')
        self.log.emit(f'Stopping capture: {reason}' + (f' ({error})' if error else ''))

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.job['error'] = 'Could not start dvgrab: ' + self.process.errorString()
            self.reason = 'error'
            self._write_log(self.job['error'])
            self.finished(-1, QProcess.ExitStatus.CrashExit)

    def finished(self, code, status):
        if self.finished_once:
            return
        self.read_log()
        self._write_log(f'dvgrab exited: code={code}; status={status}; requested_stop={self.reason or "none"}')
        self.finished_once = True
        self.stop_deadline.stop()
        self.timer.stop()
        segments = list(Path(self.job['directory']).glob(self.output_name + '*.dv'))
        self.bytes = sum(part.stat().st_size for part in segments if part.is_file())
        regular = self.reason == 'complete' or (
            not self.reason and code == 0 and status == QProcess.ExitStatus.NormalExit
            and not self.manual)
        # Never accept a forced kill, empty file, extra segments or reported drops.
        regular = regular and code == 0 and status != QProcess.ExitStatus.CrashExit and self.bytes > 0 and not self.damaged
        regular = regular and len(segments) == 1 and not self.signal_interrupted
        if regular:
            try:
                if self.resume:
                    self.start_merge()
                    return
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
                    else 'DV reception was interrupted and resumed; a gap may be missing. Check the raw footage and capture.log.'
                    if self.signal_interrupted else 'Incomplete capture or damaged/dropped frames. Check the raw footage and capture.log.')
            self.store.update(self.job, state='cancelled' if self.reason == 'cancel' else 'recovering' if self.want_recovery else 'error',
                              bytes=self.bytes, capture_incomplete=True, error=error)
            if self.want_recovery and self.reason != 'cancel':
                self.request_recovery()
            elif not self.recovery_sent:
                self.failed.emit(self.job)
        self.changed.emit()

    def start_merge(self):
        plan = self.store.finish_resume_merge(self.job, prepare_only=True)
        manifest = Path(self.job['directory']) / 'resume-merge.json'
        atomic_json(manifest, plan)
        self.store.update(self.job, state='merging')
        self.merging = True
        self.merge_process = QProcess(self)
        self.merge_process.finished.connect(self.merge_finished)
        self.merge_process.errorOccurred.connect(self.merge_error)
        args = [] if getattr(sys, 'frozen', False) else ['-m', 'minidv_capture']
        start_background(self.merge_process, sys.executable, args + ['--merge-dv', str(manifest)])
        self.changed.emit()

    def merge_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.merge_finished(-1, QProcess.ExitStatus.CrashExit)

    def merge_finished(self, code, status):
        if not self.merging:
            return
        self.merging = False
        output = bytes(self.merge_process.readAllStandardOutput()).decode(errors='replace')
        error = bytes(self.merge_process.readAllStandardError()).decode(errors='replace')
        try:
            if self.reason == 'cancel' or code != 0 or status != QProcess.ExitStatus.NormalExit:
                # The worker only copies: it never replaces or deletes sources.
                self.job.pop('resume_merge_pending', None)
                raise ValueError(error or 'DV merge interrupted; all source segments are kept.')
            result = json.loads(output)
            self.store.finish_resume_merge(self.job, prepared=result['fingerprint'])
            self.completed.emit(self.job)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.store.update(self.job, state='cancelled' if self.reason == 'cancel' else 'error',
                              capture_incomplete=True, error=str(exc))
            self.failed.emit(self.job)
        self.changed.emit()


class CaptureManager(QObject):
    changed = Signal()
    log = Signal(str)
    completed = Signal(dict)
    failed = Signal(dict)
    attention = Signal(dict, str)
    recovery_requested = Signal(object)

    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self.store = store
        self.sessions = {}
        self.health = None
        self.recovery_guard = None

    def active(self):
        return [s for s in self.sessions.values() if s.active]

    def start(self, device: Device, folder: Path, label: str, options: dict):
        self.check_transport_stopped(device)
        if not available('dvgrab'):
            raise RuntimeError('dvgrab is missing. Install it through Setup.')
        fresh = {d.guid: d for d in discover()}.get(device.guid)
        if fresh is None:
            raise RuntimeError('Camera disconnected.')
        if self.health is not None:
            self.health.check(fresh)
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
        session.attention.connect(self.attention)
        session.recovery_requested.connect(self.recovery_requested)
        session.start()
        self.changed.emit()
        return session

    def resume(self, job, automatic=False):
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
        if self.health is not None:
            self.health.check(device)
        if not device.accessible:
            raise RuntimeError('No read/write access to ' + device.node + '. Enable device access through Setup.')
        if any(s.active and (s.device.guid == device.guid or s.device.bus == device.bus) for s in self.sessions.values()):
            raise RuntimeError('A capture is already running on this FireWire bus.')
        if shutil.disk_usage(job['directory']).free < 2 * 1024**3:
            raise RuntimeError('At least 2 GiB of free space is required to continue a capture.')
        self.store.update(job, state='capturing', capture_incomplete=True, error='')
        session = CaptureSession(self.store, job, device, self, resume=True, automatic=automatic)
        previous = self.sessions.get(device.guid)
        if previous:
            previous.deleteLater()
        self.sessions[device.guid] = session
        session.changed.connect(self.changed)
        session.log.connect(self.log)
        session.completed.connect(self.completed)
        session.failed.connect(self.failed)
        session.attention.connect(self.attention)
        session.recovery_requested.connect(self.recovery_requested)
        session.start()
        self.changed.emit()
        return session

    def check_transport_stopped(self, device):
        if self.recovery_guard and self.recovery_guard.busy and not self.recovery_guard.allow_resume:
            raise RuntimeError('FireWire recovery is still pending; no new capture was started.')
        if self.health is not None:
            self.health.check(device)
        blocked = blocked_firewire_tasks()
        if blocked:
            raise RuntimeError(
                'The FireWire driver is blocked by an earlier capture (threads: '
                + ', '.join(blocked) + '). No new capture was started. '
                'Stop playback and power off the camera. If the driver remains blocked, '
                'restart the computer before retrying. Existing recordings are kept.')
        if pending_queries():
            raise RuntimeError('Waiting for cassette detection to release FireWire. Please retry shortly.')
