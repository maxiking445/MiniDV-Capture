import unittest
from unittest.mock import patch, Mock
import ctypes as c
from minidv_capture.tape_change import TapeChangeWatcher, decode_medium, query_medium
from test_core import APP, DEVICE


class TapeChangeTests(unittest.TestCase):
    def setUp(self):
        self.watcher = TapeChangeWatcher(DEVICE.guid)
        self.watcher.enabled = True
        self.starts = []
        self.watcher.ready.connect(lambda: self.starts.append(True))

    def tearDown(self):
        self.watcher.stop()
        self.watcher.deleteLater()
        APP.processEvents()

    def test_only_removed_then_stably_inserted_starts_once(self):
        for status in ('present', 'present', 'unknown', 'present'):
            self.watcher.observe(status)
        self.assertFalse(self.starts)
        self.watcher.observe('absent')
        self.watcher.observe('present')
        self.assertFalse(self.starts)
        self.watcher.observe('present')
        self.watcher.observe('present')
        self.assertEqual(self.starts, [True])

    def test_disconnect_and_errors_do_not_count_as_a_tape_change(self):
        for status in ('absent', 'disconnected', 'present', 'present', 'unknown', 'present'):
            self.watcher.observe(status)
        self.assertFalse(self.starts)

    def test_rejected_query_falls_back_without_starting(self):
        messages = []
        self.watcher.message.connect(messages.append)
        self.watcher.observe('unsupported')
        self.watcher.observe('absent')
        self.watcher.observe('present')
        self.watcher.observe('present')
        self.assertFalse(self.starts)
        self.assertIn('Start next tape', messages[-1])

    def test_stop_disarms_pending_change(self):
        self.watcher.observe('absent')
        self.watcher.stop()
        self.watcher.observe('present')
        self.watcher.observe('present')
        self.assertFalse(self.starts)

    def test_medium_responses_require_correct_stable_status(self):
        self.assertEqual(decode_medium(0x0c20da32), 'present')
        self.assertEqual(decode_medium(0x0c20da60), 'absent')
        for response in (0, 0x0f20da60, 0x0c20da7e, 0x0c20c160):
            self.assertEqual(decode_medium(response), 'unknown')
        self.assertEqual(decode_medium(0x0820daff), 'unsupported')
        self.assertEqual(decode_medium(0x0a20daff), 'unsupported')

    def test_query_targets_guid_and_uses_medium_info_status_operands(self):
        raw, rom, avc = Mock(), Mock(), Mock()
        raw.raw1394_new_handle_on_port.return_value = 1
        raw.raw1394_get_nodecount.return_value = 2
        rom.rom1394_get_guid.side_effect = [123, int(DEVICE.guid, 16)]
        def transaction(handle, node, request, length, response_length, retry):
            self.assertEqual(node, 1)
            self.assertEqual(list(request), [0x0120da7f, 0x7fffffff])
            self.assertEqual(length, 2)
            c.cast(response_length, c.POINTER(c.c_uint))[0] = 2
            return (c.c_uint32 * 2)(0x0c20da32, 0x30ffffff)
        avc.avc1394_transaction_block2.side_effect = transaction
        with patch('minidv_capture.tape_change.discover', return_value=[DEVICE]), patch('minidv_capture.tape_change.c.CDLL', side_effect=[raw, rom, avc]):
            self.assertEqual(query_medium(DEVICE.guid), 'present')
        raw.raw1394_destroy_handle.assert_called_once_with(1)

    def test_stop_targets_selected_guid_and_requires_acknowledgement(self):
        raw, rom, avc = Mock(), Mock(), Mock()
        raw.raw1394_new_handle_on_port.return_value = 1
        raw.raw1394_get_nodecount.return_value = 2
        rom.rom1394_get_guid.side_effect = [123, int(DEVICE.guid, 16)]
        def transaction(handle, node, request, length, response_length, retry):
            self.assertEqual(node, 1)
            self.assertEqual(list(request), [0x0020c460])
            self.assertEqual(length, 1)
            c.cast(response_length, c.POINTER(c.c_uint))[0] = 1
            return (c.c_uint32 * 1)(0x0920c460)
        avc.avc1394_transaction_block2.side_effect = transaction
        with patch('minidv_capture.tape_change.discover', return_value=[DEVICE]), patch('minidv_capture.tape_change.c.CDLL', side_effect=[raw, rom, avc]):
            self.assertEqual(query_medium(DEVICE.guid, stop_transport=True), 'stopped')
        raw.raw1394_destroy_handle.assert_called_once_with(1)
