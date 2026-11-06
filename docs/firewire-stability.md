# FireWire stability investigation — 2026-11-06

## Evidence from this machine

Read-only inspection of `/home/max/Videos/MiniDV/*/capture.log`, the application
log, and `journalctl -k -b -1` found:

- `max-001` and `max-003` exited normally after capture.
- `max-002`: 2026-11-05 19:46:58, signal loss triggered shutdown; an additional
  AV/C STOP helper opened FireWire while dvgrab was stopping. The helper timed out
  at 19:47:01. Neither process logged successful cleanup.
- The kernel had already reported repeated `AMD-Vi: IO_PAGE_FAULT` for
  `firewire_ohci 0000:06:00.0` before that shutdown.
- At 19:47:04 the controller reported `DMA context still active (0x40000411)`.
- Subsequent hung-task reports show both dvgrab and minidv-capture blocked in
  `fw_device_op_release`, eventually for more than 614 seconds.

This establishes a kernel/controller failure and a second helper caught in the
same release path. It does not establish that the STOP helper caused the initial
DMA fault, or prove the cause of the reported GPU stutters or boot-screen hang.
The kernel source reports “DMA context still active” when the controller does
not clear its active bit after a stop request:
https://code.googlesource.com/linux/torvalds/linux/+/24a0b5e196cf70ccff97bc0add6fa7178ad50cc4/drivers/firewire/ohci.c

## Application changes

- Let dvgrab handle automatic transport shutdown; never open a parallel STOP
  helper. Manual capture requires stopping playback on the camera itself.
- Do not automatically reset the PCI controller or retry a blocked capture.
- Disable cassette polling after a timeout/crash and before touching an already
  blocked driver. A pending query blocks new captures and capture continuation.
- Never synchronously wait for a cassette helper in the GUI or destroy its
  QProcess while it is running. Retain it until actual process completion.
- Apply the existing ten-second application exit watchdog to idle exits too,
  including retained helpers. Handle SIGTERM, SIGINT and desktop session shutdown
  without a confirmation dialog that could stall logout.
- Interrupt a capture even when cancellation arrives during process startup.
- Report a capture that has not exited after seven seconds; preserve its raw
  footage and keep its bus reserved until the process actually exits.

The watchdog bounds application shutdown while userspace is schedulable. It
cannot release an uninterruptible kernel task or repair controller DMA. These
changes therefore reduce hazardous retries and GUI hangs; they do not guarantee
that system shutdown/boot failures are fixed. Kernel/controller investigation
remains necessary if DMA faults recur. No kernel parameters, drivers or firmware
were changed, and no controller reset was performed during this investigation.

Regression tests use simulated failures and ordinary child processes. They do
not induce a real FireWire kernel hang. Run with:

```sh
QT_QPA_PLATFORM=offscreen .build-venv/bin/python -m unittest discover -s tests -q
```

Launch the changed source with `./start.sh`. Existing packaged binaries must be
rebuilt separately; a running instance does not pick up these changes.

## Deeper investigation (15-minute pass)

Hardware from `lspci -nnk`:

- AMD Ryzen platform; NVIDIA RTX 4070 SUPER and AMD integrated graphics.
- ASMedia ASM1083/1085 bridge `1b21:1080`, PCI `0000:05:00.0`.
- VIA VT6306/7/8 `1106:3044`, revision `80`, PCI `0000:06:00.0`.
- FireWire DMA masks are 32-bit. Its IOMMU group uses `DMA-FQ` translation.
- Running kernel: `7.3.1-1-cachyos`; installed alternative:
  `linux-cachyos-lts 6.18.55-2`.

On November 5, **18,086** FireWire `IO_PAGE_FAULT` entries occurred between
16:58:48 and 19:45:56. The first fault is only 29 seconds after the first capture
process started, long before its successful stop at 18:03:45. Similar faults
exist in both the November 4 and current November 6 boots. A 19:07 UTC snapshot
on November 6 already contained 4,970 such entries. They are not merely a side
effect of the failing STOP helper or the final capture abort.

