# Secure Windows 11 Malware Analysis Sandbox

This project creates a local, disposable Windows 11 x64 environment on QEMU/KVM + libvirt. It includes a small local Tk UI for creating, stopping, and destroying disposable VMs.

## Current status

The Linux control plane is implemented and can be exercised without a Windows ISO or root privileges. The Windows base template is **not ready yet**: Windows must be installed from an official Windows 11 x64 ISO, then the guest baseline must be prepared and sealed. Do not execute unknown samples before that point.

The controller uses:

- one immutable Windows base QCOW2 image;
- one QCOW2 overlay and one libvirt domain per analysis session;
- an isolated libvirt network with no forwarding to the LAN or Internet;
- UEFI/Secure Boot firmware and a virtual TPM 2.0;
- VirtIO disk/network devices, with no shared folders, clipboard, drag-and-drop, USB, or GPU passthrough;
- per-session runtime, evidence, and report directories;
- SHA-256 manifests, libvirt XML/configuration snapshots, packet capture when available, and a generated TXT report.

## Root-only installation

Run this in a terminal where sudo can ask for your password. It does not modify boot settings or unrelated VMs:

```bash
cd /home/maro/Documents/ChatGPT/vm
./install-host.sh
```

Log out and back in after the group change. If `pacman` reports a mirror or signature problem, stop and repair the host package database rather than disabling signature verification.

Verify:

```bash
./sandboxctl.py doctor
virsh -c qemu:///system list --all
```

Start the UI with:

```bash
./sandboxctl.py ui
```

The UI runs the same guarded CLI operations as the terminal: `Initialize`, `Create base VM`, `Seal base`, `Create VM`, `Stop selected`, and `Destroy selected`. Destroy keeps the evidence directory and removes only the selected disposable domain and overlay.

## Native C++ executable

Build the modern Qt Quick menu and its local login screen:

```bash
./build-linux.sh
./cpp/build/kvm-sandbox
```

On first launch, create the local operator account. Passwords are stored only as Argon2id hashes under the desktop user's application config directory. Later launches show the login screen. The C++ executable calls the same guarded `sandboxctl.py` controller; set `KVM_SANDBOX_ROOT` if the checkout is moved after compilation.

## ISO and base template

Supply an official, unmodified Windows 11 x64 ISO at `iso/Win11.iso`, or edit `config.toml`. Verify its SHA-256 against the publisher's release information before use. Then:

```bash
./sandboxctl.py init
./sandboxctl.py network-create
./sandboxctl.py base-install
```

`base-install` creates the installation VM and opens it through virt-manager/virt-viewer if available. Complete Windows setup interactively using a dedicated local test user. Never enter personal credentials or real browser/Discord sessions.

After Windows installation, install the reviewed guest baseline from local, licensed installers: the entries in `[baseline].items` in `config.toml` are the checklist shown in the UI. This is deliberately a one-time base-image step: every later VM is a QCOW2 overlay of that sealed image, so the installed programs and the reviewed game build are present without a guest agent, clipboard integration, shared folders, or drag-and-drop. Reboot and verify the guest. Then shut it down and run:

```bash
./sandboxctl.py base-seal
```

The sealed base image is immutable by policy. To update it, create a new versioned base image from a backup, update and verify it in a separate domain, then replace the configured base only after the old image is preserved.

## Disposable analysis sessions

```bash
./sandboxctl.py session-start --sample /path/to/harmless-test.exe
./sandboxctl.py session-status SESSION_ID
# Interact with the VM via virt-manager or virt-viewer; do not use shared clipboard/files.
./sandboxctl.py session-stop SESSION_ID
```

`session-stop` collects XML, domain stats, disk metadata, logs, hashes, and packet capture before powering off. It generates `reports/SESSION_ID.txt`. `session-destroy` removes only the session's overlay/domain after the evidence is preserved.

Unknown malware is intentionally out of scope for initial testing. Use the included harmless test generator and verify the entire lifecycle first:

```bash
python -m unittest discover -s tests -v
./sandboxctl.py self-test
```

## Isolation notes

The isolated network prevents guest packets from reaching the host LAN or Internet. This is safer, but it means live network behavior is not observed until a separately designed, explicitly approved controlled-network mode exists. The current implementation does not add that mode. The host still remains responsible for kernel/libvirt/QEMU vulnerabilities; keep the host patched and do not run the analysis controller as root except for the specific libvirt operations that require it.

The controller intentionally does not hide the hypervisor or fabricate host-product telemetry. It uses honest, stable per-VM UUIDs, vTPM 2.0, UEFI Secure Boot, and a consistent virtual hardware profile. Those controls provide isolation and repeatability; they are not an anti-detection or anti-cheat bypass.
