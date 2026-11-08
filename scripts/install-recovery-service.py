#!/usr/bin/env python3
"""Install a fixed-target FireWire restart service and a narrowly scoped policy."""
import argparse
import json
import os
from pathlib import Path
import pwd
import re
import subprocess


def installation_target(address=None, uid=None, pci=Path('/sys/bus/pci/devices')):
    if uid is None:
        value = os.environ.get('PKEXEC_UID') or os.environ.get('SUDO_UID')
        if not value or not value.isdecimal() or int(value) <= 0:
            raise RuntimeError('Cannot identify the desktop user; specify --owner USER_ID.')
        uid = int(value)
    if address is None:
        controllers = [p.name for p in pci.iterdir()
                       if (p / 'class').read_text().strip() == '0x0c0010']
        if len(controllers) != 1:
            raise RuntimeError('Automatic recovery requires exactly one OHCI FireWire controller.')
        address = controllers[0]
    return address, uid


def check_service_support():
    if not Path('/run/systemd/system').is_dir():
        raise RuntimeError('The recovery service requires a running systemd system.')
    result = subprocess.run(['pkaction', '--version'], capture_output=True,
                            text=True, check=True, timeout=10)
    version = re.search(r'\b(\d+)\.(\d+)\b|\b(\d{3,})\b', result.stdout)
    supported = version and (int(version[3]) >= 106 if version[3] else
                             (int(version[1]), int(version[2])) >= (0, 106))
    if not supported:
        raise RuntimeError('Unattended recovery requires polkit >= 0.106 with JavaScript rules '
                           '(for example Ubuntu 24.04). Use administrator-authorized recovery on older systems.')


def service_files(address, uid, user):
    if not re.fullmatch(r'[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]', address):
        raise ValueError('Invalid PCI address')
    if uid <= 0 or not re.fullmatch(r'[a-z_][a-z0-9_-]*\$?', user):
        raise ValueError('A normal local user is required')
    unit = f'''[Unit]
Description=MiniDV fixed-controller FireWire recovery

[Service]
Type=oneshot
Environment=PKEXEC_UID={uid}
ExecStart=/usr/bin/python3 /usr/local/lib/minidv-capture/recover-firewire.py {address} --restart
TimeoutStartSec=45
TimeoutStopSec=5
KillMode=control-group
NoNewPrivileges=yes
ProtectHome=yes
StandardOutput=truncate:/run/minidv-firewire-recovery.log
StandardError=inherit
'''
    policy = f'''// Only this local user may start this fixed, root-owned recovery unit.
polkit.addRule(function(action, subject) {{
    if (action.id === "org.freedesktop.systemd1.manage-units" &&
        action.lookup("unit") === "minidv-firewire-recover.service" &&
        action.lookup("verb") === "start" &&
        subject.user === {json.dumps(user)} && subject.local && subject.active) {{
        return polkit.Result.YES;
    }}
}});
'''
    return unit, policy


def install(address=None, uid=None):
    if os.geteuid() != 0:
        raise RuntimeError('Administrator authorization is required')
    address, uid = installation_target(address, uid)
    check_service_support()
    user = pwd.getpwuid(uid).pw_name
    unit, policy = service_files(address, uid, user)
    destination = Path('/usr/local/lib/minidv-capture')
    destination.mkdir(mode=0o755, parents=True, exist_ok=True)
    if destination.is_symlink() or destination.stat().st_uid != 0 or destination.stat().st_mode & 0o022:
        raise RuntimeError('Recovery installation directory is not safely root-owned')
    # Atomic installs keep running readers on their old complete version.
    def write(path, contents, mode=0o644):
        temporary = path.with_name(path.name + '.install-tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
        try:
            with os.fdopen(fd, 'w') as output:
                output.write(contents)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    write(destination / 'recover-firewire.py', Path(__file__).with_name('recover-firewire.py').read_text())
    write(Path('/etc/systemd/system/minidv-firewire-recover.service'), unit)
    Path('/etc/polkit-1/rules.d').mkdir(parents=True, exist_ok=True, mode=0o755)
    write(Path('/etc/polkit-1/rules.d/49-minidv-firewire-recover.rules'), policy)
    subprocess.run(['systemctl', 'daemon-reload'], check=True, timeout=15)
    write(destination / 'recovery-service.json', json.dumps({'address': address, 'uid': uid}))
    print('Installed fixed-controller recovery service. It is not started or enabled at boot.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--address', help='PCI address; defaults to the single OHCI controller')
    parser.add_argument('--owner', type=int, help='Desktop user ID; defaults to the pkexec/sudo caller')
    args = parser.parse_args()
    try:
        install(args.address, args.owner)
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        parser.exit(1, str(exc) + '\n')