The Linux OHCI source explicitly documents the Ryzen + ASM108x + VT630x reboot
problem and defines `QUIRK_REBOOT_BY_CYCLE_TIMER_READ = 0x80000000`. This machine
logs `quirks 0x80000011`: that protection is **already active**. This is evidence
of a problematic hardware combination, not proof that the documented timer
register issue is the cause of these particular DMA faults. The mitigation
avoids cycle-timer reads; it is not a general DMA fault repair.

Source: https://raw.githubusercontent.com/torvalds/linux/master/drivers/firewire/ohci.c

Read-only disassembly of the installed `firewire-core.ko.zst` confirms the
reported return address `fw_device_op_release+0x26d` immediately follows
`schedule()` inside an uninterruptible wait (`TASK_UNINTERRUPTIBLE`, value 2).
The surrounding xarray traversal corresponds to waiting for outstanding
transactions in `wait_event(client->tx_flush_wait, !has_outbound_transactions(client))`.
This explains the persistent D-state after process termination; issuing more
SIGKILLs cannot make the missing controller completion arrive.

Source: https://raw.githubusercontent.com/torvalds/linux/master/drivers/firewire/core-cdev.c

No NVIDIA Xid, AMD GPU timeout/reset, PCIe AER, or soft/hard lockup entry was
found by the targeted search of the November 5 kernel journal. This does not
prove the graphics stack was unaffected, but gives no positive basis to blame
the GPU. The shutdown journal ends without a completed power-off; it cannot
establish the cause of every reported boot or shutdown incident.

### Additional protections implemented

- Passive `journalctl` monitor: bounded snapshot of the latest 200 matching
  kernel messages in the **current boot**, then live following from its cursor.
  It never opens `/dev/fw*`, invokes a reset, or asks for elevated privileges.
- DMA/access/stalled-context errors latch a per-controller capture block for the
  monitor's lifetime. Matching running captures stop as errors, including those
  already waiting for a nominal tape-end stop. Repeated fault lines produce only
  one application notification per controller. Cassette polling is stopped too.
- Capture is blocked while the initial health check is pending or if kernel-log
  access/monitoring fails. A lost monitor also stops active captures. This
  intentionally requires usable systemd kernel-journal access; lack of access
  must not be represented as a healthy controller. History unavailable through
  journal rotation or outside the bounded snapshot cannot be reconstructed.
- Preview termination is fully asynchronous. A retained decoder prevents another
  decoder from being spawned, avoiding process accumulation on repeated switches.
- FFmpeg encoder discovery is an asynchronous queue phase with a timeout rather
  than a blocking `subprocess.run` in the GUI. Conversion processes run with
  niceness +10 when `nice` is available. Existing thread limits remain in place.
- The conversion watchdog only interrupts a stalled job once.

The real journal monitor was exercised read-only: it detected `0000:06:00.0`,
entered live-follow mode, and exited cleanly. Automated tests cover split log
lines, noise, controller isolation, repeated faults, lost permissions/processes,
startup/follow handoff, live capture fault handling, and retained preview children.
No live capture or controller reset was used to reproduce the host hang.

### Next system-level discrimination

The exact defective component (OHCI hardware, PCI bridge, DMA mapping/driver,
or their interaction) is still not proven. The least invasive next comparison
is booting the **already installed LTS kernel** and checking whether a short,
supervised capture produces any new DMA faults. If the same pattern remains,
a different controller without this VIA/ASMedia bridge combination is a useful
hardware comparison. Neither test has been performed here.

Do not treat disabling IOMMU globally as an established fix: it changes DMA
isolation and can hide rejected DMA accesses rather than correct their cause.
No bootloader, IOMMU setting, kernel, or driver was changed by this work.
