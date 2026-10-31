from pathlib import Path
import os
import sys
from PySide6.QtCore import QProcess, QProcessEnvironment
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QPlainTextEdit, QStyle
from PySide6.QtCore import QSize
from .process import available


def project_root():
    return Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent


class SetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr_ui('MiniDV Capture · Setup'))
        self.resize(640, 450)
        layout = QVBoxLayout(self)
        self.info = QLabel()
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        self.button = QPushButton(self.tr_ui('Install && set up'))
        self.button.setObjectName('primary')
        self.button.setMinimumHeight(54)
        self.button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        self.button.setIconSize(QSize(24, 24))
        self.button.setStyleSheet('QPushButton {font-size:16px; font-weight:600;}')
        self.button.setDefault(True)
        self.button.setToolTip(self.tr_ui('Install missing components and enable FireWire access. Administrator authorization is required.'))
        self.button.clicked.connect(self.install)
        layout.addWidget(self.button)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)
        self.close_button = QPushButton(self.tr_ui('Close'))
        self.close_button.clicked.connect(self.accept)
        layout.addWidget(self.close_button)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(lambda: self.output.appendPlainText(bytes(self.process.readAllStandardOutput()).decode(errors='replace')))
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.failed)
        self.refresh()

    def tr_ui(self, text):
        parent = self.parent()
        return parent.tr(text) if parent and hasattr(parent, 'tr') else text

    def refresh(self):
        components = '\n'.join(f'{name}: {self.tr_ui("ready") if available(name) else self.tr_ui("missing")}' for name in ('dvgrab', 'ffmpeg', 'ffprobe'))
        self.info.setText(components + '\n\n' + self.tr_ui('Setup supports Ubuntu/Debian (APT), Arch/CachyOS (pacman), and Fedora (DNF). You will be asked for administrator authorization. A udev rule enables FireWire access for the active local desktop session. The application itself runs without administrator privileges.'))

    def install(self):
        self.button.setText(self.tr_ui('Installing…'))
        self.button.setEnabled(False)
        self.close_button.setEnabled(False)
        env = QProcessEnvironment.systemEnvironment()
        if getattr(sys, 'frozen', False):
            env.remove('LD_LIBRARY_PATH')
            if os.environ.get('LD_LIBRARY_PATH_ORIG'):
                env.insert('LD_LIBRARY_PATH', os.environ['LD_LIBRARY_PATH_ORIG'])
        self.process.setProcessEnvironment(env)
        args = ['/usr/bin/bash', str(project_root() / 'scripts' / 'setup-system.sh')]
        if all(available(x) for x in ('dvgrab', 'ffmpeg', 'ffprobe')):
            args.append('--access-only')
        self.process.start('pkexec', args)

    def finished(self, code, status):
        self.button.setText(self.tr_ui('Install && set up'))
        self.button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.output.appendPlainText(self.tr_ui('Setup complete. Rescan the camera.') if code == 0 else
                                   self.tr_ui('Setup did not complete. Check the details above and retry.'))
        self.refresh()

    def failed(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.button.setText(self.tr_ui('Install && set up'))
            self.output.appendPlainText(self.tr_ui('Could not start administrator authorization: ') + self.process.errorString())
            self.button.setEnabled(True)
            self.close_button.setEnabled(True)

    def reject(self):
        if self.process.state() == QProcess.ProcessState.NotRunning:
            super().reject()

    def closeEvent(self, event):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            event.ignore()
        else:
            super().closeEvent(event)
