from pathlib import Path
from fractions import Fraction
import json
import os
import subprocess
import time
import uuid
from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from .process import executable, available, interrupt
from .storage import Store, fingerprint, delete_verified_source
from .preferences import english_options

FORMATS = {'MP4 / H.264': '.mp4', 'MKV / H.265': '.mkv', 'MOV / ProRes': '.mov', 'AVI / DV lossless': '.avi'}
QUALITIES = ['High', 'Standard', 'Compact']


def duration(probe):
    value = probe.get('format', {}).get('duration')
    if value is None:
        value = max((float(s.get('duration', 0)) for s in probe.get('streams', []) if s.get('duration') not in (None, 'N/A')), default=0)
    return float(value)


def video(probe):
    return next((s for s in probe.get('streams', []) if s.get('codec_type') == 'video'), None)


def field_order(probe):
    stream = video(probe) or {}
    declared = stream.get('field_order', 'unknown')
    if declared != 'unknown':
        return declared
    frame = next((f for f in probe.get('frames', []) if f.get('media_type') == 'video'), {})
    if frame:
        if not frame.get('interlaced_frame'):
            return 'progressive'
        return 'tt' if frame.get('top_field_first') else 'bb'
    return 'bb' if stream.get('codec_name') == 'dvvideo' else 'unknown'


def ratio(stream):
    sar = stream.get('sample_aspect_ratio', '1:1')
    if sar in ('N/A', '0:1', None):
        sar = '1:1'
    return Fraction(stream['width'], stream['height']) * Fraction(sar.replace(':', '/'))


def verify_metadata(source, result):
    sv, ov = video(source), video(result)
    if not sv or not ov or duration(source) <= 0 or duration(result) <= 0:
        raise ValueError('No valid video output')
    tolerance = max(0.25, duration(source) * 0.001)
    if abs(duration(source) - duration(result)) > tolerance:
        raise ValueError('Output duration does not match the source')
    if (sv['width'], sv['height']) != (ov['width'], ov['height']) or abs(float(ratio(sv) - ratio(ov))) > 0.01:
        raise ValueError('Resolution or aspect ratio changed')
    sa = [s for s in source['streams'] if s['codec_type'] == 'audio']
    oa = [s for s in result['streams'] if s['codec_type'] == 'audio']
    if len(sa) != len(oa) or any(a.get('channels') != b.get('channels') or a.get('sample_rate') != b.get('sample_rate') for a, b in zip(sa, oa)):
        raise ValueError('Audio streams, channels or sample rate missing/changed')


