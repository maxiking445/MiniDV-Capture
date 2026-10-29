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
            if job['state'] in {'capturing', 'converting', 'verifying'}:
                job['state'] = 'interrupted'
                job['error'] = 'Previous run interrupted. Raw files are kept; retry conversion explicitly.'
                self.warning = 'Interrupted jobs found. Raw files were kept.'
        self.save()

    def save(self):
        atomic_json(self.path, {'version': 1, 'jobs': self.jobs})

    def clear_history(self):
        remaining = [j for j in self.jobs if j['state'] in {'capturing', 'queued', 'converting', 'verifying'}]
        removed = len(self.jobs) - len(remaining)
        atomic_json(self.path, {'version': 1, 'jobs': remaining})
        self.jobs = remaining
        return removed

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
               'verified': False, 'progress': 0}
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
