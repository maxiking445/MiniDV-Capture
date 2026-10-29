import subprocess
import time
from types import SimpleNamespace

from PySide6.QtCore import QProcess

from minidv_capture.preview import LivePreview
from test_core import APP, Base, wait_until


class PreviewTests(Base):
    def test_growing_pal_and_ntsc_files_decode_without_changing_source(self):
        for height, rate, pixel_format, frame_size in (
            (576, '25', 'yuv420p', 144000),
            (480, '30000/1001', 'yuv411p', 120000),
        ):
            with self.subTest(height=height):
                sample = self.root / f'sample-{height}.dv'
                subprocess.run([
                    'ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f'color=red:size=720x{height}:rate={rate}',
                    '-frames:v', '15', '-aspect', '4:3', '-c:v', 'dvvideo', '-pix_fmt', pixel_format,
                    '-threads', '1', '-f', 'dv', str(sample),
                ], check=True)
                data = sample.read_bytes()
                raw = self.root / f'growing-{height}.dv'
                raw.touch()
                preview = LivePreview()
                session = SimpleNamespace(active=True, reason='', job={'raw': str(raw)})
                try:
                    preview.set_session(session)
                    preview.poll()
                    self.assertIsNone(preview.decoder)
                    # Feed new complete frames, leaving an incomplete tail on disk.
                    for count in range(1, 16):
                        raw.write_bytes(data[:count * frame_size] + b'partial')
                        preview.poll()
                        deadline = time.monotonic() + .06
                        while time.monotonic() < deadline:
                            APP.processEvents()
                            time.sleep(.005)
                        preview.poll()
                    wait_until(lambda: not preview.pixmap.isNull(), timeout=5)
                    color = preview.pixmap.toImage().pixelColor(240, 135)
                    self.assertGreater(color.red(), 200)
                    self.assertLess(color.green(), 40)
                    self.assertEqual(raw.read_bytes(), data + b'partial')
                    process = preview.decoder
                    session.active = False
                    preview.poll()
                    self.assertIsNone(preview.decoder)
                    self.assertEqual(process.state(), QProcess.ProcessState.NotRunning)
                    self.assertFalse(preview.timer.isActive())
                finally:
                    preview.stop()
                    preview.deleteLater()

    def test_switching_sessions_clears_old_picture_and_position(self):
        preview = LivePreview()
        try:
            first = SimpleNamespace(active=True, reason='', job={'raw': str(self.root / 'first.dv')})
            second = SimpleNamespace(active=True, reason='', job={'raw': str(self.root / 'second.dv')})
            preview.set_session(first)
            preview.offset = 1234
            preview.set_session(second)
            self.assertIs(preview.session, second)
            self.assertEqual(preview.offset, -1)
            self.assertTrue(preview.pixmap.isNull())
            preview.set_session(None)
            self.assertFalse(preview.timer.isActive())
        finally:
            preview.stop()
            preview.deleteLater()
