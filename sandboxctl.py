#!/usr/bin/env python3
"""Small, defensive controller for disposable Windows 11 libvirt sessions."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import signal
import shutil
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape


PROJECT = pathlib.Path(__file__).resolve().parent
DEFAULT_CONFIG = PROJECT / "config.toml"
SESSION_RE = re.compile(r"^s-\d{8}T\d{6}Z-[0-9a-f]{8}$")


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def build_session_id() -> str:
    stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
    return f"s-{stamp}-{uuid.uuid4().hex[:8]}"


def safe_child(root: pathlib.Path, child: pathlib.Path) -> pathlib.Path:
    root = root.resolve()
    child = child.resolve()
    if child == root or root not in child.parents:
        raise ValueError(f"refusing path outside sandbox root: {child}")
    return child


def run(args: list[str], *, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, text=True, capture_output=capture)


def require_tool(name: str) -> str | None:
    return shutil.which(name)


def tkinter_available() -> bool:
    try:
        import tkinter  # noqa: F401
    except ImportError:
        return False
    return True


def load_config(path: pathlib.Path) -> dict:
    import tomllib

    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    root = pathlib.Path(raw.get("project_root", "."))
    if not root.is_absolute():
        root = path.parent / root
    raw["project_root"] = root.resolve()
    for key in ("iso_path", "base_dir", "session_dir", "evidence_dir", "report_dir", "state_dir"):
        value = pathlib.Path(raw[key])
        raw[key] = (root / value).resolve() if not value.is_absolute() else value.resolve()
    return raw


def ensure_layout(cfg: dict) -> None:
    for key in ("base_dir", "session_dir", "evidence_dir", "report_dir", "state_dir"):
        cfg[key].mkdir(parents=True, exist_ok=True)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_network_xml(net: dict) -> str:
    return f"""<network>
  <name>{net['name']}</name>
  <bridge name='{net['bridge']}' stp='on' delay='0'/>
  <forward mode='none'/>
  <ip address='{net['ipv4'].split('/')[0]}' prefix='24'>
    <dhcp><range start='{net['dhcp_start']}' end='{net['dhcp_end']}'/></dhcp>
  </ip>
</network>
"""


def build_domain_xml(*, name: str, memory_mib: int, vcpus: int, machine: str,
                     overlay: str, nvram: str, network: str,
                     domain_uuid: str | None = None) -> str:
    uuid_xml = f"  <uuid>{escape(domain_uuid)}</uuid>\n" if domain_uuid else ""
    return f"""<domain type='kvm'>
  <name>{name}</name>
{uuid_xml}  <memory unit='MiB'>{memory_mib}</memory>
  <currentMemory unit='MiB'>{memory_mib}</currentMemory>
  <vcpu placement='static'>{vcpus}</vcpu>
  <os firmware='efi'>
    <type arch='x86_64' machine='{machine}'>hvm</type>
    <loader readonly='yes' secure='yes'>/usr/share/edk2/x64/OVMF_CODE.secboot.4m.fd</loader>
    <nvram>{nvram}</nvram>
    <boot dev='hd'/>
  </os>
  <features><acpi/><apic/><vmport state='off'/></features>
  <cpu mode='host-passthrough' check='none'/>
  <clock offset='localtime'/>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>destroy</on_crash>
  <devices>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='{overlay}'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <interface type='network'>
      <source network='{network}'/>
      <model type='virtio'/>
    </interface>
    <controller type='usb' model='qemu-xhci'/>
    <video><model type='virtio' heads='1' primary='yes'/></video>
    <graphics type='spice' autoport='yes'/>
    <console type='pty'/>
    <tpm model='tpm-crb'><backend type='emulator' version='2.0'/></tpm>
    <memballoon model='none'/>
  </devices>
