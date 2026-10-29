import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from minidv_capture.devices import Device, discover
from minidv_capture.storage import Store, fingerprint, delete_verified_source
from minidv_capture.capture import CaptureSession, CaptureManager, capture_arguments
from minidv_capture.conversion import (ConversionQueue, FORMATS, verify_metadata,
    video_encoder_candidates, conversion_arguments)

APP = QApplication.instance() or QApplication([])
DEVICE = Device('000085000014cad9', 'Testkamera', '/dev/fw1', '/test/bus', 0, True)


def wait_until(predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        APP.processEvents()
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('QProcess timeout exceeded')


def options(**overrides):
    return {'manual': True, 'rewind': False, 'duration': 0, 'format': 'MP4 / H.264',
            'quality': 'Standard', 'deinterlace': True, 'delete_raw': False, **overrides}


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'state/queue.json')

    def tearDown(self):
        APP.processEvents()
        self.temp.cleanup()

    def job(self, **opts):
        return self.store.create(self.root / 'tapes', 'Tape', DEVICE.to_dict(), options(**opts))


class DiscoveryTests(Base):
    def test_unknown_model_and_multiple_controllers(self):
        root, dev = self.root / 'devices', self.root / 'dev'
        root.mkdir(); dev.mkdir()
        for bus, local, remote, guid in [('a', 'fw0', 'fw1', DEVICE.guid), ('b', 'fw2', 'fw3', '0000000000000002')]:
            parent = self.root / bus
            for name in (local, remote):
                node = parent / name
                node.mkdir(parents=True)
                (root / name).symlink_to(node)
                (dev / name).touch()
            (parent / local / 'is_local').write_text('1')
            (parent / remote / 'guid').write_text('0x' + guid)
            (parent / remote / 'units').write_text('0x00a02d:0x010001')
        devices = discover(root, dev)
        self.assertEqual([d.card for d in devices], [0, 1])
        self.assertEqual(devices[0].name, 'DV camera')
        self.assertEqual(devices[0].guid, DEVICE.guid)

    def test_manual_no_guid_or_avc(self):
        args = capture_arguments(DEVICE, True, self.root, rewind=True)
        self.assertIn('-noavc', args)
        self.assertNotIn('-guid', args)
        self.assertNotIn('-rewind', args)
        self.assertEqual(args[args.index('-size') + 1], '0')

    def test_auto_selects_guid(self):
        args = capture_arguments(DEVICE, False, self.root)
        self.assertIn('0x' + DEVICE.guid, args)
        self.assertNotIn('-noavc', args)

    def test_auto_broadcast_keeps_transport_control_and_rewind(self):
        args = capture_arguments(DEVICE, False, self.root, rewind=True, broadcast=True)
        self.assertNotIn('-guid', args)
        self.assertNotIn('-noavc', args)
        self.assertNotIn('-nostop', args)
        self.assertIn('-rewind', args)
        self.assertEqual(args[args.index('-card') + 1], '0')
        self.assertEqual(args[args.index('-channel') + 1], '63')


