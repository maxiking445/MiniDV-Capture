from pathlib import Path
import runpy
import unittest
from unittest.mock import patch, Mock
from minidv_capture.recovery import FireWireRecovery
from test_core import APP

helper = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/recover-firewire.py'))


class RecoveryTests(unittest.TestCase):
    def test_bus_reset_is_never_automated(self):
        choose = helper['isolated_reset_methods']
        self.assertEqual(choose(Path('/unused'), 'pm bus'), ['pm'])
        self.assertEqual(choose(Path('/unused'), 'bus'), [])

    def test_invalid_pci_target_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'Invalid PCI'):
            helper['recover']('../../etc')

    def test_timeout_kills_helper_without_unbounded_wait(self):
        import subprocess
        recovery = FireWireRecovery()
        results = []
        recovery.finished.connect(lambda ok, text: results.append((ok, text)))
        process = Mock()
        process.wait.side_effect = subprocess.TimeoutExpired('recovery', 45)
        with patch('minidv_capture.recovery.subprocess.Popen', return_value=process), \
                patch('minidv_capture.recovery.installed_service', return_value=False):
            recovery.run('0000:06:00.0')
        process.kill.assert_called_once()
        process.wait.assert_called_once_with(timeout=45)
        self.assertFalse(results[0][0])
        self.assertIn('timed out', results[0][1])
        recovery.deleteLater()
        APP.processEvents()


class ControllerRestartTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pci = self.root / 'devices'
        self.driver = self.root / 'drivers/firewire_ohci'
        self.driver.mkdir(parents=True)
        self.device = self.pci / '0000:06:00.0'
        self.device.mkdir(parents=True)
        (self.device / 'class').write_text('0x0c0010')
        (self.device / 'reset_method').write_text('pm bus')
        (self.device / 'driver').symlink_to(self.driver, target_is_directory=True)
        self.calls = []
        self.original_write = Path.write_text
        self.globals = helper['restart_controller'].__globals__
        self.context = patch.dict(self.globals, PCI=self.pci, DRIVER=self.driver,
                                  check_clients=Mock(return_value=[]), stop_waiters=Mock())
        self.context.start()
        self.addCleanup(self.context.stop)

    def write(self, path, data, *args, **kwargs):
        self.calls.append(path.name)
        if path == self.driver / 'unbind':
            (self.device / 'driver').unlink()
        elif path == self.driver / 'bind':
            (self.device / 'driver').symlink_to(self.driver, target_is_directory=True)
            node = self.device / 'fw8'
            node.mkdir(exist_ok=True)
            self.original_write(node / 'is_local', '1')
        elif path == self.device / 'reset':
            self.assertFalse((self.device / 'driver').exists(), 'Never reset a bound OHCI driver')
        return self.original_write(path, data, *args, **kwargs)

    def test_default_only_inspects_without_writes(self):
        with patch.object(Path, 'write_text', side_effect=AssertionError('must not write')):
            helper['recover'](self.device.name)

    def test_detach_reset_bind_and_verify_in_order(self):
        with patch.object(Path, 'write_text', autospec=True, side_effect=self.write):
            helper['restart_controller'](self.device.name, self.device, 'pm bus', 1000)
        self.assertEqual(self.calls, ['unbind', 'reset_method', 'reset', 'reset_method', 'bind'])
        self.assertEqual((self.device / 'reset_method').read_text(), 'pm bus')

    def test_failed_detach_never_resets_or_binds(self):
        with patch.object(Path, 'write_text', side_effect=OSError('unbind failed')):
            with self.assertRaisesRegex(OSError, 'unbind failed'):
                helper['restart_controller'](self.device.name, self.device, 'pm bus', 1000)
        self.assertTrue((self.device / 'driver').exists())
        self.assertFalse((self.device / 'reset').exists())

    def test_reset_failure_restores_binding_but_reports_failure(self):
        def write(path, data, *args, **kwargs):
            if path == self.device / 'reset':
                raise OSError('reset failed')
            return self.write(path, data, *args, **kwargs)
        with patch.object(Path, 'write_text', autospec=True, side_effect=write):
            with self.assertRaisesRegex(RuntimeError, 'no recovery success'):
                helper['restart_controller'](self.device.name, self.device, 'pm bus', 1000)
        self.assertTrue((self.device / 'driver').exists())

    def test_no_local_node_is_not_success(self):
        with patch.object(Path, 'write_text', autospec=True, side_effect=self.write), \
                patch.dict(self.globals, has_local_node=Mock(return_value=False)), \
                patch.object(self.globals['time'], 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'could not be verified'):
                helper['restart_controller'](self.device.name, self.device, 'pm bus', 1000)

    def test_live_client_blocks_detach(self):
        with patch.dict(self.globals, check_clients=Mock(side_effect=RuntimeError('still has FireWire open'))), \
                patch.object(Path, 'write_text') as write:
            with self.assertRaisesRegex(RuntimeError, 'still has FireWire open'):
                helper['restart_controller'](self.device.name, self.device, 'pm bus', 1000)
        write.assert_not_called()

    def test_pending_helper_prevents_second_restart(self):
        recovery = FireWireRecovery()
        recovery.process = Mock()
        recovery.process.poll.return_value = None
        results = []
        recovery.finished.connect(lambda ok, message: results.append(ok))
        with patch('minidv_capture.recovery.threading.Thread') as thread:
            recovery.start('0000:06:00.0')
        thread.assert_not_called()
        self.assertEqual(results, [False])
        recovery.deleteLater()

    def test_waiters_after_detach_prevent_reset(self):
        check = Mock(side_effect=[[], *([[self.root / '123']] * 20)])
        with patch.object(Path, 'write_text', autospec=True, side_effect=self.write), \
                patch.dict(self.globals, check_clients=check), \
                patch.object(self.globals['time'], 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'Release waiters remain'):
                helper['restart_controller'](self.device.name, self.device, 'pm bus', 1000)
        self.assertEqual(self.calls, ['unbind'])

    def test_bus_only_controller_is_refused(self):
        (self.device / 'reset_method').write_text('bus')
        with self.assertRaisesRegex(RuntimeError, 'bus reset refused'):
            helper['inspect_controller'](self.device.name)

    def test_multiple_controllers_are_refused(self):
        other = self.pci / '0000:07:00.0'
        other.mkdir()
        (other / 'class').write_text('0x0c0010')
        with self.assertRaisesRegex(RuntimeError, 'exactly one'):
            helper['inspect_controller'](self.device.name)


