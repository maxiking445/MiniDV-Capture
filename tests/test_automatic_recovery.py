import json
from pathlib import Path
from unittest.mock import Mock, patch
from PySide6.QtCore import QObject, Signal, QProcess
from minidv_capture.automatic_recovery import AutomaticRecovery
from minidv_capture.capture import CaptureManager, CaptureSession
from test_core import Base, DEVICE


class Controller(QObject):
    finished = Signal(bool, str)
    busy = False

    def __init__(self):
        super().__init__()
        self.start = Mock()
        self.cancel = Mock()


class AutomaticRecoveryTests(Base):
    def setUp(self):
        super().setUp()
        self.manager = CaptureManager(self.store)
        self.controller = Controller()
        self.auto = AutomaticRecovery(self.manager, self.controller)
        self.session = CaptureSession(self.store, self.job(auto_recover=True), DEVICE)
        Path(self.session.job['raw']).write_bytes(b'DV' * 72000)
        self.session.want_recovery = True
        self.session.reason = 'error'
        self.manager.sessions[DEVICE.guid] = self.session

    def tearDown(self):
        self.auto.timer.stop()
        self.auto.session = None
        self.session.deleteLater()
        self.auto.deleteLater()
        self.manager.deleteLater()
        self.controller.deleteLater()
        super().tearDown()

    def test_restart_waits_for_old_capture_to_exit_before_camera_control(self):
        self.auto.start(self.session)
        self.assertEqual(self.session.job['state'], 'recovering')
        self.assertEqual(self.session.job['recovery_attempts'], 1)
        self.controller.start.assert_called_once_with('bus')
        with patch.object(self.auto.transport, 'start') as start:
            self.controller.finished.emit(True, 'reinitialized')
            start.assert_not_called()
            self.session.finished_once = True
            self.auto.poll()
            start.assert_called_once()
            self.assertIn('--recover-transport', start.call_args.args[1])

    def test_failed_restart_never_starts_transport_or_capture(self):
        self.auto.start(self.session)
        with patch.object(self.auto.transport, 'start') as start, patch.object(self.manager, 'resume') as resume:
            self.controller.finished.emit(False, 'unbind failed')
        start.assert_not_called()
        resume.assert_not_called()
        self.assertEqual(self.session.job['state'], 'error')
        self.assertFalse(self.session.want_recovery)

    def test_only_verified_position_resumes_automatically(self):
        self.auto.start(self.session)
        self.auto.stage = 'position'
        result = json.dumps({'prepared': True, 'saved': '00:10:00:00', 'position': '00:06:59:00'}).encode()
        with patch.object(self.auto.transport, 'readAllStandardOutput', return_value=result), \
                patch.object(self.auto.transport, 'readAllStandardError', return_value=b''), \
                patch.object(self.manager, 'resume') as resume:
            self.auto.transport_finished(0, QProcess.ExitStatus.NormalExit)
        resume.assert_called_once_with(self.session.job, automatic=True)
        self.assertFalse(self.auto.allow_resume)
        self.assertIsNone(self.auto.session)

    def test_unconfirmed_position_never_resumes(self):
        self.auto.start(self.session)
        self.auto.stage = 'position'
        with patch.object(self.auto.transport, 'readAllStandardOutput', return_value=b'{"stopped": true}'), \
                patch.object(self.auto.transport, 'readAllStandardError', return_value=b''), \
                patch.object(self.manager, 'resume') as resume:
            self.auto.transport_finished(0, QProcess.ExitStatus.NormalExit)
        resume.assert_not_called()
        self.assertEqual(self.session.job['state'], 'error')

    def test_retry_budget_is_persistent(self):
        self.session.job['recovery_attempts'] = 2
        self.auto.start(self.session)
        self.controller.start.assert_not_called()
        self.assertIn('limit', self.session.job['error'])

    def test_new_kernel_fault_during_reset_blocks_positioning(self):
        health = Mock(ready=True, error='', fault_serials={'bus': 1}, live_faults={'bus'})
        self.manager.health = health
        self.auto.start(self.session)
        self.session.finished_once = True
        health.fault_serials['bus'] = 2
        with patch.object(self.auto.transport, 'start') as start:
            self.controller.finished.emit(True, 'reinitialized')
        start.assert_not_called()
        self.assertIn('new kernel fault', self.session.job['error'])
        self.assertIn('bus', health.live_faults)

    def test_pending_position_worker_keeps_capture_blocked_after_failure(self):
        self.auto.start(self.session)
        with patch.object(self.auto.transport, 'state', return_value=QProcess.ProcessState.Running), \
                patch.object(self.auto.transport, 'kill') as kill:
            self.auto.fail('timed out')
            self.assertTrue(self.auto.busy)
            with self.assertRaisesRegex(RuntimeError, 'recovery is still pending'):
                self.manager.check_transport_stopped(DEVICE)
        kill.assert_called_once()

    def test_cancel_prevents_late_success_from_starting_capture(self):
        self.auto.start(self.session)
        self.auto.cancel(notify=False)
        with patch.object(self.auto.transport, 'start') as start:
            self.controller.finished.emit(True, 'late success')
        start.assert_not_called()
        self.assertEqual(self.session.job['state'], 'cancelled')
