# FireWire stability and recovery

## Failure handling

A FireWire kernel or DMA fault can interrupt capture and leave a process blocked
inside the kernel. Application timeouts cannot guarantee that such a process
exits. A controller reset can help, but is not a cure for hardware, kernel or
IOMMU faults. Avoid repeated resets of an unresponsive device.

Historical kernel errors do not block a new capture. Live DMA page faults are
reported as warnings; explicit stalled DMA contexts or controller-access failures
stop capture. Kernel-log monitoring must be available. Signal loss warns after
10 seconds and requests a stop after 60 seconds; silence is not proof of tape end.
Original recordings are retained on failure.

## Optional automatic recovery

The recovery option allows at most two attempts per recording:

1. Stop capture and check for other FireWire users.
2. Detach the OHCI driver, perform an isolated PCI power-management reset, and
   bind the driver again. Shared PCI bus resets and forced module unloads are refused.
3. Wait for the old capture process to exit and the same camera to reconnect.
4. Confirm camera STOP and obtain a valid timecode. Rewind to three minutes before
   the last complete saved frame, checking progress and final STOP/position.
5. Resume into a separate DV segment, then join segments in a background process.
   Overlap is preserved; source segments remain until transactional replacement succeeds.

Missing or ambiguous timecode, unconfirmed STOP, new serious controller faults,
non-progressing rewind and helper timeouts abort recovery. There is no blind
rewind fallback. Stop playback manually if recovery fails.

Recovery currently requires exactly one OHCI controller, an available isolated
`pm` reset, and sufficient access to inspect processes. Other active FireWire
clients prevent reset. A pending restart marker prevents overlapping attempts
when a terminated helper may have left the controller in an uncertain state.
Cancellation suppresses automatic continuation but allows an in-flight reset to
finish rebinding the driver.

## Installation and portability

The application uses Linux FireWire, sysfs, systemd journal access and AV/C
libraries. It does not contain a fixed camera GUID, username or PCI address.
For source installations on a supported desktop, install the optional service:

```sh
pkexec /usr/bin/python3 scripts/install-recovery-service.py
```

The installer detects the single OHCI controller and the requesting user.
Explicit `--address PCI_ADDRESS --owner USER_ID` overrides are available.
The resulting machine-specific configuration is stored under `/usr/local`,
not in the repository. The root-owned service only allows its configured active
local user to start recovery of that controller. It is not enabled at boot.

Ubuntu 24.04 ships [polkit 124](https://packages.ubuntu.com/noble/polkitd),
which supports the [JavaScript rule backend](https://www.freedesktop.org/software/polkit/docs/0.106/polkit.8.html). Older systems with
polkit 0.105, including Ubuntu 22.04, cannot use this narrowly scoped rule;
the installer refuses that configuration. Capture remains available, and reset
uses administrator authorization instead of an unattended service. Do not replace
the rule with broad passwordless systemd permissions. A desktop authentication
agent and readable kernel journal are required. No kernel command-line or IOMMU
settings are changed by installation.

## Validation limits

Automated tests cover simulated reset failures, process retention, cancellation,
timecode validation and transactional/background merge. CI runs tests and GUI
smoke checks on Ubuntu; these do not exercise physical FireWire hardware.

A hardware trial demonstrated detach/reset/bind, camera rediscovery, confirmed
STOP and a short DV recording. DMA and decoding errors recurred. The complete
rewind/resume sequence and recovery from a real kernel-blocked capture have not
been demonstrated. These results do not establish reliable unattended capture.
Personal recording logs, device identifiers and machine inventories are not
included in this repository.
