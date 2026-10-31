import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
import unittest
from dataclasses import replace
from PySide6.QtCore import Qt, QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox, QSystemTrayIcon
from minidv_capture.gui import MainWindow
from minidv_capture.storage import Store
from minidv_capture.capture import CaptureSession
from test_core import APP, DEVICE, options


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(self.root / 'config'))
        self.store = Store(self.root / 'queue.json')
        settings = QSettings(str(self.root / 'settings.ini'), QSettings.Format.IniFormat)
        with patch('minidv_capture.gui.discover', return_value=[DEVICE]), patch('minidv_capture.gui.QSettings', return_value=settings):
            self.window = MainWindow(self.store)
        self.window.scan_timer.stop()
        self.window.queue.paused = True
        self.window.show()
        APP.processEvents()

    def tearDown(self):
        for dialog in list(self.window.dialogs):
            dialog.close()
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()
        self.temp.cleanup()

    def test_default_manual_and_no_delete(self):
        self.assertTrue(self.window.options()['manual'])
        self.assertFalse(self.window.options()['delete_raw'])
        self.assertIn(DEVICE.guid, self.window.device_info.text())
        self.assertFalse(self.window.auto_next.isChecked())

    def test_wizard_allows_direct_navigation_and_preserves_settings(self):
        self.assertEqual(self.window.pages.currentIndex(), 0)
        self.assertFalse(self.window.start_button.isVisible())
        QTest.mouseClick(self.window.step_buttons[1], Qt.MouseButton.LeftButton)
        self.window.label.setText('Holiday')
        QTest.mouseClick(self.window.next_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.pages.currentIndex(), 2)
        QTest.mouseClick(self.window.step_buttons[3], Qt.MouseButton.LeftButton)
        self.assertTrue(self.window.start_button.isVisible())
        self.assertFalse(self.window.folder.isVisible())
        self.assertFalse(self.window.capture_details.isVisible())
        self.assertTrue(self.window.live_lamp.isVisible())
        self.assertFalse(self.window.live_blink_timer.isActive())
        QTest.mouseClick(self.window.details_button, Qt.MouseButton.LeftButton)
        self.assertTrue(self.window.table.isVisible())
        QTest.mouseClick(self.window.step_buttons[1], Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.label.text(), 'Holiday')
        QTest.mouseClick(self.window.back_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.pages.currentIndex(), 0)

    def test_german_language_translates_tape_name_and_default_value(self):
        self.window.language_combo.setCurrentIndex(self.window.language_combo.findData('de'))
        self.assertEqual(self.window.label.text(), 'Kassette')
        self.assertIn('Kassettenname', [label.text() for label in self.window.findChildren(type(self.window.device_info))])

    def test_auto_next_tape_after_confirmed_change_and_close_disarms(self):
        self.window.auto_next.setChecked(True)
        self.assertFalse(self.window.options()['manual'])
        job = self.store.create(self.root / 'tapes', 'Tape', DEVICE.to_dict(), self.window.options())
        self.store.update(job, state='queued')
        with patch('minidv_capture.tape_change.TapeChangeWatcher.poll'):
            self.window.tape_complete(job)
        watcher = self.window.tape_watchers[DEVICE.guid]
        with patch('minidv_capture.gui.discover', return_value=[DEVICE]), patch.object(self.window, 'start_capture') as start:
            watcher.observe('present')
            start.assert_not_called()
            watcher.observe('absent')
            watcher.observe('present')
            watcher.observe('present')
            start.assert_called_once_with(device=DEVICE, options_override=dict(job['options'], manual=False))
        self.assertFalse(self.window.tape_watchers)
        self.assertFalse(self.window.dialogs)
        with patch('minidv_capture.tape_change.TapeChangeWatcher.poll'):
            self.window.tape_complete(job)
        self.window.dialogs[0].close()
        self.assertFalse(self.window.tape_watchers)

    def test_auto_tape_name_advances_when_history_has_capture_data(self):
        self.window.auto_tape_name.setChecked(True)
        self.window.label.setText('Kassette8')
        job = self.store.create(self.root / 'tapes', 'Kassette8', DEVICE.to_dict(), options())
        with Path(job['raw']).open('wb') as raw:
            raw.truncate(1_200_000_000)
        with patch('minidv_capture.gui.available', return_value=True), patch.object(self.window.captures, 'start') as start:
            self.window.start_capture(device=DEVICE)
        self.assertEqual(self.window.label.text(), 'Kassette9')
        self.assertEqual(start.call_args.args[2], 'Kassette9')

    def test_auto_tape_name_can_be_disabled_to_continue_folder_sequence(self):
        self.window.auto_tape_name.setChecked(False)
        self.window.label.setText('Kassette8')
        job = self.store.create(self.root / 'tapes', 'Kassette8', DEVICE.to_dict(), options())
        Path(job['raw']).write_bytes(b'DV data')
        with patch('minidv_capture.gui.available', return_value=True), patch.object(self.window.captures, 'start') as start:
            self.window.start_capture(device=DEVICE)
        self.assertEqual(self.window.label.text(), 'Kassette8')
        self.assertEqual(start.call_args.args[2], 'Kassette8')

    def test_empty_history_entry_does_not_advance_auto_tape_name(self):
        self.window.auto_tape_name.setChecked(True)
        self.window.label.setText('Kassette8')
        self.store.create(self.root / 'tapes', 'Kassette8', DEVICE.to_dict(), options())
        with patch('minidv_capture.gui.available', return_value=True), patch.object(self.window.captures, 'start') as start:
            self.window.start_capture(device=DEVICE)
        self.assertEqual(self.window.label.text(), 'Kassette8')
        self.assertEqual(start.call_args.args[2], 'Kassette8')

    def test_short_capture_is_treated_as_recapture_not_new_tape(self):
        self.window.auto_tape_name.setChecked(True)
        self.window.label.setText('Kassette8')
        job = self.store.create(self.root / 'tapes', 'Kassette8', DEVICE.to_dict(), options())
        Path(job['raw']).write_bytes(b'DV data from a short capture')
        self.store.update(job, state='done', bytes=500_000_000)
        with patch('minidv_capture.gui.available', return_value=True), patch.object(self.window.captures, 'start') as start:
            self.window.start_capture(device=DEVICE)
        self.assertEqual(self.window.label.text(), 'Kassette8')
        self.assertEqual(start.call_args.args[2], 'Kassette8')

    def test_clear_history_preserves_videos_and_pending_jobs(self):
        completed = self.store.create(self.root / 'tapes', 'Finished', DEVICE.to_dict(), options())
        raw = Path(completed['raw'])
        raw.write_bytes(b'original')
        self.store.update(completed, state='done')
        pending = self.store.create(self.root / 'tapes', 'Next', DEVICE.to_dict(), options())
        self.store.update(pending, state='queued')
        QTest.mouseClick(self.window.clear_history_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.store.jobs, [pending])
        self.assertEqual(raw.read_bytes(), b'original')
        self.assertTrue((raw.parent / 'job.json').exists())
        self.assertEqual(Store(self.store.path).jobs, [pending])
        self.assertEqual(self.window.table.rowCount(), 1)

    def test_capture_progress_switches_to_conversion_before_90_minutes(self):
        job = self.store.create(self.root / 'tapes', 'Tape', DEVICE.to_dict(), options())
        session = CaptureSession(self.store, job, DEVICE, self.window.captures)
        self.window.captures.sessions[DEVICE.guid] = session
        try:
            # Waiting for PLAY must not count towards capture progress.
            session.started = time.monotonic() - 600
            self.window.refresh()
            self.assertEqual(self.window.table.cellWidget(0, 3).value(), 0)
            session.first_data = time.monotonic() - 60 * 60
            session.bytes = 10_000_000_000
            session.rate = 3_500_000
            self.window.refresh()
            bar = self.window.table.cellWidget(0, 3)
            self.assertEqual(bar.value(), 66)
            self.assertIn('Capture', bar.format())
            self.assertIn('3.5 MB/s', self.window.table.item(0, 4).text())
            self.assertIn('10.00 GB', self.window.table.item(0, 4).text())
            session.first_data = time.monotonic() - 91 * 60
            self.window.refresh()
            self.assertEqual(bar.value(), 99)
            session.finished_once = True
            job.update(state='queued', progress=0)
            self.window.refresh()
            self.assertEqual(bar.value(), 0)
            self.assertIn('Conversion', bar.format())
            job.update(state='converting', progress=42)
            self.window.refresh()
            self.assertEqual(bar.value(), 42)
            self.assertIn('Converting video', self.window.table.item(0, 4).text())
            job.update(state='verifying', progress=90)
            self.window.refresh()
            self.assertIn('Verifying', self.window.table.item(0, 4).text())
            job.update(state='done', progress=100)
            self.window.refresh()
            self.assertEqual(bar.value(), 100)
        finally:
            session.finished_once = True

    def test_tray_exit_requests_application_quit_when_hidden(self):
        self.window.hide()
        quit_requests = []
        self.window.quit_requested.connect(lambda: quit_requests.append(True))
        action = next(a for a in self.window.tray.contextMenu().actions() if a.text() == 'Quit')
        action.trigger()
        self.assertEqual(quit_requests, [True])
        self.assertFalse(self.window.tray.isVisible())

    def test_tray_right_click_does_not_open_window(self):
        self.window.hide()
        self.window.tray.activated.emit(QSystemTrayIcon.ActivationReason.Context)
        self.assertFalse(self.window.isVisible())
        self.window.tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
        self.assertTrue(self.window.isVisible())

    def test_tray_exit_waits_for_capture_and_can_be_declined(self):
        job = self.store.create(self.root / 'tapes', 'Tape', DEVICE.to_dict(), options())
        session = CaptureSession(self.store, job, DEVICE, self.window.captures)
        self.window.captures.sessions[DEVICE.guid] = session
        quit_requests = []
        self.window.quit_requested.connect(lambda: quit_requests.append(True))
        action = next(a for a in self.window.tray.contextMenu().actions() if a.text() == 'Quit')
        try:
            with patch('minidv_capture.gui.QMessageBox.question', return_value=QMessageBox.StandardButton.No):
                action.trigger()
            self.assertFalse(quit_requests)
            self.assertFalse(session.reason)
            with patch('minidv_capture.gui.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
                action.trigger()
            self.assertEqual(session.reason, 'cancel')
            self.window.finish_shutdown()
            self.assertFalse(quit_requests)
            session.finished_once = True
            self.window.finish_shutdown()
            self.assertEqual(quit_requests, [True])
        finally:
            session.finished_once = True
            self.window.shutting_down = False

    def test_auto_waits_for_data_then_shows_capture(self):
        job = self.store.create(self.root / 'tapes', 'Tape', DEVICE.to_dict(), options(manual=False))
        session = CaptureSession(self.store, job, DEVICE, self.window.captures)
        self.window.captures.sessions[DEVICE.guid] = session
        try:
            session.process_started_ok = True
            self.window.refresh()
            self.assertIn('Waiting for DV data', self.window.live.text())
            self.assertFalse(self.window.live_blink_timer.isActive())
            self.assertIs(self.window.preview.session, session)
            self.assertNotIn('Waiting for PLAY', self.window.live.text())
            Path(job['raw']).write_bytes(b'DV' * 72000)
            with patch('minidv_capture.capture.discover', return_value=[DEVICE]):
                session.poll()
            self.window.refresh()
            self.assertIn('Capturing', self.window.live.text())
            self.assertGreater(session.rate, 0)
            self.assertTrue(self.window.live_blink_timer.isActive())
            QTest.mouseClick(self.window.step_buttons[2], Qt.MouseButton.LeftButton)
            self.assertTrue(session.active)
            self.assertTrue(self.window.live_blink_timer.isActive())
        finally:
            session.finished_once = True

        self.window.refresh()
        self.assertIsNone(self.window.preview.session)
        self.assertFalse(self.window.live_blink_timer.isActive())

    def test_tape_dialog_starts_next_without_waiting_for_queue(self):
        job = self.store.create(self.root / 'tapes', 'Tape', DEVICE.to_dict(), options())
        self.store.update(job, state='queued')
        self.window.tape_complete(job)
        self.assertEqual(len(self.window.dialogs), 1)
        dialog = self.window.dialogs[0]
        button = next(b for b in dialog.buttons() if b.text() == 'Start next tape')
        with patch('minidv_capture.gui.discover', return_value=[DEVICE]), patch.object(self.window, 'start_capture') as start:
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            APP.processEvents()
            start.assert_called_once_with(device=DEVICE)
        self.assertEqual(job['state'], 'queued')

    def test_avi_disables_lossy_options(self):
        self.window.format.setCurrentText('AVI / DV lossless')
        self.assertFalse(self.window.deinterlace.isEnabled())
        self.assertFalse(self.window.quality.isEnabled())

    def test_rescan_recovers_camera_after_disconnect_with_new_node(self):
        with patch('minidv_capture.gui.discover', return_value=[]):
            QTest.mouseClick(self.window.rescan_button, Qt.MouseButton.LeftButton)
        self.assertIsNone(self.window.selected_device())
        self.assertIn('No camera', self.window.scan_result.text())
        reconnected = replace(DEVICE, node='/dev/fw3')
        other = replace(DEVICE, guid='0000000000000001', node='/dev/fw2')
        with patch('minidv_capture.gui.discover', return_value=[other, reconnected]):
            QTest.mouseClick(self.window.rescan_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.selected_device(), reconnected)
        self.assertIn('/dev/fw3', self.window.device_info.text())
        self.assertIn('2 camera(s) found', self.window.scan_result.text())
        self.assertTrue(self.window.start_button.isEnabled())
