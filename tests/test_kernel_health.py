from dataclasses import replace
from unittest.mock import patch, Mock
import unittest

from PySide6.QtCore import QProcess
from minidv_capture.firewire_health import FireWireHealth
from test_core import APP, DEVICE

FAULT = 'firewire_ohci 0000:06:00.0: AMD-Vi: Event logged [IO_PAGE_FAULT domain=0x0011 address=0xffeeb000 flags=0x0050]'


class KernelHealthTests(unittest.TestCase):
    def setUp(self):
        self.health = FireWireHealth()
        self.device = replace(DEVICE, bus='/sys/devices/pci0000:00/0000:06:00.0')

    def tearDown(self):
        self.health.stop()
        self.health.deleteLater()
        APP.processEvents()

    def test_pending_check_does_not_allow_capture(self):
        with self.assertRaisesRegex(RuntimeError, 'Checking the kernel log'):
            self.health.check(self.device)

    def test_fault_is_latched_per_controller_and_not_spammed(self):
        reports = []
        self.health.fault.connect(lambda address, message: reports.append((address, message)))
        self.health.ready, self.health.error = True, ''
        for _ in range(100):
            self.health.observe(FAULT)
        self.assertEqual(len(reports), 1)
        with self.assertRaisesRegex(RuntimeError, 'kernel DMA/driver fault'):
            self.health.check(self.device)
        self.health.check(replace(self.device, bus='/sys/0000:07:00.0'))

    def test_normal_messages_and_other_devices_are_not_firewire_faults(self):
        for line in ['firewire_ohci 0000:06:00.0: added OHCI v1.0 device',
                     'nvme 0000:02:00.0: AMD-Vi: Event logged [IO_PAGE_FAULT]',
                     'firewire_core 0000:06:00.0: failed to allocate broadcast channel']:
            self.health.observe(line)
        self.assertFalse(self.health.faults)

    def test_dma_stall_is_detected_without_iommu_error(self):
        self.health.observe('firewire_ohci 0000:06:00.0: DMA context still active (0x40000411)')
        self.assertIn('0000:06:00.0', self.health.faults)

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
            self.assertIn('0000:06:00.0', self.health.faults)
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
