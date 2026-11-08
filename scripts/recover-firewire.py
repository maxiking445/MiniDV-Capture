#!/usr/bin/env python3
"""One-shot OHCI detach/reset/probe. Default invocation only inspects hardware.

A successful result confirms controller initialization, NOT DV reception.
Unbind can block in the kernel; a caller timeout must never trigger another try.
"""
import argparse
import fcntl
import os
from pathlib import Path
import re
import signal
import stat
import time

PCI = Path('/sys/bus/pci/devices')
DRIVER = Path('/sys/bus/pci/drivers/firewire_ohci')
PROC = Path('/proc')
ADDRESS = re.compile(r'[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]')


def isolated_reset_methods(device, methods):
    # Never allow the PCI core to fall back to a downstream/shared bus reset.
    return [method for method in methods.split() if method == 'pm']


def inspect_controller(address):
    if not ADDRESS.fullmatch(address):
        raise RuntimeError('Invalid PCI address')
    device = PCI / address
    if (device / 'class').read_text().strip() != '0x0c0010':
        raise RuntimeError('Selected device is not an OHCI FireWire controller')
    if (device / 'driver').resolve() != DRIVER.resolve():
        raise RuntimeError('Selected controller is not bound to firewire_ohci')
    # Release waiters no longer necessarily have an fd identifying their card.
    controllers = [p for p in PCI.iterdir()
                   if ADDRESS.fullmatch(p.name)
                   and (p / 'class').read_text().strip() == '0x0c0010']
    if len(controllers) != 1:
        raise RuntimeError('Recovery requires exactly one OHCI FireWire controller')
    methods = (device / 'reset_method').read_text().strip()
    if not isolated_reset_methods(device, methods):
        raise RuntimeError('No isolated PM reset available; PCI bus reset refused')
    return device, methods


def check_clients(owner):
    """Reject live clients; permit only our user's dvgrab release waiters.

    This check requires root and fails closed if procfs cannot be inspected.
    Applications must be stopped first; this is not an interprocess reservation
    against an unrelated program opening FireWire after the check.
    """
    blocked = []
    for process in PROC.iterdir():
        if not process.name.isdecimal():
            continue
        try:
            for fd in (process / 'fd').iterdir():
                try:
                    target = os.readlink(fd)
                except FileNotFoundError:
                    continue
                if re.fullmatch(r'/dev/fw\d+(?: \(deleted\))?', target):
                    raise RuntimeError(f'Process {process.name} still has FireWire open. Stop all FireWire applications first.')
            waits = []
            for task in (process / 'task').iterdir():
                try:
                    waits.append((task / 'wchan').read_text().strip())
                except FileNotFoundError:
                    continue
            if 'fw_device_op_release' in waits:
                if process.stat().st_uid != owner or (process / 'comm').read_text().strip() != 'dvgrab':
                    raise RuntimeError(f'Unidentified FireWire release waiter {process.name}; recovery refused.')
                blocked.append(process)
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError as exc:
            raise RuntimeError('Cannot inspect all FireWire users; recovery refused.') from exc
    return blocked


def stop_waiters(blocked, owner):
    for process in blocked:
        try:
            handle = os.pidfd_open(int(process.name))
            try:
                if process.stat().st_uid != owner or (process / 'comm').read_text().strip() != 'dvgrab':
                    raise RuntimeError('Capture process identity changed; recovery refused.')
                signal.pidfd_send_signal(handle, signal.SIGKILL)
            finally:
                os.close(handle)
        except (FileNotFoundError, ProcessLookupError):
            pass


def has_local_node(device):
    for node in device.glob('fw[0-9]*'):
        try:
            if (node / 'is_local').read_text().strip() == '1':
                return True
        except FileNotFoundError:
            continue
    return False


def restart_controller(address, device, methods, owner):
    stop_waiters(check_clients(owner), owner)
    # Crucially, reset only AFTER normal driver removal has completed. A raw
    # PCI reset with OHCI still bound does not reinitialize its DMA contexts.
    print('Detaching firewire_ohci; this may block if kernel cleanup cannot finish.', flush=True)
    (DRIVER / 'unbind').write_text(address)
    if (device / 'driver').exists():
        raise RuntimeError('Controller is still bound; no PCI reset was attempted.')
    for _ in range(20):
        if not check_clients(owner):
            break
        time.sleep(0.1)
    else:
        raise RuntimeError('Release waiters remain after detach; reset and rebind were not attempted.')

    failure = None
    try:
        (device / 'reset_method').write_text('pm')
        print('Resetting detached controller using isolated PM reset.', flush=True)
        (device / 'reset').write_text('1')
    except OSError as exc:
        failure = exc
    finally:
        # A failed reset still needs an attempt to restore normal binding.
        try:
            (device / 'reset_method').write_text(methods)
        except OSError as exc:
            failure = failure or exc
        print('Binding firewire_ohci for fresh controller initialization.', flush=True)
        (DRIVER / 'bind').write_text(address)
    if failure:
        raise RuntimeError(f'Reset or reset-method restoration failed: {failure}; no recovery success claimed.')
    for _ in range(50):
        if (device / 'driver').resolve() == DRIVER.resolve() and has_local_node(device):
            if check_clients(owner):
                raise RuntimeError('FireWire release waiters remain; recovery not confirmed.')
            print('Controller reinitialized; release waiters cleared. DV reception and camera transport '
                  'are NOT yet verified. No capture was started.', flush=True)
            return
        time.sleep(0.1)
    raise RuntimeError('Controller initialization could not be verified; no capture was started.')


def recover(address, restart=False):
    device, methods = inspect_controller(address)
    if not restart:
        print(f'{address}: firewire_ohci bound; reset methods: {methods}. '
              'An isolated PM reset is available. Inspection only; no driver or hardware changes.', flush=True)
        return
    if os.geteuid() != 0:
        raise RuntimeError('Controller restart requires administrator authorization.')
    owner = int(os.environ.get('PKEXEC_UID', os.environ.get('SUDO_UID', os.getuid())))
    # A helper blocked in unbind keeps this lock even after a pending SIGKILL.
    # Never stack reset attempts behind a kernel operation that has not returned.
    lock_fd = os.open('/run/lock/minidv-firewire-restart.lock',
                      os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(lock_fd, 'r+') as lock:
        info = os.fstat(lock.fileno())
        if info.st_uid != 0 or not stat.S_ISREG(info.st_mode):
            raise RuntimeError('Restart lock is not a root-owned regular file; recovery refused.')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another FireWire restart is still pending; no second attempt started.') from exc
        device, methods = inspect_controller(address)
        pending = Path('/run/minidv-firewire-restart.pending')
        if pending.exists():
            raise RuntimeError('A previous restart did not complete; administrator inspection is required.')
        pending.write_text(address)
        try:
            restart_controller(address, device, methods, owner)
        finally:
            pending.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('address')
    parser.add_argument('--restart', action='store_true', help='Detach, PM reset and initialize the controller; requires root')
    args = parser.parse_args()
    try:
        recover(args.address, args.restart)
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