class RestartClientChecks(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.process = self.root / '100'
        (self.process / 'fd').mkdir(parents=True)
        (self.process / 'task/101').mkdir(parents=True)
        (self.process / 'task/101/wchan').write_text('fw_device_op_release')
        (self.process / 'comm').write_text('dvgrab')
        self.context = patch.dict(helper['check_clients'].__globals__, PROC=self.root)
        self.context.start()
        self.addCleanup(self.context.stop)

    def test_owned_release_waiter_without_live_fd_is_eligible(self):
        import os
        self.assertEqual(helper['check_clients'](os.getuid()), [self.process])

    def test_live_firewire_fd_is_refused_even_in_release_waiter(self):
        import os
        (self.process / 'fd/9').symlink_to('/dev/fw1')
        with self.assertRaisesRegex(RuntimeError, 'still has FireWire open'):
            helper['check_clients'](os.getuid())

    def test_unrelated_release_waiter_is_refused(self):
        import os
        (self.process / 'comm').write_text('another-app')
        with self.assertRaisesRegex(RuntimeError, 'Unidentified'):
            helper['check_clients'](os.getuid())

    def test_inaccessible_procfs_is_not_assumed_idle(self):
        import os
        with patch.object(Path, 'read_text', side_effect=PermissionError('denied')):
            with self.assertRaisesRegex(RuntimeError, 'Cannot inspect'):
                helper['check_clients'](os.getuid())


class RecoveryServicePolicyTests(unittest.TestCase):
    def test_policy_authorizes_only_fixed_unit_start_for_active_local_owner(self):
        installer = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/install-recovery-service.py'))
        unit, policy = installer['service_files']('0000:06:00.0', 1000, 'max')
        self.assertIn('subject.user === "max" && subject.local && subject.active', policy)
        self.assertIn('action.lookup("unit") === "minidv-firewire-recover.service"', policy)
        self.assertIn('action.lookup("verb") === "start"', policy)
        self.assertIn('Environment=PKEXEC_UID=1000', unit)
        self.assertIn('0000:06:00.0 --restart', unit)
        self.assertNotIn('[Install]', unit)
        for address, uid, user in [('bad', 1000, 'max'), ('0000:06:00.0', 0, 'root'),
                                   ('0000:06:00.0', 1000, 'x"; evil')]:
            with self.assertRaises(ValueError):
                installer['service_files'](address, uid, user)

    def test_installed_service_is_used_instead_of_mutable_privileged_script(self):
        recovery = FireWireRecovery()
        process = Mock()
        process.wait.return_value = 0
        with patch('minidv_capture.recovery.installed_service', return_value=True), \
                patch('minidv_capture.recovery.subprocess.Popen', return_value=process) as popen, \
                patch('minidv_capture.recovery.Path.read_text', return_value='Controller reinitialized'):
            recovery.run('0000:06:00.0')
        self.assertEqual(popen.call_args.args[0], ['systemctl', 'start', 'minidv-firewire-recover.service'])
        process.wait.assert_called_once_with(timeout=60)
        recovery.deleteLater()

    def test_cancel_does_not_kill_reset_midway_through_detach_bind(self):
        recovery = FireWireRecovery()
        recovery.process = Mock()
        recovery.cancel()
        recovery.process.kill.assert_not_called()
        self.assertTrue(recovery.cancelled.is_set())
        recovery.deleteLater()
