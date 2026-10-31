"""Bounded, read-only live preview of the growing raw DV file."""
from pathlib import Path
import time

from PySide6.QtCore import QProcess, QTimer, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QSizePolicy

from .process import executable


class LivePreview(QWidget):
    WIDTH, HEIGHT = 480, 270

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.picture = QLabel(self.tr_ui('Preview starts with capture'))
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setMinimumSize(240, 135)
        self.picture.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.picture.setStyleSheet('background: #090c10; color: #aab5c4;')
        layout.addWidget(self.picture, 1)
        self.status = QLabel(self.tr_ui('Live preview · muted · up to 5 fps'))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.session = None
        self.decoder = None
        self.buffer = bytearray()
        self.pixmap = QPixmap()
        self.offset = -1
        self.last_frame = 0
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.poll)

    def tr_ui(self, text):
        parent = self.parent()
        return parent.tr(text) if parent and hasattr(parent, 'tr') else text

    def set_session(self, session):
        if session is self.session:
            return
        self.stop()
        self.session = session
        self.picture.setText(self.tr_ui('Waiting for DV video …') if session else self.tr_ui('No active capture selected'))
        self.status.setText(self.tr_ui('Live preview · muted · up to 5 fps'))
        if session:
            self.timer.start()

    def start_decoder(self):
        process = QProcess(self)
        self.decoder = process
        process.setProgram(executable('ffmpeg'))
        process.setArguments([
            '-v', 'error', '-threads', '1', '-probesize', '32', '-analyzeduration', '1',
            '-f', 'dv', '-i', 'pipe:0', '-an', '-sn', '-threads', '1', '-filter_threads', '1',
            '-vf', 'scale=trunc(270*dar/2)*2:270,setsar=1,pad=480:270:(ow-iw)/2:(oh-ih)/2',
            '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-flush_packets', '1', 'pipe:1',
        ])
        process.readyReadStandardOutput.connect(self.read_image)
        process.readyReadStandardError.connect(lambda: process.readAllStandardError())
        process.errorOccurred.connect(lambda _: self.decoder_failed(process))
        process.finished.connect(lambda *_: self.decoder_failed(process))
        process.start()

    def decoder_failed(self, process):
        if self.decoder is process:
            self.timer.stop()
            self.status.setText(self.tr_ui('Preview unavailable. Capture continues independently.'))

    def poll(self):
        if not self.session or not self.session.active or self.session.reason:
            self.set_session(None)
            return
        try:
            path = Path(self.session.job['raw'])
            if not path.exists():
                return
            with path.open('rb') as source:
                header = source.read(4)
                if len(header) < 4:
                    return
                # DV DIF header: DSF selects PAL (12 sequences) or NTSC (10).
                frame_size = 144000 if header[3] & 0x80 else 120000
                count = path.stat().st_size // frame_size
                if not count:
                    return
                offset = (count - 1) * frame_size
                if offset == self.offset:
                    if self.last_frame and time.monotonic() - self.last_frame > 2:
                        self.status.setText(self.tr_ui('No new DV video · showing last frame'))
                    return
                if self.decoder is None:
                    self.start_decoder()
                if self.decoder.state() != QProcess.ProcessState.Running:
                    return
                # Never let a slow preview queue up captured video in memory.
                if self.decoder.bytesToWrite() > frame_size * 2:
                    return
                source.seek(offset)
                frame = source.read(frame_size)
                if len(frame) != frame_size:
                    return
            self.decoder.write(frame)
            self.offset = offset
        except OSError:
            self.status.setText(self.tr_ui('Waiting for readable DV data …'))

    def read_image(self):
        self.buffer.extend(bytes(self.decoder.readAllStandardOutput()))
        size = self.WIDTH * self.HEIGHT * 3
        count = len(self.buffer) // size
        if not count:
            return
        pixels = bytes(self.buffer[(count - 1) * size:count * size])
        del self.buffer[:count * size]
        image = QImage(pixels, self.WIDTH, self.HEIGHT, self.WIDTH * 3, QImage.Format.Format_RGB888).copy()
        self.pixmap = QPixmap.fromImage(image)
        self.last_frame = time.monotonic()
        self.status.setText(self.tr_ui('Live preview · muted · up to 5 fps'))
        self.show_image()

    def show_image(self):
        if not self.pixmap.isNull():
            self.picture.setPixmap(self.pixmap.scaled(self.picture.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                     Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.show_image()

    def stop(self):
        self.timer.stop()
        process, self.decoder = self.decoder, None
        if process:
            process.blockSignals(True)
            process.kill()
            process.waitForFinished(1000)
            process.deleteLater()
        self.session = None
        self.buffer.clear()
        self.pixmap = QPixmap()
        self.picture.clear()
        self.offset = -1
        self.last_frame = 0
