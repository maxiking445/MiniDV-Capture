import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from minidv_capture.transport_recovery import saved_timecode, timecode_seconds, prepare


class CheckpointTests(unittest.TestCase):
    def frame(self, packs=(b'\x13\x20\x40\x09\x00',) * 2):
        frame = bytearray(144000)
        frame[0:4] = b'\x1f\x07\x00\x80'
        frame[80] = 0x3f
        for index, pack in enumerate(packs):
            frame[86 + index * 8:91 + index * 8] = pack
        return frame

    def read(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'capture.dv'
            path.write_bytes(data)
            return saved_timecode(path)

    def test_reads_last_complete_frame_not_partial_tail(self):
        self.assertEqual(self.read(self.frame() + b'partial'), '00:09:40:20')

    def test_disagreeing_packs_are_not_a_seek_target(self):
        with self.assertRaisesRegex(ValueError, 'unambiguous'):
            self.read(self.frame((b'\x13\x20\x40\x09\x00', b'\x13\x20\x41\x09\x00')))

    def test_missing_or_invalid_timecode_refuses_automatic_rewind(self):
        for packs in ((), (b'\x13\xff\xff\xff\xff',) * 2,
                      (b'\x13\x29\x40\x09\x00',) * 2):
            with self.subTest(packs=packs), self.assertRaises(ValueError):
                self.read(self.frame(packs))

    def test_camera_timecode_validation(self):
        self.assertEqual(timecode_seconds('01:02:03:24'), 3723)
        for value in ('', '00:60:00:00', '24:00:00:00', '00:00:00:99'):
            with self.assertRaises(ValueError):
                timecode_seconds(value)


class PositioningTests(unittest.TestCase):
    def test_stops_then_rewinds_to_before_saved_scene_and_stops_again(self):
        camera = Mock()
        camera.timecode.side_effect = ['00:10:00:00', '00:09:10:00', '00:08:20:00', '00:07:30:00', '00:06:40:00', '00:06:39:00']
        with patch('minidv_capture.transport_recovery.time.sleep'):
            result = prepare(camera, '00:09:40:20')
        self.assertEqual(result, '00:06:39:00')
        self.assertEqual(camera.stop.call_count, 2)
        self.assertEqual(camera.mock_calls[0][0], 'stop')
        camera.avc.avc1394_vcr_rewind.assert_called_once()

    def test_unconfirmed_stop_never_rewinds(self):
        camera = Mock()
        camera.stop.side_effect = RuntimeError('STOP not confirmed')
        with self.assertRaisesRegex(RuntimeError, 'STOP not confirmed'):
            prepare(camera, '00:09:40:20')
        camera.avc.avc1394_vcr_rewind.assert_not_called()

    def test_missing_timecode_does_not_start_blind_rewind(self):
        camera = Mock()
        camera.timecode.side_effect = RuntimeError('timecode unavailable')
        with self.assertRaisesRegex(RuntimeError, 'timecode unavailable'):
            prepare(camera, '00:09:40:20')
        camera.stop.assert_called_once()
        camera.avc.avc1394_vcr_rewind.assert_not_called()

    def test_timecode_loss_during_rewind_still_requests_stop(self):
        camera = Mock()
        camera.timecode.side_effect = ['00:15:00:00', RuntimeError('timecode lost')]
        with patch('minidv_capture.transport_recovery.time.sleep'), self.assertRaises(RuntimeError):
            prepare(camera, '00:09:40:20')
        self.assertEqual(camera.stop.call_count, 2)

    def test_earlier_camera_timecode_is_not_assumed_to_be_verified_overlap(self):
        camera = Mock()
        camera.timecode.return_value = '00:01:00:00'
        with self.assertRaisesRegex(RuntimeError, 'ambiguous'):
            prepare(camera, '00:09:40:20')
        camera.avc.avc1394_vcr_rewind.assert_not_called()
