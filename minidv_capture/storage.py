from pathlib import Path
import json
import os
import re
import time
import uuid
from .preferences import english_options


def atomic_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('x', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        temp.unlink(missing_ok=True)


def fingerprint(path: Path) -> list[int]:
    s = path.stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns]


def safe_name(value: str) -> str:
    value = re.sub(r'[^\w .-]', '_', value, flags=re.UNICODE).strip(' .')[:80]
    return value or 'Tape'


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.jobs = []
        self.warning = ''
        if path.exists():
            try:
                data = json.loads(path.read_text())
                if not isinstance(data, dict) or not isinstance(data.get('jobs'), list):
                    raise ValueError('Invalid queue')
                for job in data['jobs']:
                    if not isinstance(job, dict) or not all(k in job for k in ('id', 'state', 'directory', 'raw', 'options')):
                        raise ValueError('Invalid job')
                self.jobs = data['jobs']
            except (OSError, ValueError) as exc:
                # Never overwrite a broken state file silently.
                raise RuntimeError(f'Cannot read queue: {path}\n{exc}') from exc
        for job in self.jobs:
            job['options'] = english_options(job['options'])
            if job['state'] == 'capturing':
                previous_state = job['state']
                job['interrupted_from'] = previous_state
                job['capture_incomplete'] = True
                job['state'] = 'interrupted'
                job['error'] = 'Capture was interrupted. Raw files are kept; resume capture or retry conversion.'
                self.warning = 'Interrupted captures found. Raw files were kept.'
            elif job['state'] in {'converting', 'verifying'}:
                previous_state = job['state']
                job['interrupted_from'] = previous_state
                job['capture_incomplete'] = False
                job.update(state='queued', error='', progress=0, verified=False)
                self.warning = 'Interrupted conversions were queued to restart automatically.'
            elif job['state'] in {'error', 'cancelled'}:
                job.setdefault('capture_incomplete', True)
            elif job['state'] == 'interrupted':
                job.setdefault('capture_incomplete', True)
        for job in self.jobs:
            if job.get('resume_merge_pending'):
                try:
                    self.finish_resume_merge(job)
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    job.update(state='error', capture_incomplete=True,
                               error=f'Could not safely recover resumed capture merge: {exc}')
        self.save()

    def save(self):
        atomic_json(self.path, {'version': 1, 'jobs': self.jobs})

    def clear_history(self):
        remaining = [j for j in self.jobs if j['state'] in {'capturing', 'queued', 'converting', 'verifying'}]
        removed = len(self.jobs) - len(remaining)
        atomic_json(self.path, {'version': 1, 'jobs': remaining})
        self.jobs = remaining
        return removed

    def remove(self, job):
        if job['state'] in {'capturing', 'queued', 'converting', 'verifying'}:
            raise ValueError('Stop or finish this tape before removing it from history.')
        index = next((i for i, item in enumerate(self.jobs) if item['id'] == job['id']), None)
        if index is None:
            return False
        removed = self.jobs.pop(index)
        try:
            self.save()
        except OSError:
            self.jobs.insert(index, removed)
            raise
        return True

    def finish_resume_merge(self, job):
        """Atomically append saved continuation segments to this tape's DV file."""
        directory = Path(job['directory']).resolve()
        raw = Path(job['raw'])
        if raw.is_symlink() or raw.name != 'capture001.dv' or raw.parent.resolve() != directory:
            raise ValueError('Unsafe original DV path')
        if not raw.is_file():
            raise ValueError('Original DV capture is missing')
        pending = job.get('resume_merge_pending')
        if pending:
            names = pending['parts']
            base_size = int(pending['base_size'])
            expected_size = int(pending['expected_size'])
            sizes = pending['sizes']
        else:
            parts = sorted(directory.glob('capture-resume-*.dv'),
                           key=lambda p: (p.stat().st_mtime_ns, p.name))
            if not parts:
                raise ValueError('No resumed DV segments were found')
            if any(p.is_symlink() or p.parent.resolve() != directory or not p.is_file() for p in parts):
                raise ValueError('Unsafe resumed DV segment path')
            sizes = {p.name: p.stat().st_size for p in parts}
            base_size = raw.stat().st_size
            expected_size = base_size + sum(sizes.values())
            names = list(sizes)
            pending = {'parts': names, 'sizes': sizes, 'base_size': base_size,
                       'expected_size': expected_size, 'base_fingerprint': fingerprint(raw)}
            self.update(job, resume_merge_pending=pending)

        if any(not isinstance(name, str) or Path(name).name != name
               or not name.startswith('capture-resume-') or not name.endswith('.dv') for name in names):
            raise ValueError('Unsafe resumed segment name')

        if raw.stat().st_size == expected_size:
            if fingerprint(raw) != pending.get('merged_fingerprint'):
                raise ValueError('Merged DV file changed while continuation recovery was pending')
            for name in names:
                (directory / name).unlink(missing_ok=True)
        elif raw.stat().st_size == base_size:
            if fingerprint(raw) != pending.get('base_fingerprint'):
                raise ValueError('Original DV file changed while continuation was pending')
            parts = []
            for name in names:
                part = directory / name
                if part.is_symlink() or part.parent.resolve() != directory or not part.is_file():
                    raise ValueError(f'Resumed segment is missing or unsafe: {name}')
                if part.stat().st_size != int(sizes[name]):
                    raise ValueError(f'Resumed segment changed during merge: {name}')
                parts.append(part)
            temp = raw.with_name(raw.name + '.merge.tmp')
            if temp.is_symlink():
                raise ValueError('Unsafe temporary merge path')
            with temp.open('wb') as output:
                for source in [raw, *parts]:
                    with source.open('rb') as incoming:
                        while chunk := incoming.read(1024 * 1024):
                            output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            pending['merged_fingerprint'] = fingerprint(temp)
            self.update(job, resume_merge_pending=pending)
            os.replace(temp, raw)
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            for part in parts:
                part.unlink()
        else:
            raise ValueError('Original DV size changed while the continuation was pending')

        job.pop('resume_merge_pending', None)
        self.update(job, state='queued', capture_incomplete=False, bytes=expected_size, error='')
        return expected_size

    def create(self, folder: Path, label: str, device: dict, options: dict) -> dict:
        folder = folder.expanduser().resolve()
        folder.mkdir(parents=True, exist_ok=True)
        base = safe_name(label)
        for index in range(1, 1000000):
            directory = folder / f'{base}-{index:03d}'
            try:
                directory.mkdir()
                break
            except FileExistsError:
                continue
        else:
            raise RuntimeError('No available tape number')
        job = {'id': uuid.uuid4().hex, 'name': directory.name, 'directory': str(directory),
               'raw': str(directory / 'capture001.dv'), 'device': device, 'options': options,
               'state': 'capturing', 'created': time.time(), 'error': '', 'output': '',
               'verified': False, 'progress': 0, 'capture_incomplete': True}
        self.jobs.append(job)
        self.update(job)
        return job

    def update(self, job: dict, **changes):
        job.update(changes)
        atomic_json(Path(job['directory']) / 'job.json', job)
        self.save()


def delete_verified_source(job: dict):
    """Deletion is opt-in and restricted to this job's unchanged raw capture."""
    if not job['options'].get('delete_raw') or not job.get('verified') or job['state'] != 'done':
        return False
    raw, output = Path(job['raw']), Path(job['output'])
    if raw.is_symlink() or raw.name != 'capture001.dv' or raw.parent.resolve() != Path(job['directory']).resolve():
        raise ValueError('Unsafe raw file path; original kept')
    if not output.is_file() or output.is_symlink() or output.resolve() == raw.resolve():
        raise ValueError('Verified output missing; original kept')
    if fingerprint(raw) != job.get('source_fingerprint') or fingerprint(output) != job.get('output_fingerprint'):
        raise ValueError('File changed since verification; original kept')
    raw.unlink()
    return True