def available_video_encoders():
    """Return FFmpeg's compiled video encoder names without requiring a GPU."""
    try:
        result = subprocess.run([executable('ffmpeg'), '-hide_banner', '-encoders'],
            capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return set()
    names = set()
    for line in (result.stdout + result.stderr).splitlines():
        columns = line.split()
        if len(columns) >= 2 and columns[0].startswith('V'):
            names.add(columns[1])
    return names


def video_encoder_candidates(fmt, encoders, source_probe, deinterlace=True):
    """Prefer hardware video encoders, then always provide the CPU encoder."""
    if fmt == 'MP4 / H.264':
        codec, software = 'h264', 'libx264'
    elif fmt == 'MKV / H.265':
        codec, software = 'hevc', 'libx265'
    else:
        label = 'DV stream copy' if fmt == 'AVI / DV lossless' else 'CPU'
        return [{'backend': 'cpu', 'codec': None, 'label': label}]

    # Preserve interlaced output when deinterlacing is disabled; the CPU
    # encoders below support the existing field-order configuration.
    if not deinterlace and field_order(source_probe) in {'bb', 'bt', 'tt', 'tb'}:
        return [{'backend': 'cpu', 'codec': software, 'label': 'CPU'}]

    candidates = []
    nvenc = f'{codec}_nvenc'
    if nvenc in encoders:
        candidates.append({'backend': 'nvenc', 'codec': nvenc, 'label': 'NVIDIA NVENC'})
    vaapi = f'{codec}_vaapi'
    if vaapi in encoders:
        for device in sorted(Path('/dev/dri').glob('renderD*')):
            candidates.append({'backend': 'vaapi', 'codec': vaapi, 'device': str(device),
                               'label': f'VAAPI ({device.name})'})
    candidates.append({'backend': 'cpu', 'codec': software, 'label': 'CPU'})
    return candidates


def conversion_arguments(job, destination: Path, source_probe, encoder=None):
    options = english_options(job['options'])
    fmt = options['format']
    quality = options.get('quality', 'Standard')
    crf = {'High': '17', 'Standard': '20', 'Compact': '24'}[quality]
    encoder = encoder or {'backend': 'cpu', 'codec': None}
    backend = encoder['backend']
    args = ['-hide_banner', '-nostdin', '-n', '-xerror', '-threads', '2']
    if backend == 'vaapi':
        args += ['-vaapi_device', encoder['device']]
    args += ['-i', job['raw'],
            '-map', '0:v:0', '-map', '0:a?', '-map_metadata', '0']
    deinterlace = options.get('deinterlace', True) and fmt != 'AVI / DV lossless'
    filters = []
    if deinterlace:
        filters.append('bwdif=mode=send_field:parity=auto:deint=all')
    if fmt == 'MP4 / H.264':
        if backend == 'nvenc':
            quality = {'High': '17', 'Standard': '20', 'Compact': '24'}[quality]
            args += ['-c:v', encoder['codec'], '-preset', 'p4', '-rc', 'vbr', '-cq', quality, '-b:v', '0', '-pix_fmt', 'yuv420p']
        elif backend == 'vaapi':
            args += ['-c:v', encoder['codec'], '-qp', crf]
        else:
            args += ['-c:v', 'libx264', '-preset', 'fast', '-crf', crf, '-pix_fmt', 'yuv420p']
        args += ['-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart']
    elif fmt == 'MKV / H.265':
        if backend == 'nvenc':
            quality = {'High': '17', 'Standard': '20', 'Compact': '24'}[quality]
            args += ['-c:v', encoder['codec'], '-preset', 'p4', '-rc', 'vbr', '-cq', quality, '-b:v', '0']
        elif backend == 'vaapi':
            args += ['-c:v', encoder['codec'], '-qp', crf]
        else:
            args += ['-c:v', 'libx265', '-preset', 'fast', '-crf', crf, '-x265-params', 'pools=2:frame-threads=1']
        args += ['-c:a', 'flac']
    elif fmt == 'MOV / ProRes':
        profile = {'High': '3', 'Standard': '2', 'Compact': '1'}[quality]
        args += ['-c:v', 'prores_ks', '-profile:v', profile, '-pix_fmt', 'yuv422p10le', '-c:a', 'pcm_s16le']
    elif fmt == 'AVI / DV lossless':
        args += ['-c', 'copy']
    else:
        raise ValueError('Unknown output format')
    if not deinterlace and fmt != 'AVI / DV lossless':
        field = field_order(source_probe)
        if field in {'bb', 'bt', 'tt', 'tb'}:
            args += ['-flags', '+ilme+ildct', '-field_order', 'bb' if field in {'bb', 'bt'} else 'tt']
            filters.append('setfield=bff' if field in {'bb', 'bt'} else 'setfield=tff')
            if backend == 'cpu' and fmt == 'MP4 / H.264':
                args += ['-x264-params', 'bff=1' if field in {'bb', 'bt'} else 'tff=1']
            if backend == 'cpu' and fmt == 'MKV / H.265':
                i = args.index('-x265-params') + 1
                args[i] += ':interlace=' + ('bff' if field in {'bb', 'bt'} else 'tff')
    if backend == 'vaapi':
        filters += ['format=nv12', 'hwupload']
    if filters:
        args += ['-vf', ','.join(filters), '-filter_threads', '1']
    args += ['-threads', '2', '-progress', 'pipe:1', '-nostats', str(destination)]
    return args


class ConversionQueue(QObject):
    changed = Signal()
    log = Signal(str)
    done = Signal(dict)

    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self.store = store
        self.process = None
        self.job = None
        self.phase = ''
        self.active_encoder = ''
        self.encoder_candidates = [None]
        self.encoder_index = 0
        self.paused = False
        self.stopping = False
        self.buffer = bytearray()
        self.stderr_tail = ''
        self.last_output = time.monotonic()
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.watchdog)
        self.timer.start()
        QTimer.singleShot(0, self.pump)

    def pump(self):
        if self.job or self.paused or not all(available(x) for x in ('ffmpeg', 'ffprobe')):
            return
        job = next((j for j in self.store.jobs if j['state'] == 'queued'), None)
        if not job:
            return
        self.job = job
        self.stopping = False
        try:
            raw = Path(job['raw'])
            if raw.is_symlink() or not raw.is_file() or raw.stat().st_size == 0:
                raise ValueError('Raw file is missing or empty')
            self.store.update(job, state='converting', source_fingerprint=fingerprint(raw), progress=0, verified=False)
            suffix = FORMATS[job['options']['format']]
            self.destination = Path(job['directory']) / (job['name'] + suffix)
            if self.destination.exists():
                self.destination = self.destination.with_name(job['name'] + '-' + uuid.uuid4().hex[:8] + suffix)
            self.partial = self.destination.with_name(self.destination.stem + '.partial' + suffix)
            if self.partial.exists():
                self.partial = self.destination.with_name(self.destination.stem + '.' + uuid.uuid4().hex[:8] + '.partial' + suffix)
            self.run('probe-source', 'ffprobe', ['-v', 'error', '-read_intervals', '%+#1', '-show_frames', '-show_format', '-show_streams', '-of', 'json', str(raw)])
        except (OSError, ValueError, KeyError) as exc:
            self.fail(str(exc))

    def run(self, phase, program, args):
        self.phase = phase
        self.buffer.clear()
        self.stderr_tail = ''
        self.last_output = time.monotonic()
        if self.process:
            self.process.deleteLater()
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.read_stdout)
        self.process.readyReadStandardError.connect(self.read_stderr)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.log.emit(f'{phase}: {program} ' + ' '.join(args))
        self.process.start(executable(program), args)
        self.changed.emit()

    def read_stdout(self):
        if not self.process:
            return
        data = bytes(self.process.readAllStandardOutput())
        self.last_output = time.monotonic()
        self.buffer.extend(data)
        if self.phase in {'encode', 'decode-check'}:
            while b'\n' in self.buffer:
                line, _, rest = self.buffer.partition(b'\n')
                self.buffer = bytearray(rest)
                if line.startswith(b'out_time_us='):
                    try:
                        seconds = int(line.split(b'=')[1]) / 1e6
                        base, span = (0, 85) if self.phase == 'encode' else (85, 14)
                        self.job['progress'] = min(99, base + int(span * seconds / duration(self.source_probe)))
                        self.changed.emit()
                    except (ValueError, ZeroDivisionError):
                        pass

    def read_stderr(self):
        if not self.process:
            return
        text = bytes(self.process.readAllStandardError()).decode(errors='replace')
        self.last_output = time.monotonic()
        self.stderr_tail = (self.stderr_tail + text)[-6000:]
        if text and self.job:
            try:
                with (Path(self.job['directory']) / 'conversion.log').open('a') as f:
                    f.write(text)
            except OSError:
                self.stopping = True
                interrupt(self.process)
            self.log.emit(text.strip())

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.fail(self.process.errorString())

    def watchdog(self):
        if self.job and self.process and time.monotonic() - self.last_output > (60 if self.phase.startswith('probe') else 600):
            self.stderr_tail += '\nProcess stalled; timeout exceeded.'
            self.stopping = True
            interrupt(self.process)

    def finished(self, code, status):
        if not self.job:
            return
        self.read_stdout()
        self.read_stderr()
        if self.stopping or code != 0 or status != QProcess.ExitStatus.NormalExit:
            if self.phase == 'encode' and not self.stopping and self.encoder_index + 1 < len(self.encoder_candidates):
                failed_encoder = self.encoder_candidates[self.encoder_index]
                self.encoder_index += 1
                next_encoder = self.encoder_candidates[self.encoder_index]
                self.active_encoder = next_encoder['label']
                try:
                    self.partial.unlink(missing_ok=True)
                except OSError as exc:
                    self.fail(f'Could not remove failed partial output before encoder fallback: {exc}')
                    return
                self.log.emit(f'{failed_encoder["label"]} encoding failed; retrying with {next_encoder["label"]}.')
                self.run('encode', 'ffmpeg', conversion_arguments(
                    self.job, self.partial, self.source_probe, next_encoder))
                return
            self.fail('Conversion interrupted/failed. Original kept.\n' + self.stderr_tail)
            return
        try:
            if self.phase == 'probe-source':
                self.source_probe = json.loads(bytes(self.buffer))
                if not video(self.source_probe) or duration(self.source_probe) <= 0:
                    raise ValueError('Raw capture contains no valid video')
                fmt = english_options(self.job['options'])['format']
                deinterlace = self.job['options'].get('deinterlace', True)
                self.encoder_candidates = video_encoder_candidates(fmt, available_video_encoders(),
                    self.source_probe, deinterlace)
                self.encoder_index = 0
                encoder = self.encoder_candidates[self.encoder_index]
                self.active_encoder = encoder['label']
                self.log.emit(f'Video encoder selected: {encoder["label"]}.')
                self.run('encode', 'ffmpeg', conversion_arguments(
                    self.job, self.partial, self.source_probe, encoder))
            elif self.phase == 'encode':
                self.store.update(self.job, state='verifying')
                self.run('probe-result', 'ffprobe', ['-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(self.partial)])
            elif self.phase == 'probe-result':
                verify_metadata(self.source_probe, json.loads(bytes(self.buffer)))
                # Decode every frame and every audio stream, not just a header check.
                self.run('decode-check', 'ffmpeg', ['-hide_banner', '-nostdin', '-v', 'error', '-xerror', '-err_detect', 'explode',
                    '-threads', '2', '-i', str(self.partial), '-map', '0:v', '-map', '0:a?',
                    '-progress', 'pipe:1', '-f', 'null', '-'])
            elif self.phase == 'decode-check':
                if fingerprint(Path(self.job['raw'])) != self.job['source_fingerprint']:
                    raise ValueError('Raw file changed during conversion')
                # No replacement of existing user files, even if created mid-conversion.
                with self.partial.open('rb') as f:
                    os.fsync(f.fileno())
                os.link(self.partial, self.destination)
                self.partial.unlink()
                directory_fd = os.open(self.destination.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
                job = self.job
                self.store.update(job, state='done', verified=True, progress=100,
                                  output=str(self.destination), output_fingerprint=fingerprint(self.destination), error='')
                try:
                    if delete_verified_source(job):
                        self.store.update(job, raw_deleted=True)
                except (OSError, ValueError) as exc:
                    self.store.update(job, error='Output completed; original kept: ' + str(exc))
                self.job = None
                self.changed.emit()
                self.done.emit(job)
                QTimer.singleShot(0, self.pump)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            self.fail(str(exc))

    def fail(self, message):
        if self.job:
            self.store.update(self.job, state='conversion_error', error=message, verified=False)
        self.log.emit(message)
        self.job = None
        self.changed.emit()
        QTimer.singleShot(0, self.pump)

    def cancel(self):
        self.paused = True
        if self.job:
            self.stopping = True
            interrupt(self.process)
        self.changed.emit()

    def retry(self, job):
        if job['state'] not in {'error', 'cancelled', 'interrupted', 'conversion_error'}:
            raise ValueError('This job cannot be queued again')
        if not Path(job['raw']).is_file():
            raise ValueError('No raw file available')
        # Explicit recovery of partial captures never inherits permission to delete.
        job['options']['delete_raw'] = False
        self.store.update(job, state='queued', error='', progress=0, verified=False)
        self.paused = False
        self.pump()