class StorageTests(Base):
    def test_old_german_preferences_remain_usable(self):
        job = self.job(format='AVI / DV verlustfrei', quality='Hoch')
        restored = Store(self.store.path).jobs[0]
        self.assertEqual(restored['options']['format'], 'AVI / DV lossless')
        self.assertEqual(restored['options']['quality'], 'High')
        self.assertEqual(restored['raw'], job['raw'])

    def test_unique_numbering(self):
        a, b = self.job(), self.job()
        self.assertEqual(a['name'], 'Tape-001')
        self.assertEqual(b['name'], 'Tape-002')

    def test_restart_keeps_partial(self):
        job = self.job(delete_raw=True)
        Path(job['raw']).write_bytes(b'partial')
        restarted = Store(self.store.path).jobs[0]
        self.assertEqual(restarted['state'], 'interrupted')
        self.assertTrue(restarted['capture_incomplete'])
        self.assertEqual(Path(job['raw']).read_bytes(), b'partial')

    def test_restart_queues_interrupted_conversion_automatically(self):
        job = self.job()
        Path(job['raw']).write_bytes(b'complete DV recording')
        self.store.update(job, state='converting', progress=47, capture_incomplete=False)

        restarted = Store(self.store.path).jobs[0]

        self.assertEqual(restarted['state'], 'queued')
        self.assertEqual(restarted['progress'], 0)
        self.assertEqual(restarted['interrupted_from'], 'converting')
        self.assertFalse(restarted['capture_incomplete'])
        self.assertEqual(Path(job['raw']).read_bytes(), b'complete DV recording')

    def test_finish_resume_merge_appends_segments_and_queues_conversion(self):
        job = self.job()
        raw = Path(job['raw'])
        raw.write_bytes(b'original')
        resumed = Path(job['directory']) / 'capture-resume-test.dv'
        resumed.write_bytes(b'continued')

        self.assertEqual(self.store.finish_resume_merge(job), len(b'originalcontinued'))

        self.assertEqual(raw.read_bytes(), b'originalcontinued')
        self.assertFalse(resumed.exists())
        self.assertEqual(job['state'], 'queued')
        self.assertFalse(job['capture_incomplete'])

    def test_corrupt_queue_not_overwritten(self):
        self.store.path.write_text('{broken')
        with self.assertRaises(RuntimeError):
            Store(self.store.path)
        self.assertEqual(self.store.path.read_text(), '{broken')

    def verified(self):
        job = self.job(delete_raw=True)
        raw = Path(job['raw']); raw.write_bytes(b'raw')
        out = raw.with_suffix('.mp4'); out.write_bytes(b'checked')
        job.update(state='done', verified=True, output=str(out), source_fingerprint=fingerprint(raw), output_fingerprint=fingerprint(out))
        return job

    def test_delete_verified(self):
        job = self.verified()
        self.assertTrue(delete_verified_source(job))
        self.assertFalse(Path(job['raw']).exists())

    def test_no_delete_failed(self):
        job = self.verified(); job['state'] = 'error'
        self.assertFalse(delete_verified_source(job))
        self.assertTrue(Path(job['raw']).exists())

    def test_no_delete_changed(self):
        for field in ('raw', 'output'):
            job = self.verified()
            Path(job[field]).write_bytes(b'changed')
            with self.assertRaises(ValueError):
                delete_verified_source(job)
            self.assertTrue(Path(job['raw']).exists())

    def test_no_delete_symlink(self):
        job = self.verified()
        raw = Path(job['raw']); raw.unlink()
        other = self.root / 'precious'; other.write_bytes(b'precious')
        raw.symlink_to(other)
        with self.assertRaises(ValueError):
            delete_verified_source(job)
        self.assertEqual(other.read_bytes(), b'precious')


