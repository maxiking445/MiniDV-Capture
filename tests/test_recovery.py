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
        with patch('minidv_capture.recovery.subprocess.Popen', return_value=process):
            recovery.run('0000:06:00.0')
        process.kill.assert_called_once()
        process.wait.assert_called_once_with(timeout=45)
        self.assertFalse(results[0][0])
        self.assertIn('timed out', results[0][1])
        recovery.deleteLater()
        APP.processEvents()
