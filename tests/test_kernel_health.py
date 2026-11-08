from dataclasses import replace
from unittest.mock import patch, Mock
import unittest
import json

from PySide6.QtCore import QProcess
from minidv_capture.firewire_health import FireWireHealth
from test_core import APP, DEVICE

DMA_FAULT = 'firewire_ohci 0000:03:00.0: AMD-Vi: Event logged [IO_PAGE_FAULT domain=0x0011 address=0xffeeb000 flags=0x0050]'
FAULT = 'firewire_ohci 0000:03:00.0: DMA context still active (0x40000411)'


class KernelHealthTests(unittest.TestCase):
    def setUp(self):
        self.health = FireWireHealth()
        self.device = replace(DEVICE, bus='/sys/devices/pci0000:00/0000:03:00.0')

    def tearDown(self):
        self.health.stop()
        self.health.deleteLater()
        APP.processEvents()

    def test_live_dma_fault_warns_without_stopping_or_blocking_capture(self):
        faults, warnings = [], []
        self.health.fault.connect(lambda *args: faults.append(args))
        self.health.warning.connect(warnings.append)
        self.health.following, self.health.ready, self.health.error = True, True, ''
        for _ in range(100):
            self.health.observe(DMA_FAULT)
        self.health.check(self.device)
        self.assertFalse(faults)
        self.assertFalse(self.health.live_faults)
        self.assertEqual(len(warnings), 1)
        # A subsequent actual DMA stall must still stop capture.
        self.health.observe(FAULT)
        self.assertEqual(len(faults), 1)
        with self.assertRaises(RuntimeError):
            self.health.check(self.device)

    def test_pending_check_does_not_allow_capture(self):
        with self.assertRaisesRegex(RuntimeError, 'Checking the kernel log'):
            self.health.check(self.device)

    def test_fault_is_latched_per_controller_and_not_spammed(self):
        reports = []
        self.health.fault.connect(lambda address, message: reports.append((address, message)))
        self.health.ready, self.health.error = True, ''
        self.health.following = True
        for _ in range(100):
            self.health.observe(FAULT)
        self.assertEqual(len(reports), 1)
        with self.assertRaisesRegex(RuntimeError, 'kernel DMA/driver fault'):
            self.health.check(self.device)
        self.health.check(replace(self.device, bus='/sys/0000:07:00.0'))

    def test_historical_fault_warns_but_allows_capture_after_check(self):
        warnings, faults = [], []
        self.health.warning.connect(warnings.append)
        self.health.fault.connect(lambda *args: faults.append(args))
        self.health.observe(FAULT)
        self.health.observe(FAULT)
        self.health.observe('-- cursor: s=test;b=boot;i=42')
        with patch.object(self.health.process, 'start'):
            self.health.finished(0, QProcess.ExitStatus.NormalExit)
        self.health.check(self.device)
        self.assertEqual(len(warnings), 1)
        self.assertFalse(faults)
        self.assertFalse(self.health.live_faults)

    def test_new_fault_after_historical_warning_still_stops_capture(self):
        reports = []
        self.health.fault.connect(lambda *args: reports.append(args))
        self.health.observe(FAULT)
        self.health.following = True
        self.health.ready, self.health.error = True, ''
        self.health.observe(FAULT)
        self.health.observe(FAULT)
        self.assertEqual(len(reports), 1)
        with self.assertRaisesRegex(RuntimeError, 'kernel DMA/driver fault'):
            self.health.check(self.device)

    def test_reverse_snapshot_footer_does_not_replay_historical_fault(self):
        reports = []
        self.health.fault.connect(lambda *args: reports.append(args))
        def entry(cursor, timestamp):
            return json.dumps({'__CURSOR': cursor, '__MONOTONIC_TIMESTAMP': str(timestamp), 'MESSAGE': FAULT})
        self.health.observe(entry('newest', 200))
        self.health.observe(entry('older', 100))
        self.health.observe('-- cursor: boot-start')
        with patch.object(self.health.process, 'start') as start:
            self.health.finished(0, QProcess.ExitStatus.NormalExit)
        self.assertIn('--after-cursor=newest', start.call_args.args[1])
        self.health.observe(entry('older', 100))
        self.health.observe(entry('newest', 200))
        self.health.check(self.device)
        self.assertFalse(reports)
        self.health.observe(entry('live', 300))
        self.assertEqual(len(reports), 1)
        with self.assertRaises(RuntimeError):
            self.health.check(self.device)

    def test_normal_messages_and_other_devices_are_not_firewire_faults(self):
        for line in ['firewire_ohci 0000:03:00.0: added OHCI v1.0 device',
                     'nvme 0000:02:00.0: AMD-Vi: Event logged [IO_PAGE_FAULT]',
                     'firewire_core 0000:03:00.0: failed to allocate broadcast channel']:
            self.health.observe(line)
        self.assertFalse(self.health.faults)

    def test_dma_stall_is_detected_without_iommu_error(self):
        self.health.observe('firewire_ohci 0000:03:00.0: DMA context still active (0x40000411)')
        self.assertIn('0000:03:00.0', self.health.faults)

    def test_snapshot_is_current_boot_bounded_and_has_timeout(self):
        with patch.object(self.health.process, 'start') as start:
            self.health.start()
        program, args = start.call_args.args
        self.assertEqual(program, 'journalctl')
        self.assertIn('-b', args)
        self.assertEqual(args[args.index('-n') + 1], '200')
        self.assertTrue(self.health.deadline.isActive())

    def test_snapshot_cursor_covers_gap_before_live_monitor(self):
        self.health.observe('-- cursor: s=test;b=boot;i=42')
        with patch.object(self.health.process, 'start') as start:
            self.health.finished(0, QProcess.ExitStatus.NormalExit)
        self.assertIn('--after-cursor=s=test;b=boot;i=42', start.call_args.args[1])
        self.assertIn('--follow', start.call_args.args[1])
        self.assertTrue(self.health.ready)

    def test_empty_snapshot_with_valid_cursor_is_supported(self):
        self.health.observe('-- cursor: s=test;b=boot;i=0')
        with patch.object(self.health.process, 'start'):
            self.health.finished(1, QProcess.ExitStatus.NormalExit)
        self.health.check(self.device)

    def test_inaccessible_log_and_dead_monitor_fail_closed(self):
        for following in [False, True]:
            self.health.following = following
            self.health.finished(1, QProcess.ExitStatus.NormalExit)
            with self.assertRaisesRegex(RuntimeError, 'unavailable'):
                self.health.check(self.device)

    def test_partial_lines_are_parsed_and_memory_is_bounded(self):
        data = (FAULT + '\n').encode()
        with patch.object(self.health.process, 'readAllStandardOutput', side_effect=[data[:30], data[30:], b'x' * 100_000]):
            self.health.read_output()
            self.assertFalse(self.health.faults)
            self.health.read_output()
            self.assertIn('0000:03:00.0', self.health.faults)
            self.health.read_output()
            self.assertLessEqual(len(self.health.buffer), 8192)

    def test_timeout_does_not_restart_or_wait_for_child(self):
        with patch.object(self.health.process, 'kill') as kill, patch.object(self.health.process, 'waitForFinished') as wait:
            self.health.timed_out()
        kill.assert_called_once()
        wait.assert_not_called()
        self.assertTrue(self.health.stopping)
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            self.health.check(self.device)
