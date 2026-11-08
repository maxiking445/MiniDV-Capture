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

## Correction: historical errors must not prevent a new attempt

The initial implementation latched historical journal entries as current faults.
That was too restrictive: a prior DMA error alone does not establish that the
controller is still blocked. The startup snapshot now only emits a warning.
After the snapshot completes, capture may start despite historical entries.
Live faults still stop/block capture, including a new occurrence identical to a
historical warning. Actual blocked FireWire tasks and still-running sessions
remain protected by the existing process/bus checks. This supersedes the initial
snapshot-blocking behavior described above.

## Correction: a DMA page fault alone is not a capture-stall signal

At 21:31:47 on November 6, a fresh IO_PAGE_FAULT arrived during startup/rewind,
9 seconds after dvgrab started. The monitor itself stopped capture before any
frames arrived. Treating any page fault as a controller hang was too broad.
Live IO_PAGE_FAULT entries now produce one visible warning per controller per
application run, without stopping playback/capture or latching a start block.
Explicit DMA-context stalls and register-access failures still trigger the
fault path. Existing blocked-task detection, bus ownership, signal-loss timeout,
and bounded application shutdown remain enabled. This restores capture attempts
but does not repair DMA faults or guarantee host stability.


## November 7 stall: why automatic driver reload is not enabled

The `max-010/capture.log` records capture starting at 21:42:09, missing/invalid
packets, signal-loss shutdown at 21:55:48, and a stuck process at 21:55:55.
The previous boot journal subsequently reports dvgrab thread 22707 in D state,
blocked in `fw_device_op_release+0x26d/0x480` for 983, 1105 and 1228 seconds.
This is a kernel-side release hang, not merely an application process awaiting
another stop button press. The running kernel is now 7.3.3-1-cachyos; 6.18.60-2-cachyos-lts is also
installed but was not booted/tested during this investigation.

A timed userspace command cannot guarantee cancellation of a kernel wait.
Upstream FireWire controller removal drains workqueues and waits for all card
references with `wait_for_completion(&card->done)`; it has no bounded completion
contract. This does not prove every unload will hang, but it rules out promising
that unload/reload will safely recover this fault. No module unload, PCI reset,
rebind, IOMMU change, or live capture was attempted during this investigation.
Source: https://github.com/torvalds/linux/blob/master/drivers/firewire/core-card.c
(`fw_core_remove_card`). A camera STOP/seek command also needs the affected bus.

Changes made:

- After 10 seconds without file growth following received data, emit one warning
  per stall, including a nonmodal visible dialog and notification. Keep monitoring
  for returning data. The recording lamps and status stop claiming data is arriving.
- After the existing 60-second timeout, request stop as an **incomplete capture**,
  not a confirmed tape end. No automatic conversion or next-tape workflow follows.
  This also means a real tape end detected only by silence needs manual review.
- Report errors immediately, without waiting for dvgrab to finish. A stuck stop
  updates the same dialog and keeps the bus reserved. Even a later clean exit
  after that deadline requires review instead of automatic conversion. Persistence failures must
  not prevent the initial stop signal or the stuck-process alert.
- If data returns after a warned stall, continue receiving, but require review
  at completion because the saved file may have a gap. Do not silently queue it.
- Resume instructions require positioning at least one minute before the last
  **saved** scene. Rewinding one minute from a tape that continued playing can
  leave a large gap. No automatic rewind or unverified seek is issued.

The saved max-010 raw file contains 14,473 complete PAL DV frames (2,084,112,000
bytes), about 9 minutes 39 seconds of video. An offline ffprobe check of its last
frame reports an invalid timecode. Therefore an exact automatic seek target
cannot be promised from this sample; inspect the saved scene itself. The original
file was only read, never modified.

Tests simulate a stalled/returning stream, a clean child exit after signal loss,
a stuck child, metadata write failure, and GUI warnings/status. These tests do
not establish hardware recovery or eliminate the underlying DMA/driver fault.


## Follow-up: a targeted restart is possible, but must include driver initialization

