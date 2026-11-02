#!/usr/bin/env python3
"""Recover one FireWire controller; never reset a shared PCI bridge."""
import os
from pathlib import Path
import re
import signal
import sys
import time


def blocked_tasks():
    result = []
    for process in Path('/proc').iterdir():
        if not process.name.isdecimal():
            continue
        try:
            if any((task / 'wchan').read_text().strip() == 'fw_device_op_release'
                   for task in (process / 'task').iterdir()):
                result.append(process)
        except (OSError, ProcessLookupError):
            continue
    return result


def isolated_reset_methods(device, methods):
    # Even a dedicated downstream bus reset did not recover this failure and
    # coincided with encoder timeouts on the affected host. Never automate it.
    return [method for method in methods.split() if method == 'pm']


def recover(address):
    if not re.fullmatch(r'[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]', address):
        raise RuntimeError('Invalid PCI address')
    device = Path('/sys/bus/pci/devices') / address
    if device.joinpath('class').read_text().strip() != '0x0c0010':
        raise RuntimeError('Selected device is not an OHCI FireWire controller')
    if device.joinpath('driver').resolve().name != 'firewire_ohci':
        raise RuntimeError('Selected device is not using firewire_ohci')
    # A release blocked in the kernel has usually already closed its fds, so
    # its controller cannot reliably be identified. Refuse ambiguous systems.
    controllers = [p for p in Path('/sys/bus/pci/drivers/firewire_ohci').iterdir()
                   if re.fullmatch(r'[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]', p.name)]
    if len(controllers) != 1:
        raise RuntimeError('Automatic recovery requires exactly one FireWire controller')
    owner = int(os.environ.get('PKEXEC_UID', os.environ.get('SUDO_UID', os.getuid())))
    blocked = blocked_tasks()
    if not blocked:
        print('No blocked FireWire tasks remain.', flush=True)
        return
    blocked_ids = {p.name for p in blocked}
    for process in Path('/proc').iterdir():
        if not process.name.isdecimal() or process.name in blocked_ids:
            continue
        try:
            for fd in (process / 'fd').iterdir():
                try:
                    target = os.readlink(fd)
                except OSError:
                    continue
                if re.fullmatch(r'/dev/fw\d+', target):
                    raise RuntimeError(f'Process {process.name} is still using FireWire. Stop active captures first.')
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    for process in blocked:
        try:
            # Never kill another user's process or an unidentified Python process.
            if process.stat().st_uid != owner or process.joinpath('comm').read_text().strip() != 'dvgrab':
                continue
            handle = os.pidfd_open(int(process.name))
            try:
                if process.stat().st_uid == owner and process.joinpath('comm').read_text().strip() == 'dvgrab':
                    signal.pidfd_send_signal(handle, signal.SIGKILL)
                    print(f'Sent SIGKILL to blocked dvgrab {process.name}.', flush=True)
            finally:
                os.close(handle)
        except ProcessLookupError:
            pass
    time.sleep(1)
    if not blocked_tasks():
        print('FireWire tasks released.', flush=True)
        return
    methods_file = device / 'reset_method'
    methods = methods_file.read_text().strip()
    allowed = isolated_reset_methods(device, methods)
    if not allowed:
        raise RuntimeError('No isolated reset available; shared bus reset refused')
    try:
        for method in allowed:
            print(f'Resetting FireWire controller {address} using isolated {method} reset.', flush=True)
            try:
                methods_file.write_text(method)
                (device / 'reset').write_text('1')
                break
            except OSError as error:
                print(f'{method} reset failed: {error}', flush=True)
        else:
            raise RuntimeError('All isolated reset methods failed')
    finally:
        try:
            methods_file.write_text(methods)
        except OSError as error:
            print(f'Could not restore reset-method preference: {error}', flush=True)
    for _ in range(20):
        if not blocked_tasks():
            print('FireWire recovery completed.', flush=True)
            return
        time.sleep(0.25)
    raise RuntimeError('FireWire tasks remain blocked after reset. Recovery did not succeed.')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise RuntimeError('Expected one PCI address')
        recover(sys.argv[1])
    except (OSError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr, flush=True)
        raise SystemExit(1)
