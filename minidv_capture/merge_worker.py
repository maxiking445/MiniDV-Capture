"""Copy resumed segments outside the GUI; the parent commits the result."""
import json
import os
from pathlib import Path
from .storage import fingerprint


def copy_merge(manifest_path):
    plan = json.loads(Path(manifest_path).read_text())
    temp = Path(plan['temp'])
    sources = [Path(p) for p in plan['sources']]
    if temp.is_symlink() or any(p.is_symlink() or p.parent != temp.parent or p == temp for p in sources):
        raise ValueError('Unsafe merge path')
    if [fingerprint(p) for p in sources] != plan['fingerprints']:
        raise ValueError('Merge sources changed')
    with temp.open('wb') as output:
        for path in sources:
            with path.open('rb') as incoming:
                while chunk := incoming.read(1024 * 1024):
                    output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    if temp.stat().st_size != plan['size'] or [fingerprint(p) for p in sources] != plan['fingerprints']:
        raise ValueError('Merge sources changed while copying')
    print(json.dumps({'fingerprint': fingerprint(temp)}), flush=True)