The earlier discussion was too categorical if read as saying that only a reboot
can ever recover FireWire. Current sysfs advertises `pm bus` for 0000:06:00.0.
A targeted controller restart is a candidate; availability does not establish
that it recovers the observed hang. A reboot also discards blocked kernel tasks
and rebuilds kernel/DMA state, which a userspace PCI reset does not do by itself.

A closer look at upstream OHCI shows:

- `pci_remove` invokes `fw_core_remove_card` before the final OHCI software reset.
- Card removal disables/flushed contexts and cancels pending transactions before
  waiting for the final references. This **could** unblock a release waiter; the
  presence of the final wait is not proof that unbind must fail.
- The upstream `fw_ohci_pci_driver` has probe/remove and system sleep handlers,
  but no PCI error-handler `reset_prepare`/`reset_done` hooks. A raw PCI `reset`
  write while the driver stays bound therefore must not be equated with fresh
  OHCI initialization. PCI configuration restoration alone is insufficient.

Sources inspected:
https://github.com/torvalds/linux/blob/master/drivers/firewire/ohci.c
https://github.com/torvalds/linux/blob/master/drivers/firewire/core-card.c
https://github.com/torvalds/linux/blob/master/drivers/pci/pci.c
https://www.kernel.org/doc/html/latest/PCI/pci-error-recovery.html

Replaced the old privileged helper's bound-device reset with a one-shot sequence:
exclusive lock; refuse active FireWire descriptors/unidentified release waiters;
terminate only the requesting user's dvgrab release waiters; unbind the selected
OHCI; require completed detach and disappearance of waiters; select **only PM**;
reset the detached device; restore reset-method preferences; bind the driver;
require its local FireWire node and no release waiters. PCI bus resets and forced
module unloading remain excluded. On reset failure, binding is still attempted,
but success is not reported. A helper that has not exited prevents another attempt.
The helper does not exclude an unrelated application opening FireWire after the
preflight; all other FireWire applications must remain stopped during testing.

Default invocation is inspection-only:

```sh
python3 scripts/recover-firewire.py 0000:06:00.0
```

An explicitly authorized, supervised test after stopping playback and capture is:

```sh
pkexec /usr/bin/python3 scripts/recover-firewire.py 0000:06:00.0 --restart
```

Only the inspection was run on the real controller. The user reported an ongoing
capture/playback, so no live restart was attempted. Automated tests use temporary
fake sysfs/procfs trees. No automatic recovery trigger was enabled, and the dormant
GUI completion handler no longer automatically retries capture after helper
success. Success means **controller initialized**, not verified camera control,
healthy DMA, or complete DV reception. Those must be tested before enabling an
unattended recovery policy. A timed-out kernel unbind can still remain blocked.

## November 8 supervised hardware test

At the user's explicit request, performed the prepared isolated PM reset on
0000:06:00.0. Before the test, host process inspection found the application
(PID 2390) but **no dvgrab process**. The helper exited successfully. Kernel
journal timestamps (CET):

- 10:52:46: firewire_ohci removed and added again as card 1.
- 10:52:47: local fw0 created.
- 10:52:50: camera fw1 recreated with the original GUID 000085000014cad9.

The first STOP query was unconfirmed; native camera status was 0x0c20c160
(`Loading Medium`), and the camera timecode request failed. The user confirmed
that tape/mode had not yet been ready and was being set up. A later transport
worker confirmed STOP (0x0c20c460), but still could not obtain a camera timecode.

A bounded dvgrab trial requested five seconds of raw DV into a new temporary
folder, using the application's broadcast selection (`-card 0 -channel 63`).
No recorded data arrived within the 25-second wait. SIGINT stopped dvgrab cleanly;
it exited 1 with `0 frames` / `Error: no DV`. The journal contains **40 new
IO_PAGE_FAULT entries** from 10:58:09 through 10:58:25, addresses 0xffeeb000 and
0xfff64000. Logs are `/tmp/minidv-reset-test.log`,
`/tmp/minidv-reset-kernel.log`, and
`/tmp/minidv-reception-test-pp5mdiyq/capture.log` on this machine.

