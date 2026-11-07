#!/usr/bin/env python3
"""Small local Tk UI for the disposable libvirt sandbox controller."""

from __future__ import annotations

import json
import pathlib
import queue
import subprocess
import sys
import threading

import sandboxctl


def load_session_rows(evidence_dir: pathlib.Path) -> list[tuple[str, str]]:
    """Return only session records with a valid id and matching VM name."""
    rows: list[tuple[str, str]] = []
    if not evidence_dir.is_dir():
        return rows
    for metadata_path in sorted(evidence_dir.glob("*/session.json")):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            sid = metadata["session_id"]
            vm_name = metadata["vm_name"]
            if sandboxctl.SESSION_RE.fullmatch(sid) and vm_name == f"win11-{sid}":
                rows.append((sid, vm_name))
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
    return rows


class SandboxUi:
    def __init__(self, root, config_path: pathlib.Path):
        global tk, messagebox, ttk
        import tkinter as tk
        from tkinter import messagebox, ttk

        self.root = root
        self.config_path = config_path.resolve()
        self.cfg = sandboxctl.load_config(self.config_path)
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.rows: list[tuple[str, str]] = []

        root.title("KVM Sandbox")
        root.geometry("820x560")
        root.minsize(700, 460)

        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="KVM Sandbox", font=("TkDefaultFont", 18, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text="Disposable Windows VM control · vTPM 2.0 · UEFI Secure Boot · no host sharing",
        ).pack(anchor="w", pady=(2, 14))

        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(0, 12))
        self._button(actions, "Initialize", self._start("init")).pack(side="left", padx=(0, 6))
        self._button(actions, "Create base VM", self._start("base-install")).pack(side="left", padx=6)
        self._button(actions, "Seal base", self._start("base-seal")).pack(side="left", padx=6)
        self._button(actions, "Create VM", self._start("session-start", "--sample", "ui-created")).pack(side="left", padx=6)
        self._button(actions, "Stop selected", self.stop_selected).pack(side="left", padx=6)
        self._button(actions, "Destroy selected", self.destroy_selected).pack(side="left", padx=6)
        self._button(actions, "Refresh", self.refresh).pack(side="right")

        body = ttk.Panedwindow(frame, orient="horizontal")
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body, padding=(0, 0, 10, 0))
        right = ttk.Frame(body, padding=(10, 0, 0, 0))
        body.add(left, weight=1)
        body.add(right, weight=2)

        ttk.Label(left, text="Disposable VMs", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        self.sessions = tk.Listbox(left, exportselection=False, activestyle="dotbox")
        self.sessions.pack(fill="both", expand=True, pady=(6, 0))
        self.sessions.bind("<<ListboxSelect>>", self.show_selected)

        ttk.Label(right, text="Selected VM", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        self.selected_var = tk.StringVar(value="None")
        ttk.Label(right, textvariable=self.selected_var).pack(anchor="w", pady=(6, 12))
        ttk.Label(right, text="Baseline carried by the sealed image", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        baseline = self.cfg.get("baseline", {}).get("items", [])
        baseline_text = "\n".join(f"• {item}" for item in baseline) or "Configure [baseline].items in config.toml"
        ttk.Label(right, text=baseline_text, justify="left").pack(anchor="w", pady=(6, 12))
        ttk.Label(right, text="Activity", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        self.output = tk.Text(right, height=14, wrap="word", state="disabled")
        self.output.pack(fill="both", expand=True, pady=(6, 0))

        self.status = tk.StringVar(value="Ready")
        ttk.Label(frame, textvariable=self.status, relief="sunken", anchor="w").pack(fill="x", pady=(12, 0))
        self.refresh()
        self.root.after(150, self._drain_events)

    @staticmethod
    def _button(parent: ttk.Frame, label: str, command):
        return ttk.Button(parent, text=label, command=command)

    def _start(self, *args: str):
        return lambda: self.run_action(*args)

    def append_output(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.insert("end", text.rstrip() + "\n\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def run_action(self, *args: str) -> None:
        self.status.set(f"Running: {' '.join(args)}")
        self.append_output(f"> {' '.join(args)}")

        def worker() -> None:
            command = [sys.executable, str(pathlib.Path(sandboxctl.__file__).resolve()),
                       "--config", str(self.config_path), *args]
            try:
                result = subprocess.run(command, text=True, capture_output=True, check=False)
                output = (result.stdout + result.stderr).strip() or "(no output)"
                self.events.put(("done", f"exit {result.returncode}\n{output}"))
            except OSError as exc:
                self.events.put(("done", f"process error: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _drain_events(self) -> None:
        try:
            while True:
                kind, text = self.events.get_nowait()
                if kind == "done":
                    self.append_output(text)
                    self.status.set("Ready")
                    self.refresh()
        except queue.Empty:
            pass
        self.root.after(150, self._drain_events)

    def refresh(self) -> None:
        self.rows = load_session_rows(self.cfg["evidence_dir"])
        selected = self.sessions.curselection()
        selected_sid = self.rows[selected[0]][0] if selected and selected[0] < len(self.rows) else None
        self.sessions.delete(0, "end")
        for sid, vm_name in self.rows:
            self.sessions.insert("end", f"{sid}  ·  {vm_name}")
        if selected_sid:
            for index, (sid, _) in enumerate(self.rows):
                if sid == selected_sid:
                    self.sessions.selection_set(index)
                    break
        self.show_selected()

    def show_selected(self, _event=None) -> None:
        selection = self.sessions.curselection()
        self.selected_var.set(self.rows[selection[0]][0] if selection else "None")

    def selected_id(self) -> str | None:
        selection = self.sessions.curselection()
        return self.rows[selection[0]][0] if selection else None

    def stop_selected(self) -> None:
        sid = self.selected_id()
        if sid:
            self.run_action("session-stop", sid)
        else:
            self.status.set("Select a VM first")

    def destroy_selected(self) -> None:
        sid = self.selected_id()
        if not sid:
            self.status.set("Select a VM first")
            return
        if messagebox.askyesno("Destroy disposable VM", f"Destroy {sid}? Evidence stays on disk."):
            self.run_action("session-destroy", sid)


def main(config_path: pathlib.Path | None = None) -> int:
    import tkinter as tk

    config = config_path or (pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else sandboxctl.DEFAULT_CONFIG)
    root = tk.Tk()
    SandboxUi(root, config)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