class CaptureTests(Base):
    def test_start_selects_broadcast_only_for_single_camera_on_known_controller(self):
        for device, peers, broadcast in (
            (DEVICE, [DEVICE], True),
            (DEVICE, [DEVICE, replace(DEVICE, guid='0000000000000002')], False),
            (replace(DEVICE, card=-1), [replace(DEVICE, card=-1)], False),
        ):
            with self.subTest(device=device, peers=peers):
                s = CaptureSession(self.store, self.job(manual=False), device)
                with patch('minidv_capture.capture.discover', return_value=peers), patch.object(s.process, 'start'):
                    s.start()
                self.assertEqual('-guid' not in s.process.arguments(), broadcast)
                s.timer.stop()
                s.deleteLater()

    def session(self, script):
        job = self.job()
        fake = self.root / 'fake.py'; fake.write_text(script)
        s = CaptureSession(self.store, job, DEVICE)
        self.addCleanup(s.deleteLater)
        with patch('minidv_capture.capture.executable', return_value=sys.executable), patch('minidv_capture.capture.capture_arguments', return_value=[str(fake), job['raw']]):
            s.start()
        s.timer.stop()
        return s

    def running(self, extra=''):
        return self.session('import sys,time,signal\nsignal.signal(signal.SIGINT,lambda *a:sys.exit(0))\nopen(sys.argv[1],"wb").write(b"DV"*72000)\n' + extra + '\ntime.sleep(30)\n')

    def test_stop_queues_and_signals_next_tape(self):
        s = self.running(); done = []; s.completed.connect(done.append)
        wait_until(lambda: Path(s.job['raw']).exists())
        s.stop('complete'); wait_until(lambda: s.finished_once)
        self.assertEqual(s.job['state'], 'queued')
        self.assertEqual(len(done), 1)

    def test_failed_exit_preserves_raw(self):
        s = self.session('import sys\nopen(sys.argv[1],"wb").write(b"partial")\nsys.exit(4)\n')
        done = []; s.completed.connect(done.append)
        wait_until(lambda: s.finished_once)
        self.assertEqual(s.job['state'], 'error')
        self.assertFalse(done)
        self.assertTrue(Path(s.job['raw']).exists())

    def test_disconnect(self):
        s = self.running()
        wait_until(lambda: Path(s.job['raw']).exists())
        with patch('minidv_capture.capture.discover', return_value=[]):
            s.poll()
        wait_until(lambda: s.finished_once)
        self.assertEqual(s.job['state'], 'error')
        self.assertIn('disconnected', s.job['error'])

    def test_missing_program(self):
        s = CaptureSession(self.store, self.job(), DEVICE)
        with patch('minidv_capture.capture.executable', return_value='/missing/dvgrab'):
            s.start()
        wait_until(lambda: s.finished_once)
        self.assertEqual(s.job['state'], 'error')
        s.deleteLater()

    def test_same_bus_locked(self):
        manager = CaptureManager(self.store)
        s = CaptureSession(self.store, self.job(), DEVICE)
        manager.sessions[DEVICE.guid] = s
        with patch('minidv_capture.capture.available', return_value=True), patch('minidv_capture.capture.discover', return_value=[DEVICE]):
            with self.assertRaisesRegex(RuntimeError, 'already'):
                manager.start(DEVICE, self.root, 'second', options())
        s.deleteLater(); manager.deleteLater()

    def test_dropped_frames_fail(self):
        s = self.running('sys.stderr.write("1 frame dropped\\n");sys.stderr.flush()')
        wait_until(lambda: s.damaged)
        s.stop('complete'); wait_until(lambda: s.finished_once)
        self.assertEqual(s.job['state'], 'error')

    def test_damaged_frames_fail(self):
        s = self.running('sys.stderr.write("damaged frame near: timecode 00:00:01.19\\n");sys.stderr.flush()')
        wait_until(lambda: s.damaged)
        s.stop('complete'); wait_until(lambda: s.finished_once)
        self.assertEqual(s.job['state'], 'error')