</domain>
"""


def virsh(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(["virsh", "-c", "qemu:///system", *args], check=check)


def cmd_doctor(cfg: dict, _args: argparse.Namespace) -> int:
    checks = ["qemu-system-x86_64", "qemu-img", "virsh", "virt-install", "swtpm"]
    print(f"project: {cfg['project_root']}")
    print(f"kvm: {'yes' if pathlib.Path('/dev/kvm').exists() else 'no'}")
    for item in checks:
        print(f"{item}: {'found' if require_tool(item) else 'MISSING'}")
    print(f"tkinter: {'found' if tkinter_available() else 'MISSING'}")
    try:
        result = virsh("version")
        print("libvirt: reachable")
        print(result.stdout.splitlines()[0] if result.stdout else "")
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"libvirt: unavailable ({exc})")
    free = shutil.disk_usage(cfg["project_root"])
    print(f"free_bytes: {free.free}")
    return 0


def cmd_init(cfg: dict, _args: argparse.Namespace) -> int:
    ensure_layout(cfg)
    print(f"initialized: {cfg['project_root']}")
    if cfg["iso_path"].exists():
        print(f"iso_sha256: {sha256(cfg['iso_path'])}")
    else:
        print(f"ISO missing: {cfg['iso_path']}")
    return 0


def cmd_network_create(cfg: dict, _args: argparse.Namespace) -> int:
    xml_path = cfg["state_dir"] / f"{cfg['network']['name']}.xml"
    xml_path.write_text(build_network_xml(cfg["network"]), encoding="utf-8")
    try:
        virsh("net-info", cfg["network"]["name"])
        print("network already exists")
    except subprocess.CalledProcessError:
        virsh("net-define", str(xml_path))
        virsh("net-autostart", cfg["network"]["name"])
        virsh("net-start", cfg["network"]["name"])
        print("network created and started")
    return 0


def require_iso(cfg: dict) -> pathlib.Path:
    iso = cfg["iso_path"]
    if not iso.is_file():
        raise RuntimeError(f"official Windows 11 x64 ISO required at {iso}")
    return iso


def cmd_base_install(cfg: dict, args: argparse.Namespace) -> int:
    iso = require_iso(cfg)
    ensure_layout(cfg)
    base = cfg["base_dir"] / "win11-base-install.qcow2"
    if base.exists() and not args.reuse:
        raise RuntimeError(f"refusing to overwrite existing installer disk: {base}; use --reuse")
    if not base.exists():
        run(["qemu-img", "create", "-f", "qcow2", str(base), f"{cfg['vm']['disk_gib']}G"])
    name = cfg["vm"]["name"]
    cmd = ["virt-install", "--connect", "qemu:///system", "--name", name,
           "--memory", str(cfg["vm"]["memory_mib"]), "--vcpus", str(cfg["vm"]["vcpus"]),
           "--machine", cfg["vm"]["machine"], "--os-variant", "win11",
           "--disk", f"path={base},format=qcow2,bus=virtio",
           "--disk", f"path={iso},device=cdrom",
           "--network", f"network={cfg['network']['name']},model=virtio",
           "--boot", "uefi,loader_secure=yes",
           "--tpm", "backend.type=emulator,backend.version=2.0",
           "--graphics", "spice", "--noautoconsole"]
    run(cmd)
    print(f"installer VM created: {name}")
    print("Complete Windows setup interactively, install the reviewed baseline, then run base-seal.")
    return 0


def base_image(cfg: dict) -> pathlib.Path:
    path = cfg["base_dir"] / "win11-base.qcow2"
    if path.is_symlink() or not path.is_file() or cfg["base_dir"] not in path.resolve().parents:
        raise RuntimeError(f"sealed base image missing: {path}; complete installation and base-seal first")
    return path


def cmd_base_seal(cfg: dict, _args: argparse.Namespace) -> int:
    source = cfg["base_dir"] / "win11-base-install.qcow2"
    target = cfg["base_dir"] / "win11-base.qcow2"
    if not source.is_file():
        raise RuntimeError(f"installer disk missing: {source}")
    try:
        virsh("domstate", cfg["vm"]["name"])
        raise RuntimeError("stop and undefine the installer VM before sealing")
    except subprocess.CalledProcessError:
        pass
    if target.exists():
        raise RuntimeError(f"refusing to overwrite sealed base: {target}")
    shutil.copy2(source, target)
    target.chmod(0o444)
    print(f"sealed immutable base: {target}")
    print(f"sha256: {sha256(target)}")
    return 0


def session_paths(cfg: dict, sid: str) -> dict[str, pathlib.Path]:
    if not SESSION_RE.fullmatch(sid):
        raise ValueError("invalid session id")
    root = safe_child(cfg["session_dir"], cfg["session_dir"] / sid)
    return {"root": root, "runtime": root / "runtime", "evidence": safe_child(cfg["evidence_dir"], cfg["evidence_dir"] / sid),
            "report": safe_child(cfg["report_dir"], cfg["report_dir"] / sid)}


def cmd_session_start(cfg: dict, args: argparse.Namespace) -> int:
    base = base_image(cfg)
    ensure_layout(cfg)
    sid = build_session_id()
    paths = session_paths(cfg, sid)
    for key in ("root", "runtime", "evidence", "report"):
        paths[key].mkdir(parents=True, exist_ok=True)
    overlay = paths["runtime"] / "overlay.qcow2"
    nvram = paths["runtime"] / "nvram.fd"
    run(["qemu-img", "create", "-f", "qcow2", "-F", "qcow2", "-b", str(base), str(overlay)])
    run(["qemu-img", "info", "--backing-chain", str(overlay)], capture=True)
    vm_name = f"win11-{sid}"
    domain_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"local-kvm-sandbox:{sid}"))
    xml = build_domain_xml(name=vm_name, memory_mib=cfg["vm"]["memory_mib"], vcpus=cfg["vm"]["vcpus"],
                            machine=cfg["vm"]["machine"], overlay=str(overlay), nvram=str(nvram),
                            network=cfg["network"]["name"], domain_uuid=domain_uuid)
    xml_path = paths["evidence"] / "domain.xml"
    xml_path.write_text(xml, encoding="utf-8")
    metadata = {"session_id": sid, "vm_name": vm_name, "hardware_uuid": domain_uuid,
                "created_utc": now_utc().isoformat(),
                "overlay": str(overlay), "base_sha256": sha256(base), "sample": args.sample,
                "policy": {"network": "isolated-no-forward", "shared_folders": False, "clipboard": False,
                            "drag_and_drop": False, "usb_passthrough": False, "gpu_passthrough": False}}
    (paths["evidence"] / "session.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    virsh("define", str(xml_path))
    virsh("start", vm_name)
    if cfg["analysis"].get("capture_packets", False) and require_tool("tcpdump"):
        capture = paths["evidence"] / "network.pcap"
        proc = subprocess.Popen(["tcpdump", "-i", cfg["network"]["bridge"], "-n", "-U", "-w", str(capture)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        (paths["runtime"] / "tcpdump.pid").write_text(str(proc.pid) + "\n", encoding="utf-8")
    print(sid)
    print(f"VM: {vm_name}")
    print("Use virt-manager or virt-viewer for the interactive desktop.")
    return 0


def collect_session(cfg: dict, sid: str, *, stopped: str) -> pathlib.Path:
    paths = session_paths(cfg, sid)
    evidence = paths["evidence"]
    evidence.mkdir(parents=True, exist_ok=True)
    metadata_path = evidence / "session.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    vm_name = metadata.get("vm_name", f"win11-{sid}")
    if vm_name != f"win11-{sid}":
        raise RuntimeError("session metadata VM name does not match session id")
    for name, args in (("final-domain.xml", ["dumpxml", vm_name]), ("domstats.txt", ["domstats", vm_name]),
                       ("domblkinfo.txt", ["domblkinfo", vm_name, "--all"])):
        result = virsh(*args, check=False)
        (evidence / name).write_text((result.stdout or "") + (result.stderr or ""), encoding="utf-8")
    overlay = pathlib.Path(metadata.get("overlay", ""))
    if overlay.is_file():
        result = run(["qemu-img", "info", "--backing-chain", str(overlay)], check=False)
        (evidence / "overlay-info.txt").write_text((result.stdout or "") + (result.stderr or ""), encoding="utf-8")
    metadata.update({"stopped_utc": stopped, "evidence_sha256": {}})
    for file in sorted(evidence.rglob("*")):
        if file.is_file() and file.name != "session.json":
            metadata["evidence_sha256"][str(file.relative_to(evidence))] = sha256(file)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    report = paths["report"] / f"{sid}.txt"
    lines = ["Windows 11 Malware Analysis Sandbox Report", "=" * 44, f"session_id: {sid}",
             f"vm_name: {vm_name}", f"stopped_utc: {stopped}", f"base_sha256: {metadata.get('base_sha256', 'unknown')}",
             "", "Isolation policy:", json.dumps(metadata.get("policy", {}), indent=2), "",
             "Evidence files and SHA-256:"]
    lines.extend(f"- {name}: {digest}" for name, digest in metadata["evidence_sha256"].items())
    lines.extend(["", "Interpretation limits:",
                  "- This report records host-observable artifacts only.",
                  "- It does not prove that malware was safe or absent.",
                  "- The network was isolated with no forwarding."])
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def cmd_session_stop(cfg: dict, args: argparse.Namespace) -> int:
    paths = session_paths(cfg, args.session_id)
    pid_path = paths["runtime"] / "tcpdump.pid"
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
            os.kill(pid, signal.SIGINT)
        except (ValueError, ProcessLookupError, PermissionError):
            pass
        pid_path.unlink(missing_ok=True)
    metadata = json.loads((paths["evidence"] / "session.json").read_text(encoding="utf-8"))
    vm_name = metadata["vm_name"]
    if vm_name != f"win11-{args.session_id}":
        raise RuntimeError("session metadata VM name does not match session id")
    virsh("shutdown", vm_name, check=False)
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        state = virsh("domstate", vm_name, check=False).stdout.lower()
        if "shut off" in state or "not found" in state:
            break
        time.sleep(2)
    report = collect_session(cfg, args.session_id, stopped=now_utc().isoformat())
    print(f"report: {report}")
    return 0


def cmd_session_status(cfg: dict, args: argparse.Namespace) -> int:
    paths = session_paths(cfg, args.session_id)
    metadata_path = paths["evidence"] / "session.json"
    if not metadata_path.exists():
        raise RuntimeError("session metadata missing")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    result = virsh("domstate", metadata["vm_name"], check=False)
    print(f"session_id: {args.session_id}")
    print(f"vm_name: {metadata['vm_name']}")
    print(f"state: {(result.stdout or result.stderr).strip()}")
    print(f"evidence: {paths['evidence']}")
    return 0


def cmd_session_destroy(cfg: dict, args: argparse.Namespace) -> int:
    paths = session_paths(cfg, args.session_id)
    metadata_path = paths["evidence"] / "session.json"
    if not metadata_path.exists():
        raise RuntimeError("session evidence metadata missing; refusing destruction")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    vm_name = metadata["vm_name"]
    if vm_name != f"win11-{args.session_id}":
        raise RuntimeError("session metadata VM name does not match session id")
    virsh("destroy", vm_name, check=False)
    virsh("undefine", vm_name, "--nvram", check=False)
    overlay = pathlib.Path(metadata["overlay"])
    if overlay.is_file() and not overlay.is_symlink() and paths["runtime"] in overlay.resolve().parents:
        overlay.unlink()
    print(f"destroyed disposable VM and overlay for {args.session_id}; evidence retained at {paths['evidence']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    sub.add_parser("init")
    sub.add_parser("network-create")
    base_install = sub.add_parser("base-install")
    base_install.add_argument("--reuse", action="store_true")
    sub.add_parser("base-seal")
    start = sub.add_parser("session-start")
    start.add_argument("--sample", required=True)
    stop = sub.add_parser("session-stop")
    stop.add_argument("session_id")
    stop.add_argument("--timeout", type=int, default=120)
    status = sub.add_parser("session-status")
    status.add_argument("session_id")
    destroy = sub.add_parser("session-destroy")
    destroy.add_argument("session_id")
    sub.add_parser("self-test")
    sub.add_parser("ui")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    if args.command == "self-test":
        import unittest
        return 0 if unittest.main(module=None, argv=[sys.argv[0], "discover", "-s", "tests", "-v"], exit=False).result.wasSuccessful() else 1
    if args.command == "ui":
        from ui import main as ui_main
        return ui_main(args.config)
    try:
        ensure_layout(cfg)
        return {"doctor": cmd_doctor, "init": cmd_init, "network-create": cmd_network_create,
                "base-install": cmd_base_install, "base-seal": cmd_base_seal,
                "session-start": cmd_session_start, "session-stop": cmd_session_stop,
                "session-status": cmd_session_status,
                "session-destroy": cmd_session_destroy}[args.command](cfg, args)
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
