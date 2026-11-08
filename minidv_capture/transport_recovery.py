"""Isolated AV/C recovery worker. Never run alongside a capture or another query."""
import ctypes as c
from collections import Counter
import json
from pathlib import Path
import re
import sys
import time
from .devices import discover


def timecode_seconds(value):
    if not re.fullmatch(r'\d{2}:\d{2}:\d{2}[:.]\d{2}', value):
        raise ValueError('Camera did not return a valid timecode')
    h, m, s, f = map(int, re.split('[:.]', value))
    if h >= 24 or m >= 60 or s >= 60 or f >= 30:
        raise ValueError('Camera timecode is out of range')
    return h * 3600 + m * 60 + s


def saved_timecode(path):
    """Read only the last complete DV frame; refuse conflicting/invalid packs.

    DV subcode packs are 5 bytes in 8-byte SSYB records. Require repeated
    timecode values instead of trusting a single damaged packet. No resync or
    inference from file duration: tape timecode can differ from capture time.
    """
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Unsafe DV checkpoint path')
    with path.open('rb') as source:
        header = source.read(4)
        if len(header) != 4 or header[0] >> 5 != 0:
            raise ValueError('No valid DV header at checkpoint')
        pal = bool(header[3] & 0x80)
        frame_size, fps = (144000, 25) if pal else (120000, 30)
        size = source.seek(0, 2)
        if size < frame_size:
            raise ValueError('No complete saved DV frame for recovery')
        source.seek((size // frame_size - 1) * frame_size)
        frame = source.read(frame_size)
    values = Counter()
    for sequence in range(12 if pal else 10):
        for block in (1, 2):
            offset = sequence * 12000 + block * 80
            if frame[offset] >> 5 != 1:
                continue
            for packet in range(6):
                pos = offset + 6 + packet * 8
                pack = frame[pos:pos + 5]
                if pack[0] != 0x13:
                    continue
                digits = [byte & mask for byte, mask in zip(pack[1:], (0x3f, 0x7f, 0x7f, 0x3f))]
                if any(byte & 15 > 9 for byte in digits):
                    continue
                f, s, m, h = [(byte >> 4) * 10 + (byte & 15) for byte in digits]
                if f < fps and s < 60 and m < 60 and h < 24:
                    values[f'{h:02}:{m:02}:{s:02}:{f:02}'] += 1
    if len(values) != 1 or next(iter(values.values()), 0) < 2:
        raise ValueError('Last saved DV frame has no unambiguous timecode; automatic rewind refused')
    return next(iter(values))


class Camera:
    def __init__(self, guid):
        device = next((d for d in discover() if d.guid == guid and d.accessible), None)
        if device is None:
            raise RuntimeError('Original camera is not accessible after restart')
        self.raw = c.CDLL('libraw1394.so.11')
        self.rom = c.CDLL('librom1394.so.0')
        self.avc = c.CDLL('libavc1394.so.0')
        self.raw.raw1394_new_handle_on_port.argtypes = [c.c_int]
        self.raw.raw1394_new_handle_on_port.restype = c.c_void_p
        self.raw.raw1394_destroy_handle.argtypes = [c.c_void_p]
        self.raw.raw1394_get_nodecount.argtypes = [c.c_void_p]
        self.rom.rom1394_get_guid.argtypes = [c.c_void_p, c.c_uint16]
        self.rom.rom1394_get_guid.restype = c.c_uint64
        for name in ('stop', 'rewind', 'play', 'status'):
            function = getattr(self.avc, 'avc1394_vcr_' + name)
            function.argtypes = [c.c_void_p, c.c_uint16]
            function.restype = c.c_uint32 if name == 'status' else None
        self.avc.avc1394_vcr_get_timecode2.argtypes = [c.c_void_p, c.c_uint16, c.c_char_p]
        self.avc.avc1394_vcr_get_timecode2.restype = c.c_int
        self.handle = self.raw.raw1394_new_handle_on_port(device.card)
        if not self.handle:
            raise RuntimeError('Could not open FireWire for camera control')
        try:
            self.node = next(node for node in range(self.raw.raw1394_get_nodecount(self.handle))
                             if self.rom.rom1394_get_guid(self.handle, node) == int(guid, 16))
        except Exception as exc:
            self.close()
            raise RuntimeError('Original camera GUID not found on the bus') from exc

    def close(self):
        if self.handle:
            self.raw.raw1394_destroy_handle(self.handle)
            self.handle = None

    def status(self):
        return self.avc.avc1394_vcr_status(self.handle, self.node)

    def timecode(self):
        buffer = c.create_string_buffer(16)
        result = self.avc.avc1394_vcr_get_timecode2(self.handle, self.node, buffer)
        if result < 0:
            raise RuntimeError('Camera timecode unavailable; check tape and PLAYER/VCR mode')
        value = buffer.value.decode('ascii')
        timecode_seconds(value)
        return value

    def stop(self):
        self.avc.avc1394_vcr_stop(self.handle, self.node)
        deadline = time.monotonic() + 15
        previous = None
        while time.monotonic() < deadline:
            status = self.status()
            if status != previous:
                print(f'Camera STOP status: 0x{status:08x}', file=sys.stderr, flush=True)
                previous = status
            if status == 0x0c20c460:
                return
            time.sleep(.2)
        raise RuntimeError('Camera STOP was not confirmed. Stop playback manually; capture will not resume.')


def prepare(camera, checkpoint, overlap=180, already_stopped=False):
    if not already_stopped:
        camera.stop()  # Stop immediately after reconnection, before reading position.
    target = max(0, timecode_seconds(checkpoint) - overlap)
    current = timecode_seconds(camera.timecode())
    if current < timecode_seconds(checkpoint) - 2:
        raise RuntimeError('Camera timecode precedes the saved scene; tape position is ambiguous')
    if current <= target:
        return camera.timecode()
    print(f'Rewind: current={current}s, target<={target}s; saved={checkpoint}', file=sys.stderr, flush=True)
    camera.avc.avc1394_vcr_rewind(camera.handle, camera.node)
    deadline = time.monotonic() + 90
    last_progress = time.monotonic()
    previous = current
    try:
        while time.monotonic() < deadline:
            time.sleep(.2)
            current = timecode_seconds(camera.timecode())
            if previous - current > 60:
                raise RuntimeError('Large timecode discontinuity during rewind; tape position is ambiguous')
            if current <= target:
                break
            if current < previous:
                last_progress = time.monotonic()
            elif current > previous + 1:
                raise RuntimeError('Tape timecode increased while rewinding; position is uncertain')
            if time.monotonic() - last_progress > 5:
                raise RuntimeError('Rewind made no confirmed progress')
            previous = current
        else:
            raise RuntimeError('Rewind timed out')
    finally:
        camera.stop()
    actual = camera.timecode()
    if timecode_seconds(actual) > target:
        raise RuntimeError('Required overlap was not reached; capture not resumed')
    return actual


def run(guid, path=None):
    deadline = time.monotonic() + 15
    while not any(d.guid == guid and d.accessible for d in discover()):
        if time.monotonic() >= deadline:
            raise RuntimeError('Camera did not reconnect after controller restart')
        time.sleep(.25)
    camera = Camera(guid)
    try:
        if path:
            # STOP must precede even a failing checkpoint read.
            camera.stop()
            checkpoint = saved_timecode(path)
            actual = prepare(camera, checkpoint, already_stopped=True)
            result = {'prepared': True, 'saved': checkpoint, 'position': actual}
        else:
            camera.stop()
            result = {'stopped': True, 'position': camera.timecode()}
    finally:
        camera.close()
    print(json.dumps(result), flush=True)