class ConversionTests(Base):
    @classmethod
    def setUpClass(cls):
        cls.media_dir = tempfile.TemporaryDirectory()
        cls.sample = Path(cls.media_dir.name) / 'sample.dv'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=720x576:rate=25',
            '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-t', '0.6', '-aspect', '4:3',
            '-c:v', 'dvvideo', '-pix_fmt', 'yuv420p', '-threads', '1', '-c:a', 'pcm_s16le', '-ac', '2', '-f', 'dv', str(cls.sample)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.media_dir.cleanup()

    def queue(self):
        queue = ConversionQueue(self.store)
        self.addCleanup(queue.deleteLater)
        return queue

    def enqueue(self, **opts):
        job = self.job(**opts)
        Path(job['raw']).write_bytes(self.sample.read_bytes())
        self.store.update(job, state='queued')
        return job

    def test_hardware_encoder_is_preferred_with_cpu_fallback(self):
        source = {'streams': [{'codec_type': 'video', 'field_order': 'progressive'}]}
        candidates = video_encoder_candidates('MP4 / H.264', {'h264_nvenc'}, source)
        self.assertEqual([c['codec'] for c in candidates], ['h264_nvenc', 'libx264'])
        job = self.job(format='MP4 / H.264')
        gpu_args = conversion_arguments(job, self.root / 'gpu.mp4', source, candidates[0])
        cpu_args = conversion_arguments(job, self.root / 'cpu.mp4', source, candidates[1])
        self.assertIn('h264_nvenc', gpu_args)
        self.assertIn('-cq', gpu_args)
        self.assertIn('libx264', cpu_args)

    def test_vaapi_upload_filter_and_interlaced_cpu_preservation(self):
        progressive = {'streams': [{'codec_type': 'video', 'field_order': 'progressive'}]}
        job = self.job(format='MKV / H.265')
        vaapi = {'backend': 'vaapi', 'codec': 'hevc_vaapi', 'device': '/dev/dri/renderD128'}
        args = conversion_arguments(job, self.root / 'gpu.mkv', progressive, vaapi)
        self.assertIn('/dev/dri/renderD128', args)
        self.assertIn('format=nv12,hwupload', args[args.index('-vf') + 1])

        interlaced = {'streams': [{'codec_type': 'video', 'field_order': 'bb'}]}
        candidates = video_encoder_candidates('MP4 / H.264', {'h264_nvenc'}, interlaced, deinterlace=False)
        self.assertEqual([c['codec'] for c in candidates], ['libx264'])

    def test_failed_hardware_encoder_retries_on_cpu(self):
        job = self.enqueue(format='MP4 / H.264')
        candidates = [
            {'backend': 'nvenc', 'codec': 'missing_test_encoder', 'label': 'Test GPU'},
            {'backend': 'cpu', 'codec': 'libx264', 'label': 'CPU'},
        ]
        messages = []
        queue = self.queue()
        queue.log.connect(messages.append)
        with patch('minidv_capture.conversion.video_encoder_candidates', return_value=candidates):
            queue.pump()
            wait_until(lambda: job['state'] in {'done', 'conversion_error'}, 45)
        self.assertEqual(job['state'], 'done', job['error'])
        self.assertTrue(any('retrying with CPU' in message for message in messages))

    def test_all_formats_real_ffmpeg(self):
        for fmt in FORMATS:
            with self.subTest(format=fmt):
                job = self.enqueue(format=fmt)
                queue = self.queue(); queue.pump()
                wait_until(lambda: job['state'] in {'done', 'conversion_error'}, 45)
                self.assertEqual(job['state'], 'done', job['error'])
                self.assertTrue(job['verified'])
                self.assertTrue(Path(job['raw']).exists())
                self.assertTrue(Path(job['output']).exists())

    def test_interlaced_outputs_without_deinterlacing(self):
        for fmt in ('MP4 / H.264', 'MKV / H.265', 'MOV / ProRes'):
            with self.subTest(format=fmt):
                job = self.enqueue(format=fmt, deinterlace=False)
                queue = self.queue(); queue.pump()
                wait_until(lambda: job['state'] in {'done', 'conversion_error'}, 45)
                self.assertEqual(job['state'], 'done', job['error'])
                probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', job['output']]))
                self.assertIn(probe['streams'][0]['field_order'], ('bb', 'bt'))

    def test_delete_after_verification(self):
        job = self.enqueue(delete_raw=True)
        queue = self.queue(); queue.pump()
        wait_until(lambda: job['state'] in {'done', 'conversion_error'})
        self.assertEqual(job['state'], 'done', job['error'])
        self.assertTrue(job.get('raw_deleted'))
        self.assertFalse(Path(job['raw']).exists())

    def test_bad_media_kept_next_job_runs(self):
        bad = self.job(delete_raw=True)
        Path(bad['raw']).write_bytes(b'not video')
        self.store.update(bad, state='queued')
        good = self.enqueue()
        queue = self.queue(); queue.pump()
        wait_until(lambda: good['state'] in {'done', 'conversion_error'})
        self.assertEqual(bad['state'], 'conversion_error')
        self.assertTrue(Path(bad['raw']).exists())
        self.assertEqual(good['state'], 'done', good['error'])

    def test_metadata_rejects_missing_audio(self):
        probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(self.sample)]))
        changed = json.loads(json.dumps(probe))
        changed['streams'] = [s for s in changed['streams'] if s['codec_type'] != 'audio']
        with self.assertRaises(ValueError):
            verify_metadata(probe, changed)

    def test_recovery_disables_delete(self):
        job = self.enqueue(delete_raw=True)
        self.store.update(job, state='interrupted')
        queue = self.queue(); queue.retry(job)
        self.assertFalse(job['options']['delete_raw'])
        wait_until(lambda: job['state'] in {'done', 'conversion_error'})
        self.assertTrue(Path(job['raw']).exists())


if __name__ == '__main__':
    unittest.main()
