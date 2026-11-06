from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from minidv_capture.devices import blocked_firewire_tasks
from minidv_capture.capture import CaptureManager
from test_core import APP, DEVICE, options


class FireWireHealthTests(unittest.TestCase):
    def test_detects_blocked_worker_even_when_leader_has_exited(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for tid, wait in [('100', '0'), ('101', 'fw_device_op_release'), ('102', 'futex_wait')]:
                task = root / '100' / 'task' / tid
                task.mkdir(parents=True)
                (task / 'wchan').write_text(wait)
            self.assertEqual(blocked_firewire_tasks(root), ['101'])

    def test_pending_query_prevents_capture_and_resume(self):
        manager = CaptureManager(Mock())
        with patch('minidv_capture.capture.blocked_firewire_tasks', return_value=[]), \
                patch('minidv_capture.capture.pending_queries', return_value=True):
            with self.assertRaisesRegex(RuntimeError, 'cassette detection'):
                manager.start(DEVICE, Path('/tmp'), 'Tape', options())
            with self.assertRaisesRegex(RuntimeError, 'cassette detection'):
                manager.resume({'device': DEVICE.to_dict()})
        manager.store.create.assert_not_called()
        manager.store.update.assert_not_called()
        manager.deleteLater()

    def test_blocked_driver_prevents_new_jobs_and_resume(self):
        store = Mock()
        manager = CaptureManager(store)
        try:
            with patch('minidv_capture.capture.blocked_firewire_tasks', return_value=['101']):
                with self.assertRaisesRegex(RuntimeError, 'FireWire driver is blocked'):
                    manager.start(DEVICE, Path('/tmp'), 'Tape', options())
                with self.assertRaisesRegex(RuntimeError, 'FireWire driver is blocked'):
                    manager.resume({'device': DEVICE.to_dict()})
            store.create.assert_not_called()
            store.update.assert_not_called()
        finally:
            manager.deleteLater()
            APP.processEvents()
