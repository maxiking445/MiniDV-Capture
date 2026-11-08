"""Bounded capture recovery: reset, confirmed STOP/overlap, new DV segment."""
import json
from pathlib import Path
import sys
import time
from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from .tape_change import pending_queries


class AutomaticRecovery(QObject):
    message = Signal(dict, str)
    failed = Signal(dict)

    def __init__(self, captures, controller, parent=None):
        super().__init__(parent)
        self.captures, self.controller = captures, controller
        self.session = None
        self.stage = ''
        self.allow_resume = False
        self.transport = QProcess(self)
        self.transport.finished.connect(self.transport_finished)
        self.transport.errorOccurred.connect(self.transport_error)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll)
        controller.finished.connect(self.controller_finished)
        captures.recovery_requested.connect(self.start)
        captures.recovery_guard = self

    @property
    def busy(self):
        return self.session is not None or self.transport.state() != QProcess.ProcessState.NotRunning or self.controller.busy

    def start(self, session):
        try:
            self.start_step(session)
        except (OSError, RuntimeError, ValueError) as exc:
            self.fail(str(exc))

    def start_step(self, session):
        if self.busy:
            session.want_recovery = False
            self.captures.store.update(session.job, state='error', error='Another recovery is still pending; raw footage kept.')
            self.failed.emit(session.job)
            return
        self.session = session
        job = session.job
        attempts = job.get('recovery_attempts', 0)
        if attempts >= 2 or pending_queries():
            self.fail('Automatic recovery stopped: retry limit reached or another camera query is pending. Raw footage kept.')
            return
        self.address = Path(session.device.bus).name.lower()
        health = self.captures.health
        if health and (not health.ready or health.error):
            self.fail('Kernel monitoring is unavailable; automatic restart refused.')
            return
        self.fault_serial = health.fault_serials.get(self.address, 0) if health else 0
        self.captures.store.update(job, state='recovering', capture_incomplete=True,
                                   recovery_attempts=attempts + 1)
        self.message.emit(job, 'Restarting FireWire after stalled capture. Administrator authorization may be required. Raw footage is kept.')
        self.stage = 'controller'
        self.controller.start(self.address)

    def controller_finished(self, success, message):
        if self.session is None or self.stage != 'controller':
            return
        if not success:
            self.fail(message)
            return
        self.stage = 'release'
        self.deadline = time.monotonic() + 10
        self.timer.start()
        self.poll()

    def poll(self):
        try:
            self.poll_step()
        except (OSError, RuntimeError, ValueError) as exc:
            self.fail(str(exc))

    def poll_step(self):
        if self.session is None:
            return
        if time.monotonic() >= self.deadline:
            if self.transport.state() != QProcess.ProcessState.NotRunning:
                self.transport.kill()
            self.fail('Recovery timed out. Camera STOP/position is not confirmed; stop playback manually. No new capture was started.')
            return
        if self.stage != 'release' or self.session.active:
            return
        health = self.captures.health
        if health:
            if not health.ready or health.error or health.fault_serials.get(self.address, 0) != self.fault_serial:
                self.fail('A new kernel fault occurred during restart; automatic capture refused.')
                return
            # Only a verified completed controller restart can clear the old latch.
            health.live_faults.discard(self.address)
        paths = list(Path(self.session.job['directory']).glob(self.session.output_name + '*.dv'))
        if not paths:
            self.fail('No saved DV checkpoint; automatic positioning refused.')
            return
        checkpoint = max(paths, key=lambda p: (p.stat().st_mtime_ns, p.name))
        args = [] if getattr(sys, 'frozen', False) else ['-m', 'minidv_capture']
        self.stage = 'position'
        self.deadline = time.monotonic() + 150
        self.message.emit(self.session.job, 'Controller restarted. Stopping the camera and rewinding to three minutes before the last saved scene.')
        self.transport.start(sys.executable, args + ['--recover-transport', self.session.device.guid, str(checkpoint)])

    def transport_error(self, error):
        if error == QProcess.ProcessError.FailedToStart and self.session is not None:
            self.fail('Could not start camera positioning helper: ' + self.transport.errorString())

    def transport_finished(self, code, status):
        output = bytes(self.transport.readAllStandardOutput()).decode(errors='replace')
        error = bytes(self.transport.readAllStandardError()).decode(errors='replace')
        if self.session is None or self.stage != 'position':
            return
        if code != 0 or status != QProcess.ExitStatus.NormalExit:
            self.fail(error or 'Camera positioning failed; no capture resumed.')
            return
        try:
            result = json.loads(output)
            if not isinstance(result, dict) or result.get('prepared') is not True:
                raise ValueError('Camera position was not confirmed')
            job = self.session.job
            self.captures.store.update(job, state='error', recovery_position=result,
                                      capture_incomplete=True, error='')
            self.allow_resume = True
            self.captures.resume(job, automatic=True)
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            self.fail(str(exc))
            return
        finally:
            self.allow_resume = False
        self.timer.stop()
        self.session = None
        self.stage = ''
        self.message.emit(job, 'Capture resumed in a new DV segment with overlap. Segments will be joined when capture finishes normally.')

    def fail(self, message):
        self.timer.stop()
        if self.transport.state() != QProcess.ProcessState.NotRunning:
            self.transport.kill()
            message += ' Camera STOP is unconfirmed; stop playback manually.'
        if self.session is None:
            return
        job = self.session.job
        self.session.want_recovery = False
        self.session = None
        self.stage = ''
        try:
            self.captures.store.update(job, state='error', capture_incomplete=True, error=message)
        except OSError as exc:
            job.update(state='error', capture_incomplete=True, error=message + f' Could not save state: {exc}')
        self.failed.emit(job)

    def cancel(self, notify=True):
        self.timer.stop()
        self.controller.cancel()
        if self.transport.state() != QProcess.ProcessState.NotRunning:
            self.transport.kill()
        if self.session:
            job = self.session.job
            self.session.want_recovery = False
            self.session.reason = 'cancel'
            self.session = None
            self.stage = ''
            self.captures.store.update(job, state='cancelled', capture_incomplete=True,
                error='Automatic recovery cancelled. Stop playback on the camera. All recorded segments are kept.')
            if notify:
                self.failed.emit(job)
