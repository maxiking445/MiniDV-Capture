from dataclasses import dataclass, asdict
from pathlib import Path
import os
import re


@dataclass(frozen=True)
class Device:
    guid: str
    name: str
    node: str
    bus: str
    card: int
    accessible: bool

    def to_dict(self):
        return asdict(self)


def read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def discover(root=Path('/sys/bus/firewire/devices'), devroot=Path('/dev')) -> list[Device]:
    """Passive sysfs discovery; never sends an AV/C transport command.

    libraw1394 enumerates local cards by increasing fw node order. Each remote
    device belongs to the same sysfs controller directory as its local node.
    Discovery is repeated before every capture (fw numbers can change).
    """
    nodes = sorted((p for p in root.glob('fw*') if re.fullmatch(r'fw\d+', p.name)),
                   key=lambda p: int(p.name[2:]))
    local = [p for p in nodes if read(p / 'is_local') == '1']
    buses = {str(p.resolve().parent): i for i, p in enumerate(local)}
    found = []
    for node in nodes:
        if '0x00a02d:0x010001' not in read(node / 'units'):
            continue
        guid = read(node / 'guid').lower().removeprefix('0x')
        if not re.fullmatch(r'[0-9a-f]{16}', guid):
            continue
        bus = str(node.resolve().parent)
        name = ' '.join(filter(None, [read(node / 'vendor_name'), read(node / 'model_name')]))
        device = devroot / node.name
        found.append(Device(guid, name or 'DV camera', str(device), bus,
                            buses.get(bus, -1), os.access(device, os.R_OK | os.W_OK)))
    return found
