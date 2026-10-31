from pathlib import Path
import json
import re
import time
from PySide6.QtCore import Qt, QSettings, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QLineEdit, QFileDialog, QCheckBox, QSpinBox, QGroupBox,
    QFormLayout, QPlainTextEdit, QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar,
    QMessageBox, QSystemTrayIcon, QSplitter, QAbstractItemView, QMenu, QStyle)
from .devices import discover
from .capture import CaptureManager
from .conversion import ConversionQueue, FORMATS, QUALITIES
from .process import available
from .preview import LivePreview
from .preferences import english_options
from .tape_change import TapeChangeWatcher
from . import __version__
from .setup import SetupDialog, project_root
from .translations import LANGUAGES

STATES = {'capturing': 'Capturing', 'queued': 'Queued', 'converting': 'Converting',
          'verifying': 'Verifying output', 'done': 'Done', 'error': 'Capture error',
          'cancelled': 'Cancelled', 'interrupted': 'Interrupted', 'conversion_error': 'Conversion error'}
MIN_CAPTURE_BYTES_FOR_TAPE_ADVANCE = 1_100_000_000  # About five minutes of DV video.



class MainWindow(QMainWindow):
    quit_requested = Signal()

    def __init__(self, store):
        super().__init__()
        self.store = store
        self.settings = QSettings('MiniDVCapture', 'MiniDVCapture')
        self.captures = CaptureManager(store, self)
        self.queue = ConversionQueue(store, self)
        self.devices = []
        self.dialogs = []
        self.tape_watchers = {}
        self.retry_capture = None
        self.shutting_down = False
        try:
            self.device_options = json.loads(self.settings.value('device_options', '{}'))
            if not isinstance(self.device_options, dict):
                self.device_options = {}
            self.device_options = {key: english_options(value) for key, value in self.device_options.items()
                                   if isinstance(value, dict)}
        except (TypeError, ValueError):
            self.device_options = {}
        self.previous_guid = ''
        self.language = self.settings.value('language', 'en')
        if self.language not in LANGUAGES:
            self.language = 'en'
        self.setWindowTitle('MiniDV Capture')
        self.setWindowIcon(QIcon(str(project_root() / 'assets/minidv-capture.svg')))
        self.resize(1160, 830)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 18, 24, 18)
        top = QHBoxLayout()
        title = QLabel('MiniDV Capture')
        title.setObjectName('title')
        top.addWidget(title)
        top.addStretch()
        setup = QPushButton('Setup')
        setup.clicked.connect(self.setup)
        top.addWidget(setup)
        self.language_combo = QComboBox()
        for code, language in LANGUAGES.items():
            self.language_combo.addItem(f"{language['flag']}  {language['name']}", code)
        self.language_combo.setCurrentIndex(self.language_combo.findData(self.language))
        self.language_combo.setToolTip('Sprache / Language')
        self.language_combo.currentIndexChanged.connect(self.change_language)
        top.addWidget(self.language_combo)
        layout.addLayout(top)
        self.dependencies = QLabel()
        self.dependencies.setWordWrap(True)
        layout.addWidget(self.dependencies)
        device_box = QGroupBox('1 · Camera')
        device_layout = QVBoxLayout(device_box)
        row = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(420)
        self.device_combo.currentIndexChanged.connect(self.device_changed)
        row.addWidget(self.device_combo, 1)
        self.rescan_button = QPushButton('↻  Rescan cameras')
        self.rescan_button.setToolTip('Rescan FireWire devices and access permissions, including after a disconnect.')
        self.rescan_button.clicked.connect(self.rescan_devices)
        row.addWidget(self.rescan_button)
        device_layout.addLayout(row)
        self.device_info = QLabel()
        self.device_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        device_layout.addWidget(self.device_info)
        self.scan_result = QLabel()
        self.scan_result.setWordWrap(True)
        device_layout.addWidget(self.scan_result)
        layout.addWidget(device_box)
        settings_row = QHBoxLayout()
        capture_box = QGroupBox('2 · Capture')
        form = QFormLayout(capture_box)
        self.folder = QLineEdit(self.settings.value('folder', str(Path.home() / 'Videos' / 'MiniDV')))
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder)
        browse = QPushButton('Browse …')
        browse.clicked.connect(self.browse)
        folder_row.addWidget(browse)
        form.addRow('Output folder', folder_row)
        self.label = QLineEdit(self.settings.value('label', self.tr('Tape')))
        if self.label.text() == 'Tape' and self.language == 'de':
            self.label.setText(self.tr('Tape'))
        form.addRow('Tape name', self.label)
        self.auto_tape_name = QCheckBox('Automatically increment tape name for the next tape')
        self.auto_tape_name.setChecked(self.settings.value('auto_tape_name', True, type=bool))
        self.auto_tape_name.setToolTip('When enabled, Tape8-001 is followed by Tape9-001. When disabled, captures keep the same tape name and folder numbering continues, for example Tape8-002.')
        form.addRow(self.auto_tape_name)
        self.mode = QComboBox()
        self.mode.addItems(['Manual · PLAY on camera', 'Automatic · AV/C'])
        self.mode.currentIndexChanged.connect(self.mode_changed)
        form.addRow('Transport', self.mode)
        self.rewind = QCheckBox('Rewind automatically before capture')
        self.rewind.setEnabled(False)
        form.addRow(self.rewind)
        self.duration = QSpinBox()
        self.duration.setRange(0, 240)
        self.duration.setSuffix(' min')
        self.duration.setSpecialValueText('No time limit')
        form.addRow('Optional time limit', self.duration)
        self.mode_hint = QLabel('Select PLAYER/VCR mode. Start capture here, then press PLAY on the camera.')
        self.mode_hint.setWordWrap(True)
        form.addRow(self.mode_hint)
        self.auto_next = QCheckBox('Start next capture automatically after changing the tape')
        self.auto_next.setToolTip('Uses AV/C cassette detection and automatic playback. Falls back to Start next tape if unsupported.')
        self.auto_next.toggled.connect(self.auto_next_changed)
        form.addRow(self.auto_next)
        settings_row.addWidget(capture_box, 1)
        convert_box = QGroupBox('3 · Background conversion')
        convert_form = QFormLayout(convert_box)
        self.format = QComboBox()
        self.format.addItems(FORMATS)
        self.format.setCurrentText(english_options({'format': self.settings.value('format', 'MP4 / H.264')})['format'])
        self.format.currentTextChanged.connect(self.format_changed)
        convert_form.addRow('Format', self.format)
        self.quality = QComboBox()
        self.quality.addItems(QUALITIES)
        self.quality.setCurrentText(english_options({'quality': self.settings.value('quality', 'Standard')})['quality'])
        convert_form.addRow('Quality', self.quality)
        self.deinterlace = QCheckBox('Deinterlace · smooth 50p/59.94p')
        self.deinterlace.setChecked(self.settings.value('deinterlace', True, type=bool))
        convert_form.addRow(self.deinterlace)
        self.delete_raw = QCheckBox('Delete original DV after successful verification')
        # Deliberately do not restore destructive permission across launches.
        self.delete_raw.setChecked(False)
        self.delete_raw.setToolTip('Only after duration, audio, video and full decoding checks. Originals are kept if any check fails.')
        convert_form.addRow(self.delete_raw)
        note = QLabel('Raw footage is kept by default. AVI/DV remuxes without quality loss.\n'
                      'You can capture the next tape while conversion runs.')
        note.setWordWrap(True)
        convert_form.addRow(note)
        settings_row.addWidget(convert_box, 1)
        layout.addLayout(settings_row)
        self.format_changed()
        buttons = QHBoxLayout()
        self.start_button = QPushButton('Start capture')
        self.start_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.start_button.setObjectName('primary')
        self.start_button.clicked.connect(self.start_capture)
        self.stop_button = QPushButton('Stop && convert')
        self.stop_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        self.stop_button.setToolTip('Finish capture, convert the footage and offer to start the next tape.')
        self.stop_button.clicked.connect(lambda: self.stop_capture(False))
        self.cancel_button = QPushButton('Cancel capture')
        self.cancel_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton))
        self.cancel_button.setToolTip('Stop capture and keep the raw file without converting it.')
        self.cancel_button.clicked.connect(lambda: self.stop_capture(True))
        buttons.addStretch()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch()
        self.live = QLabel('Ready')
        layout.addWidget(self.live)
        split = QSplitter(Qt.Orientation.Vertical)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['Tape', 'Camera', 'Status', 'Progress', 'Details'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.job_context_menu)
        self.table.itemSelectionChanged.connect(self.show_job_log)
        split.addWidget(self.table)
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMaximumBlockCount(1500)
        split.addWidget(self.logs)
        split.setSizes([240, 100])
        monitor_row = QSplitter(Qt.Orientation.Horizontal)
        preview_box = QGroupBox('Live preview')
        preview_layout = QVBoxLayout(preview_box)
        self.preview = LivePreview(self)
        preview_layout.addWidget(self.preview)
        monitor_row.addWidget(preview_box)
        monitor_row.addWidget(split)
        monitor_row.setSizes([480, 620])
        layout.addWidget(monitor_row, 1)
        bottom = QHBoxLayout()
        bottom.addStretch()
        self.pause_button = QPushButton('Pause queue')
        self.pause_button.clicked.connect(self.toggle_queue)
        bottom.addWidget(self.pause_button)
        retry = QPushButton('Retry selected conversion')
        retry.clicked.connect(self.retry)
        bottom.addWidget(retry)
        open_folder = QPushButton('Open folder')
        open_folder.clicked.connect(self.open_folder)
        bottom.addWidget(open_folder)
        self.clear_history_button = QPushButton('Clear history')
        self.clear_history_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        self.clear_history_button.setToolTip('Remove finished and failed jobs from the list. Keep video files and active or queued jobs.')
        self.clear_history_button.clicked.connect(self.clear_history)
        bottom.addWidget(self.clear_history_button)
        self.version_label = QLabel(f'Version {__version__}')
        self.version_label.setToolTip('MiniDV Capture application version')
        bottom.insertWidget(0, self.version_label)
        bottom.insertStretch(1, 1)
        layout.addLayout(bottom)
        layout.addLayout(buttons)
        feedback = QHBoxLayout()
        self.capture_feedback = QLabel()
        self.capture_feedback.setWordWrap(True)
        feedback.addWidget(self.capture_feedback, 1)
        self.check_devices_button = QPushButton('Check devices')
        self.check_devices_button.clicked.connect(self.rescan_devices)
        feedback.addWidget(self.check_devices_button)
        self.retry_capture_button = QPushButton('Retry capture')
        self.retry_capture_button.clicked.connect(self.retry_capture_start)
        feedback.addWidget(self.retry_capture_button)
        layout.addLayout(feedback)
        self.capture_feedback.hide()
        self.check_devices_button.hide()
        self.retry_capture_button.hide()
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip('MiniDV Capture')
        self.tray_menu = QMenu(self)
        self.tray_menu.addAction('Open', self.show_window)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction('Quit', self.close)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.tray_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.captures.changed.connect(self.refresh)
        self.captures.log.connect(self.append_log)
        self.captures.completed.connect(self.tape_complete)
        self.captures.failed.connect(self.capture_failed)
        self.queue.changed.connect(self.refresh)
        self.queue.log.connect(self.append_log)
        self.queue.done.connect(lambda j: self.notify('Conversion complete', j['name']))
        self.scan_timer = QTimer(self)
        self.scan_timer.setInterval(2500)
        self.scan_timer.timeout.connect(self.scan)
        self.scan_timer.start()
        self.scan()
        self.refresh()
        if store.warning:
            self.append_log(store.warning)
        geometry = self.settings.value('geometry')
        if geometry:
            self.restoreGeometry(geometry)
        self.retranslate_ui()

    def tr(self, text):
        return LANGUAGES.get(self.language, LANGUAGES['en'])['strings'].get(text, text)

    def change_language(self, _index):
        previous_default = self.tr('Tape')
        self.language = self.language_combo.currentData()
        self.settings.setValue('language', self.language)
        if self.label.text() == previous_default:
            self.label.setText(self.tr('Tape'))
        self.retranslate_ui()

    def retranslate_ui(self):
        # Translate static controls in place; combo data and saved job values stay canonical.
        for kind in (QLabel, QPushButton, QGroupBox, QCheckBox):
            for widget in self.findChildren(kind):
                source = widget.property('source_text')
                if source is None:
                    source = widget.title() if isinstance(widget, QGroupBox) else widget.text()
                    widget.setProperty('source_text', source)
                if isinstance(widget, QGroupBox):
                    widget.setTitle(self.tr(source))
                else:
                    widget.setText(self.tr(source))
        self.mode.setItemText(0, self.tr('Manual · PLAY on camera'))
        self.mode.setItemText(1, self.tr('Automatic · AV/C'))
        self.auto_tape_name.setToolTip(self.tr('When enabled, Tape8-001 is followed by Tape9-001. When disabled, captures keep the same tape name and folder numbering continues, for example Tape8-002.'))
        self.table.setHorizontalHeaderLabels([self.tr(x) for x in ('Tape', 'Camera', 'Status', 'Progress', 'Details')])
        self.refresh()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_window()

    def append_log(self, text):
        if text:
            self.logs.appendPlainText(text)

    def selected_device(self):
        guid = self.device_combo.currentData()
        return next((d for d in self.devices if d.guid == guid), None)

    def scan(self):
        devices = discover()
        if devices != self.devices:
            old = self.device_combo.currentData() or self.previous_guid or self.settings.value('guid', '')
            self.devices = devices
            self.device_combo.blockSignals(True)
            self.device_combo.clear()
            for d in devices:
                self.device_combo.addItem(f'{d.name} · {d.guid} · {d.node}', d.guid)
            index = self.device_combo.findData(old)
            self.device_combo.setCurrentIndex(max(0, index))
            self.device_combo.blockSignals(False)
            self.device_changed()
        self.refresh()

    def rescan_devices(self):
        self.scan()
        stamp = time.strftime('%H:%M:%S')
        if self.devices:
            accessible = sum(d.accessible for d in self.devices)
            message = f'{len(self.devices)} camera(s) found; {accessible} accessible.'
            if not accessible:
                message += ' Open Setup to enable FireWire access.'
        else:
            message = ('No camera found on the FireWire bus. Check PLAYER/VCR mode and connection; '
                       'if needed, power-cycle the camera and scan again.')
        self.scan_result.setText(f'Scan at {stamp}: {message}')
        self.statusBar().showMessage(message, 15000)
        self.append_log(f'Camera scan {stamp}: {message}')

    def options(self):
        return {'manual': self.mode.currentIndex() == 0, 'rewind': self.rewind.isChecked() and self.mode.currentIndex() == 1,
                'auto_next': self.auto_next.isChecked(),
                'duration': self.duration.value(), 'format': self.format.currentText(),
                'quality': self.quality.currentText(), 'deinterlace': self.deinterlace.isChecked(),
                'delete_raw': self.delete_raw.isChecked(), 'signal_timeout': 60}

    def device_changed(self):
        if self.previous_guid:
            self.device_options[self.previous_guid] = self.options()
        d = self.selected_device()
        if d:
            self.previous_guid = d.guid
            options = self.device_options.get(d.guid, {})
            self.auto_next.blockSignals(True)
            self.mode.setCurrentIndex(0 if options.get('manual', True) else 1)
            self.rewind.setChecked(options.get('rewind', False))
            self.duration.setValue(options.get('duration', 0))
            self.auto_next.setChecked(options.get('auto_next', False))
            if self.auto_next.isChecked():
                self.mode.setCurrentIndex(1)
            self.auto_next.blockSignals(False)
        self.refresh()

    def mode_changed(self):
        manual = self.mode.currentIndex() == 0
        if manual and hasattr(self, 'auto_next'):
            self.auto_next.setChecked(False)
        self.rewind.setEnabled(not manual)
        self.mode_hint.setText(self.tr('Select PLAYER/VCR mode. Start capture here, then press PLAY on the camera.') if manual else
                              self.tr('Select PLAYER/VCR mode on the camera. The app starts playback automatically.'))

    def auto_next_changed(self, checked):
        if checked:
            self.mode.setCurrentIndex(1)
        else:
            device = self.selected_device()
            if device:
                self.stop_tape_watcher(device.guid)

    def stop_tape_watcher(self, guid):
        watcher = self.tape_watchers.pop(guid, None)
        if watcher:
            watcher.stop()
            watcher.message.emit('Automatic start is off. Use Start next tape to continue.')
            watcher.deleteLater()

    def format_changed(self, *_):
        enabled = self.format.currentText() != 'AVI / DV lossless'
        self.quality.setEnabled(enabled)
        self.deinterlace.setEnabled(enabled)

    def browse(self):
        directory = QFileDialog.getExistingDirectory(self, 'Output folder', self.folder.text())
        if directory:
            self.folder.setText(directory)

    def start_capture(self, _checked=False, device=None, options_override=None):
        device = device or self.selected_device()
        if not device:
            self.error('No FireWire camera found. Check PLAYER/VCR mode, power and cable.')
            return
        if not all(available(x) for x in ('dvgrab', 'ffmpeg', 'ffprobe')):
            self.setup()
            return
        try:
            options = options_override if options_override is not None else (self.options() if device.guid == self.device_combo.currentData() else self.device_options.get(device.guid, self.options()))
            active_on_bus = any(s.active and s.device.bus == device.bus for s in self.captures.sessions.values())
            if self.auto_tape_name.isChecked() and not active_on_bus:
                matching = [j for j in self.store.jobs
                            if re.fullmatch(re.escape(self.label.text()) + r'-\d{3,}', j.get('name', ''))
                            and self.has_capture_data(j)]
                if matching:
                    latest = max(matching, key=lambda j: j.get('created', 0))
                    incremented = self.next_tape_label(latest)
                    if incremented:
                        self.label.setText(incremented)
            for guid, watcher in list(self.tape_watchers.items()):
                # Cancel pending auto-starts before taking control of this bus.
                peer = next((d for d in self.devices if d.guid == guid), None)
                if guid == device.guid or (peer and peer.bus == device.bus):
                    self.stop_tape_watcher(guid)
            self.captures.start(device, Path(self.folder.text()), self.label.text(), options)
            self.retry_capture = (device, dict(options))
            self.capture_feedback.setText(self.tr('Capture request accepted. Waiting for dvgrab to start…'))
            self.capture_feedback.show()
            self.check_devices_button.hide()
            self.retry_capture_button.hide()
            self.save_settings()
        except (OSError, ValueError, RuntimeError) as exc:
            self.error(str(exc))

    def stop_capture(self, cancelled):
        d = self.selected_device()
        session = self.captures.sessions.get(d.guid) if d else None
        if not session or not session.active:
            return
        session.stop('cancel' if cancelled else 'complete')
        self.refresh()

    def retry_capture_start(self):
        if not self.retry_capture:
            return
        device, options = self.retry_capture
        self.rescan_devices()
        fresh = next((d for d in self.devices if d.guid == device.guid), None)
        if not fresh:
            self.capture_feedback.setText(self.tr('Camera not found. Check power, PLAYER/VCR mode and FireWire cable, then check devices and retry.'))
            return
        self.capture_feedback.hide()
        self.start_capture(device=fresh, options_override=options)

    def refresh(self):
        missing = [x for x in ('dvgrab', 'ffmpeg', 'ffprobe') if not available(x)]
        self.dependencies.setText(self.tr('Missing components: ') + ', '.join(missing) + self.tr(' · Install missing components in Setup.') if missing else
                                  self.tr('All components ready'))
        d = self.selected_device()
        self.device_info.setText(f'GUID {d.guid}  ·  {d.node}  ·  Controller {d.card}  ·  '
            + (self.tr('Device access ready') if d.accessible else self.tr('Access denied – open Setup')) if d else
            self.tr('No camera connected. Select PLAYER/VCR mode and connect via FireWire.'))
        session = self.captures.sessions.get(d.guid) if d else None
        active = bool(session and session.active)
        self.preview.set_session(session if active and not session.reason else None)
        self.start_button.setEnabled(bool(d) and not active)
        self.stop_button.setEnabled(active and not session.reason)
        self.cancel_button.setEnabled(active and not session.reason)
        if active:
            seconds = int(time.monotonic() - session.started)
            suffix = (' · ' + self.tr('dvgrab started; waiting for PLAY') if session.job['options']['manual'] and session.process_started_ok else
                      ' · ' + self.tr('Starting dvgrab…') if not session.process_started_ok else
                      ' · ' + self.tr('Waiting for DV data (may be rewinding)')
                      if session.job['options'].get('rewind') else ' · ' + self.tr('Waiting for DV data'))
            if session.bytes:
                suffix = ' · ' + self.tr('Capturing · DV data arriving')
            self.live.setText(f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02} · '
                              f'{session.bytes / 1e9:.2f} GB · {session.rate / 1e6:.1f} MB/s{suffix}')
            if session.bytes:
                self.capture_feedback.setText(self.tr('DV data is arriving and the recording file is growing.'))
                self.capture_feedback.show()
                self.check_devices_button.hide()
                self.retry_capture_button.hide()
            elif session.process_started_ok:
                self.capture_feedback.setText(self.tr('dvgrab is running. No DV data has arrived yet. In Manual mode, press PLAY on the camera; otherwise check camera mode and connection.'))
                self.capture_feedback.show()
                self.check_devices_button.show()
                self.retry_capture_button.hide()
            else:
                self.capture_feedback.setText(self.tr('Starting dvgrab…'))
                self.capture_feedback.show()
                self.check_devices_button.hide()
                self.retry_capture_button.hide()
        else:
            self.live.setText(self.tr(f'{len(self.captures.active())} capture(s) active') if self.captures.active() else self.tr('Ready'))
        selected = self.selected_job()
        selected_id = selected['id'] if selected else None
        self.table.blockSignals(True)
        jobs = list(reversed(self.store.jobs))
        self.table.setRowCount(len(jobs))
        for row, j in enumerate(jobs):
            progress, progress_label, detail = self.job_progress(j)
            values = [j['name'], j['device']['name'] + ' · ' + j['device']['guid'][-6:],
                      self.tr(STATES.get(j['state'], j['state'])), '', detail]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, j['id'])
                self.table.setItem(row, col, item)
            self.table.setRowHeight(row, 58)
            bar = self.table.cellWidget(row, 3)
            if not isinstance(bar, QProgressBar):
                bar = QProgressBar()
                bar.setMinimumWidth(150)
                self.table.setCellWidget(row, 3, bar)
            bar.setRange(0, 100)
            bar.setValue(progress)
            bar.setFormat(progress_label + ' %p%')
            bar.setToolTip(self.tr('Capture estimate based on 90 minutes. This does not detect the end of the tape.')
                           if j['state'] == 'capturing' else self.tr('Conversion includes output verification.'))
            if j['id'] == selected_id:
                self.table.selectRow(row)
        self.table.blockSignals(False)
        self.pause_button.setText(self.tr('Resume queue' if self.queue.paused else 'Pause queue'))

    def job_progress(self, job):
        state = job['state']
        if state == 'capturing':
            session = next((s for s in self.captures.sessions.values() if s.job['id'] == job['id']), None)
            if session:
                elapsed = max(0, time.monotonic() - session.first_data) if session.first_data is not None else 0
                percent = min(99, int(elapsed / (90 * 60) * 100))
                if session.reason:
                    detail = self.tr('Stopping capture…')
                elif session.bytes:
                    detail = (f'{self.tr("Capturing")} · {session.rate / 1e6:.1f} MB/s\n{session.bytes / 1e9:.2f} GB · '
                              f'{int(elapsed)//60:02}:{int(elapsed)%60:02} / 90:00 (est.)')
                else:
                    detail = self.tr('Waiting for PLAY') if session.manual else self.tr('Waiting for DV data / rewinding')
                return percent, 'Capture ≈', detail
            return 0, 'Capture ≈', 'Waiting for DV data'
        detail = {
            'queued': 'Waiting for conversion', 'converting': 'Converting video',
            'verifying': 'Verifying video and audio', 'done': 'Complete · output verified',
            'cancelled': 'Cancelled · raw footage kept', 'interrupted': 'Interrupted · raw footage kept',
        }.get(state, 'Stopped')
        detail = self.tr(detail)
        if self.queue.job is job:
            detail = {'probe-source': 'Inspecting source video',
                      'probe-result': 'Checking output metadata', 'decode-check': 'Verifying video and audio'
                      }.get(self.queue.phase, detail)
            if self.queue.phase == 'encode':
                detail = f'Converting video · {self.queue.active_encoder}' if self.queue.active_encoder else 'Converting video'
        value = 0 if state == 'queued' else min(100, max(0, job.get('progress', 0)))
        return value, 'Conversion' if state in {'queued', 'converting', 'verifying', 'done', 'conversion_error'} else 'Stopped', job.get('error') or detail

    def selected_job(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return next((j for j in self.store.jobs if item and j['id'] == item.data(Qt.ItemDataRole.UserRole)), None)

    def job_context_menu(self, position):
        index = self.table.indexAt(position)
        if not index.isValid():
            return
        self.table.selectRow(index.row())
        job = self.selected_job()
        if not job:
            return
        menu = QMenu(self)
        retry = menu.addAction('Retry conversion')
        retry_states = {'error', 'cancelled', 'interrupted', 'conversion_error'}
        raw = Path(job['raw'])
        retry.setEnabled(job['state'] in retry_states and raw.is_file() and raw.stat().st_size > 0)
        retry.triggered.connect(lambda _checked=False, target=job: self.retry_job(target))
        resume = menu.addAction('Resume capture')
        resume.setEnabled(job.get('capture_incomplete', False)
                          and job['state'] in {'error', 'cancelled', 'interrupted'})
        resume.triggered.connect(lambda _checked=False, target=job: self.resume_capture(target))
        menu.addSeparator()
        remove = menu.addAction('Remove')
        remove.setToolTip('Remove this entry from history; keep all video and log files.')
        remove.setEnabled(job['state'] not in {'capturing', 'queued', 'converting', 'verifying'})
        remove.triggered.connect(lambda _checked=False, target=job: self.remove_history_job(target))
        menu.exec(self.table.viewport().mapToGlobal(position))

    def retry_job(self, job):
        try:
            self.queue.retry(job)
        except (OSError, ValueError) as exc:
            self.error(str(exc))

    def resume_capture(self, job):
        dialog = QMessageBox(QMessageBox.Icon.Question, 'Resume capture',
            'Put the camera at the point where the capture stopped. The app cannot seek to the exact stop position. '
            'Capture will start without rewinding; press PLAY on the camera when the app is waiting. '
            'The new DV segment will be appended to the existing tape capture when you stop it.',
            QMessageBox.StandardButton.NoButton, self)
        start = dialog.addButton('Start capture', QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.exec()
        if dialog.clickedButton() != start:
            return
        try:
            self.captures.resume(job)
        except (OSError, RuntimeError, ValueError) as exc:
            self.error(str(exc))

    def remove_history_job(self, job):
        try:
            removed = self.store.remove(job)
        except (OSError, ValueError) as exc:
            self.error(str(exc))
            return
        if removed:
            if self.selected_job() is None:
                self.logs.clear()
            self.refresh()
            self.statusBar().showMessage('Removed from history. Video and log files were kept.', 10000)

    def show_job_log(self):
        job = self.selected_job()
        if not job:
            return
        self.logs.clear()
        self.append_log(job.get('error', ''))
        for name in ('capture.log', 'conversion.log'):
            path = Path(job['directory']) / name
            if path.is_file():
                try:
                    with path.open('rb') as f:
                        f.seek(max(0, path.stat().st_size - 16000))
                        self.append_log(name + '\n' + f.read().decode(errors='replace'))
                except OSError as exc:
                    self.append_log(str(exc))

    def tape_complete(self, job):
        self.queue.pump()
        self.notify('Tape complete', job['name'] + ' – insert the next tape')
        dialog = QMessageBox(self)
        dialog.setWindowTitle('Tape complete')
        dialog.setText(f'{job["name"]}: Tape complete – insert the next tape.\n'
                       'Conversion continues independently in the background.')
        next_button = dialog.addButton('Start next tape', QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton('Close', QMessageBox.ButtonRole.RejectRole)
        dialog.setInformativeText('This closes the tape series. Conversions continue in the background.')
        guid = job['device']['guid']
        self.stop_tape_watcher(guid)
        handled = False
        def cleanup():
            self.stop_tape_watcher(guid)
            if dialog in self.dialogs:
                self.dialogs.remove(dialog)
            dialog.deleteLater()
        def chosen(button):
            nonlocal handled
            if handled:
                return
            handled = True
            self.stop_tape_watcher(guid)
            if button == next_button:
                device = next((d for d in discover() if d.guid == job['device']['guid']), None)
                if device:
                    next_label = self.next_tape_label(job) if self.auto_tape_name.isChecked() else ''
                    if next_label:
                        self.label.setText(next_label)
                    if job['options'].get('auto_next'):
                        preferences = self.options() if self.selected_device() and self.selected_device().guid == guid else self.device_options.get(guid, job['options'])
                        self.start_capture(device=device, options_override=dict(job['options'], manual=False,
                                           auto_next=preferences.get('auto_next', False)))
                    else:
                        self.start_capture(device=device)
                else:
                    self.error('Camera disconnected.')
            cleanup()
        dialog.buttonClicked.connect(chosen)
        dialog.finished.connect(lambda _: cleanup())
        self.dialogs.append(dialog)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.show()
        if job['options'].get('auto_next'):
            watcher = TapeChangeWatcher(guid, dialog)
            self.tape_watchers[guid] = watcher
            watcher.message.connect(dialog.setInformativeText)
            watcher.ready.connect(next_button.click)
            watcher.start()

    def next_tape_label(self, previous_job):
        """Increment a numbered tape label after that tape has actual capture data."""
        if not self.has_capture_data(previous_job):
            return ''

        # Store names look like Tape8-001; remove only the per-folder sequence.
        base = re.sub(r'-\d{3,}$', '', previous_job.get('name', ''))
        match = re.fullmatch(r'(.*?)(\d+)', base)
        if not match:
            return ''
        prefix, number = match.groups()
        return f'{prefix}{int(number) + 1:0{len(number)}d}'

    @staticmethod
    def has_capture_data(job):
        raw = Path(job.get('raw', ''))
        size = job.get('bytes', 0) or 0
        try:
            if raw.is_file():
                size = max(size, raw.stat().st_size)
        except OSError:
            pass
        return size >= MIN_CAPTURE_BYTES_FOR_TAPE_ADVANCE

    def capture_failed(self, job):
        self.notify('Capture stopped', job['error'])
        self.append_log(job['name'] + ': ' + job['error'])
        if 'No DV data received' in job.get('error', ''):
            device = next((d for d in self.devices if d.guid == job['device']['guid']), None)
            if device:
                self.retry_capture = (device, dict(job['options']))
            self.capture_feedback.setText('No DV data arrived. Check camera power, PLAYER/VCR mode and FireWire cable. Run a device check, then retry the capture.')
            self.capture_feedback.show()
            self.check_devices_button.show()
            self.retry_capture_button.setVisible(device is not None)
        self.error(job['error'])

    def notify(self, title, text):
        if self.tray.isVisible():
            self.tray.showMessage(title, text, QSystemTrayIcon.MessageIcon.Information, 8000)
        self.statusBar().showMessage(title + ': ' + text, 15000)

    def toggle_queue(self):
        self.queue.paused = not self.queue.paused
        self.queue.pump()
        self.refresh()
        if self.queue.paused:
            self.statusBar().showMessage('The current conversion will finish; queued jobs will wait.')

    def retry(self):
        job = self.selected_job()
        if not job:
            return
        self.retry_job(job)

    def open_folder(self):
        job = self.selected_job()
        path = job['directory'] if job else self.folder.text()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).expanduser())))

    def clear_history(self):
        try:
            count = self.store.clear_history()
        except OSError as exc:
            self.error(str(exc))
            return
        self.logs.clear()
        self.refresh()
        self.statusBar().showMessage(f'Cleared {count} history entries. Video files and pending jobs were kept.', 10000)

    def setup(self):
        if self.captures.active() or self.queue.job:
            self.error('Wait for active captures and conversions to finish before running setup.')
            return
        SetupDialog(self).exec()
        self.scan()
        self.queue.pump()

    def error(self, text):
        QMessageBox.warning(self, 'MiniDV Capture', text)

    def save_settings(self):
        if self.previous_guid:
            self.device_options[self.previous_guid] = self.options()
        for key, value in {'folder': self.folder.text(), 'label': self.label.text(),
                           'auto_tape_name': self.auto_tape_name.isChecked(), 'format': self.format.currentText(),
                           'quality': self.quality.currentText(), 'deinterlace': self.deinterlace.isChecked(),
                           'guid': self.device_combo.currentData() or '', 'geometry': self.saveGeometry(),
                           'device_options': json.dumps(self.device_options)}.items():
            self.settings.setValue(key, value)
        self.settings.sync()

    def closeEvent(self, event):
        if self.shutting_down:
            event.ignore()
            return
        if self.captures.active() or self.queue.job:
            reply = QMessageBox.question(self, 'Tasks running',
                'Cancel active tasks and quit? Partial files will be kept; '
                'queued jobs will resume next time.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            event.ignore()
            if reply == QMessageBox.StandardButton.Yes:
                self.shutting_down = True
                for guid in list(self.tape_watchers):
                    self.stop_tape_watcher(guid)
                self.queue.cancel()
                for session in self.captures.active():
                    session.stop('cancel')
                self.shutdown_timer = QTimer(self)
                self.shutdown_timer.setInterval(100)
                self.shutdown_timer.timeout.connect(self.finish_shutdown)
                self.shutdown_timer.start()
                self.setEnabled(False)
            return
        self.save_settings()
        for guid in list(self.tape_watchers):
            self.stop_tape_watcher(guid)
        self.preview.stop()
        self.scan_timer.stop()
        self.tray.hide()
        event.accept()
        self.quit_requested.emit()

    def finish_shutdown(self):
        if not self.captures.active() and not self.queue.job:
            self.shutdown_timer.stop()
            self.shutting_down = False
            self.setEnabled(True)
            self.close()


def apply_theme(app):
    # Native widget behaviour, explicit dark palette independent of KDE theme.
    from PySide6.QtGui import QPalette, QColor
    palette = QPalette()
    for role, color in [(QPalette.ColorRole.Window, '#171d27'), (QPalette.ColorRole.WindowText, '#e8edf5'),
                        (QPalette.ColorRole.Base, '#101620'), (QPalette.ColorRole.AlternateBase, '#202936'),
                        (QPalette.ColorRole.Text, '#e8edf5'), (QPalette.ColorRole.Button, '#263345'),
                        (QPalette.ColorRole.ButtonText, '#e8edf5'), (QPalette.ColorRole.Highlight, '#397dd1'),
                        (QPalette.ColorRole.HighlightedText, '#ffffff'), (QPalette.ColorRole.ToolTipBase, '#263345'),
                        (QPalette.ColorRole.ToolTipText, '#ffffff')]:
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor('#87909e'))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor('#87909e'))
    app.setPalette(palette)
    app.setStyleSheet('QLabel#title {font-size:26px;font-weight:700;} '
        'QGroupBox {font-weight:600;border:1px solid #354155;border-radius:8px;margin-top:12px;padding:16px 10px 8px;} '
        'QGroupBox::title {subcontrol-origin:margin;left:12px;padding:0 5px;} '
        'QPushButton {padding:8px 12px;border-radius:5px;} QPushButton#primary {background:#246bc1;color:white;font-weight:600;} '
        'QPushButton#primary:disabled {background:#273647;color:#87909e;} '
        'QLineEdit,QComboBox,QSpinBox {padding:5px;} QTableWidget {gridline-color:#303b4b;}')