Thus detach/reset/probe and camera rediscovery were actually demonstrated, but
restored DV reception was **not** demonstrated. The tape's recorded position
still needs confirmation; do not attribute zero frames to the controller alone.
The new DMA faults independently show that this reset did not prevent their
recurrence. This was not a test of recovery from an already blocked D-state task.

Added an isolated, currently unwired `--recover-transport GUID [DV_FILE]` worker
for STOP verification and timecode-guided rewind. It reads a consensus timecode
from the last complete saved DV frame, targets three minutes earlier (clamped
at tape start), and verifies rewind progress and final STOP/position. It refuses
missing/conflicting timecodes and unconfirmed STOP. This is preparation for a
recovery state machine, not an enabled automatic capture/restart/merge loop.
The worker must be externally supervised with a timeout like other FireWire
helpers; Python deadlines cannot interrupt a blocked kernel call. It was used
only for STOP/status on the actual camera; no physical rewind was attempted.

An offline check of the saved max-010 frame finds matching DV subcode packs for
00:09:40:20, despite ffprobe rejecting its timecode flags. This is not evidence
that the camera supports matching position queries during rewind; those still
need a hardware test before the routine can be enabled for unattended use.


## Follow-up: reception and automatic recovery implementation

The earlier statements above describe intermediate test stages, not the final
implementation. After the user rewound the cassette, a second five-second test
received 125 PAL frames (18,000,000 bytes) and dvgrab exited cleanly. The recording
is `/tmp/minidv-reception-test-gzybbd8u/test001.dv`. Full FFmpeg decoding reported
numerous damaged-block errors, and new kernel DMA faults occurred around
11:04:47–48. Reception after reset is demonstrated; healthy DMA is not.

The subsequent camera STOP query succeeded with timecode 00:34:52:18. A physical
rewind test targeting three minutes before the last saved frame failed because
STOP could not be confirmed. That version did not log which STOP stage failed,
so neither successful rewind nor absence of tape movement can be inferred.
A separate later status query confirmed STOP (0x0c20c460), with unavailable
timecode. The revised worker logs stages and permits 15 seconds for STOP;
its complete rewind/resume path has not yet passed a hardware test.

Automatic recovery is now connected to capture stalls and serious controller
faults. The opt-in recording option defaults on for new recordings, with at most
two attempts per job. Controller restart must succeed, the old capture process
must exit, and the camera must confirm STOP and a verifiable rewind position
before capture resumes. New serious kernel faults, missing/ambiguous timecode,
non-progressing rewind, and worker deadlines abort the sequence. No timed blind
rewind or forced module unload is performed. Original and resumed DV segments
are joined by an isolated background process with transactional replacement;
source footage remains available until successful commit. Duplicate footage is
intentionally retained.

The optional root-owned fixed-target systemd service permits only the configured
active local user to start this specific service through polkit. It runs the
same reviewed helper with a 45-second service deadline. A pending marker blocks
further capture/recovery if termination leaves controller state uncertain.
Cancellation suppresses continuation but lets an already running controller
restart complete its rebind. No service is enabled at boot.

Validation: 142 automated tests and an isolated offscreen GUI smoke test passed.
These cover simulated recovery stages, cancellation, process timeouts, reset
refusals, timecode validation and transactional/background merge. They do not
establish recovery from a real kernel D-state hang. Persistent DMA and decoding
errors remain unresolved; this implementation must not be described as a cure
for the underlying controller/kernel/IOMMU problem.


The fixed-target service was installed and tested on the real host. Its first
start failed before executing the helper (systemd STDOUT setup could not create
the nested log path). The corrected unit logs directly to
`/run/minidv-firewire-recovery.log`. A subsequent
`systemctl --no-ask-password start minidv-firewire-recover.service` succeeded:
detach, isolated PM reset, bind and initialization checks all passed. This also
confirmed the narrowly scoped passwordless start authorization in this session.
The following camera query confirmed STOP (0x0c20c460), but timecode remained
unavailable, so rewind/resume was not attempted. The updated GUI was launched.
All 142 tests passed again after the log-path correction. The service is static,
not enabled at boot. No actual D-state hang was induced for this test.
