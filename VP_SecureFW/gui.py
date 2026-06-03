# -*- coding: utf-8 -*-
"""
gui.py  –  VP SecureFW Test Framework  |  Tkinter GUI

Provides a user-friendly interface to runtestplan.py without modifying any
existing project files.

Launch:
    python gui.py
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
TESTPLANS_DIR = ROOT / "testplans"
PRODUCTCONFIGS_DIR = ROOT / "productconfigs"
REPORTS_DIR = ROOT / "reports"

# ---------------------------------------------------------------------------
# Colours / Fonts  (centralised for easy theming)
# ---------------------------------------------------------------------------
CLR = {
    "bg":          "#F5F5F5",
    "panel_bg":    "#FFFFFF",
    "accent":      "#1565C0",      # dark-blue accent
    "accent_hover":"#1976D2",
    "run_btn":     "#2E7D32",      # green
    "stop_btn":    "#C62828",      # red
    "hdr_bg":      "#1565C0",
    "hdr_fg":      "#FFFFFF",
    "border":      "#BDBDBD",
    "pass":        "#1B5E20",
    "fail":        "#B71C1C",
    "warn":        "#E65100",
    "info":        "#0D47A1",
    "console_bg":  "#1E1E1E",
    "console_fg":  "#D4D4D4",
    "status_bg":   "#E3F2FD",
}

FONT_FAMILY = "Segoe UI"
FONT = (FONT_FAMILY, 10)
FONT_BOLD = (FONT_FAMILY, 10, "bold")
FONT_LARGE = (FONT_FAMILY, 12, "bold")
FONT_MONO = ("Consolas", 9)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def list_testplans() -> list[str]:
    """Return sorted list of YAML file names in testplans/ directory."""
    if not TESTPLANS_DIR.exists():
        return []
    return sorted(p.name for p in TESTPLANS_DIR.glob("*.yaml"))


def list_reports() -> list[str]:
    """Return sorted list of report xlsx files (newest first)."""
    if not REPORTS_DIR.exists():
        return []
    return sorted(
        (p.name for p in REPORTS_DIR.glob("*.xlsx")),
        reverse=True,
    )


def list_product_configs() -> list[str]:
    """Return sorted list of product config stems (without .json)."""
    if not PRODUCTCONFIGS_DIR.exists():
        return []
    return sorted(p.stem for p in PRODUCTCONFIGS_DIR.glob("*.json"))


def get_relay_settings() -> tuple[str, int]:
    """Parse COM port and baud from relaycontrol/relayon.py."""
    script = ROOT / "relaycontrol" / "relayon.py"
    try:
        content = script.read_text(encoding="utf-8")
        m = re.search(r"serial\.Serial\('(COM\d+)'\s*,\s*(\d+)\)", content)
        if m:
            return m.group(1), int(m.group(2))
    except Exception:
        pass
    return "COM10", 9600


def set_relay_settings(com_port: str, baud: int):
    """Rewrite both relay scripts with updated COM port and baud."""
    for fname, data_byte in [("relayon.py", "b'1'"), ("relayoff.py", "b'0'")]:
        script = ROOT / "relaycontrol" / fname
        content = f"import serial\n\nserial.Serial('{com_port}',{baud}).write({data_byte})\n"
        script.write_text(content, encoding="utf-8")


def load_testplan_ids(yaml_name: str) -> list[str]:
    """Parse a testplan YAML and return the list of test IDs."""
    try:
        import yaml  # type: ignore
        path = TESTPLANS_DIR / yaml_name
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return [str(t.get("id", "")) for t in data.get("tests", []) if t.get("id")]
    except Exception:
        return []


def load_product_config_for_plan(yaml_name: str) -> dict | None:
    """Try to load the product config JSON for the given testplan filename."""
    try:
        import yaml  # type: ignore
        path = TESTPLANS_DIR / yaml_name
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        product_name = data.get("product_name") or data.get("product")
        if not product_name:
            stem = Path(yaml_name).stem
            candidate = stem.split("_")[0]
            cfg_path = PRODUCTCONFIGS_DIR / f"{candidate}.json"
            if cfg_path.exists():
                product_name = candidate

        if product_name:
            cfg_path = PRODUCTCONFIGS_DIR / f"{product_name}.json"
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as f:
                    return json.load(f)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# TestPlan YAML helpers
# ---------------------------------------------------------------------------

def _ystr(s: str) -> str:
    """Serialize a plain YAML scalar — adds double-quotes when needed."""
    if s is None:
        return ''
    s = str(s)
    if not s:
        return '""'
    if re.search(r'[:#\[\]{},!@&*?]', s) or s[0] in ('-', '|', '>', '!', '%'):
        return json.dumps(s)
    return s


def _ypath(p: str) -> str:
    """Always double-quote file paths for YAML."""
    if not p:
        return ''
    return json.dumps(str(p))


def _yflag(v) -> str:
    """Serialize a flag value: plain int stays unquoted, hex strings get quoted."""
    if v is None:
        return ''
    s = str(v).strip()
    if not s or s in ('None', 'null'):
        return ''
    if re.match(r'^0[xX][0-9A-Fa-f]+', s):
        return f'"{s}"'
    try:
        return str(int(s))
    except ValueError:
        return f'"{s}"'


def _flag_to_native(s: str):
    """Convert a flag string from the UI to Python int or string."""
    s = str(s).strip()
    if re.match(r'^0[xX][0-9A-Fa-f]+', s):
        return s          # Keep hex as str
    try:
        return int(s)     # Plain integer
    except ValueError:
        return s          # Keep as str


def serialize_testplan(data: dict) -> str:
    """Serialize a testplan dict to a clean, human-readable YAML string."""
    lines: list[str] = []
    lines.append(f'name: {_ystr(data.get("name", "Test Plan"))}')
    if data.get("product_name"):
        lines.append(f'product_name: {data["product_name"]}')
    lines.append('')
    lines.append('tests:')
    for t in data.get("tests", []):
        lines.append(f'  - id: {t.get("id", "")}')
        if t.get("scenario"):
            lines.append(f'    scenario: {_ystr(t["scenario"])}')

        for suffix in ("", "_main", "_ble", "_wifi"):
            key = f"delivery_method{suffix}"
            if t.get(key):
                lines.append(f'    {key}: {t[key]}')

        if t.get("reset_type"):
            lines.append(f'    reset_type: {t["reset_type"]}')

        if t.get("board_number") is not None:
            lines.append(f'    board_number: {t["board_number"]}')

        srec = (t.get("flash_srec") or "").strip()
        lines.append(f'    flash_srec: {_ypath(srec) if srec else ""}')

        for suffix in ("", "_ble", "_wifi"):
            key = f"update_pkg{suffix}"
            val = (t.get(key) or "").strip()
            if val:
                lines.append(f'    {key}: {_ypath(val)}')

        for suffix in ("", "_ble", "_wifi"):
            key = f"expected_flags_after_reset{suffix}"
            flags = t.get(key)
            if flags:
                lines.append(f'    {key}:')
                for fname, fval in flags.items():
                    fv = _yflag(fval)
                    if fv:
                        lines.append(f'      {fname}: {fv}')

        lines.append('')
    return '\n'.join(lines)


def load_testplan_full(yaml_name: str) -> dict:
    """Load a complete testplan YAML file and return as a dict."""
    try:
        import yaml as _yaml
        p = TESTPLANS_DIR / yaml_name
        with open(p, 'r', encoding='utf-8') as f:
            return _yaml.safe_load(f) or {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Test Plan Editor Dialog
# ---------------------------------------------------------------------------

class TestPlanDialog(tk.Toplevel):
    """Create or edit a YAML test plan file with a full graphical editor."""

    DELIVERY_METHODS = ["SelfProgrammer", "JFlash", "InstallOnly"]
    RESET_TYPES      = ["install", "reset"]
    ERROR_CODES      = ["0xAF", "0x100", "0x104", "0x109", "0x600", "0x601",
                        "0x20A0", "0x2060", "0x4A0", "0x0"]

    def __init__(self, parent: "App", mode: str = "new", yaml_name: str | None = None):
        super().__init__(parent)
        self._parent = parent
        self._mode   = mode
        self._orig_yaml_name = yaml_name

        self.title("New Test Plan" if mode == "new" else f"Edit Test Plan — {yaml_name}")
        self.geometry("980x700")
        self.minsize(860, 600)
        self.configure(bg=CLR["bg"])
        self.grab_set()
        self.transient(parent)

        # Plan-level StringVars
        self.sv_plan_name    = tk.StringVar(value="My New Test Plan")
        self.sv_product_name = tk.StringVar()
        self.sv_filename     = tk.StringVar(value="NewPlan.yaml")

        # Per-test StringVars (reused across tests via load/commit)
        self._sv: dict[str, tk.Variable] = {}
        self._sv_ble_en  = tk.BooleanVar(value=False)
        self._sv_wifi_en = tk.BooleanVar(value=False)
        self._init_test_vars()

        # Internal test list and selection
        self._tests: list[dict] = []
        self._current_idx: int = -1

        # Load existing plan or start blank
        if mode == "edit" and yaml_name:
            data = load_testplan_full(yaml_name)
            self.sv_plan_name.set(data.get("name", ""))
            self.sv_product_name.set(data.get("product_name") or "")
            self.sv_filename.set(yaml_name)
            self._tests = [dict(t) for t in data.get("tests", [])]

        if not self._tests:
            self._tests = [self._blank_test()]

        self._build_ui()

        # Auto-generate filename from plan name (new mode only)
        if mode == "new":
            self.sv_plan_name.trace_add("write", self._auto_filename)

        self._rebuild_list()
        self._select_test(0)
        self.focus_set()

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _init_test_vars(self):
        for k in [
            "t_id", "t_scenario", "t_delivery", "t_reset_type", "t_board_number",
            "t_flash_srec", "t_update_pkg",
            "t_delivery_ble",  "t_update_pkg_ble",
            "t_delivery_wifi", "t_update_pkg_wifi",
            "f_req",  "f_frez",  "f_actbin",  "f_rollbk",  "f_errcode",
            "fb_req", "fb_frez", "fb_actbin", "fb_rollbk", "fb_errcode",
            "fw_req", "fw_frez", "fw_actbin", "fw_rollbk", "fw_errcode",
        ]:
            self._sv[k] = tk.StringVar()

    @staticmethod
    def _blank_test() -> dict:
        return {
            "id": "Test 1",
            "scenario": "",
            "delivery_method": "SelfProgrammer",
            "reset_type": "install",
            "flash_srec": "",
            "expected_flags_after_reset": {
                "FwUpdate_req": 0, "FwUpdate_frez": 1,
                "FwUpdate_actbin": 0, "FwUpdate_rollbk": 255,
                "SelfProg Error Code": "0xAF",
            },
        }

    def _auto_filename(self, *_):
        name = self.sv_plan_name.get().strip()
        slug = re.sub(r'[^A-Za-z0-9]+', '_', name).strip('_')
        if slug:
            self.sv_filename.set(f"{slug}.yaml")

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=CLR["hdr_bg"], height=46)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)
        icon = "✦  New Test Plan" if self._mode == "new" else "✎  Edit Test Plan"
        tk.Label(hdr, text=f"  {icon}", bg=CLR["hdr_bg"], fg=CLR["hdr_fg"],
                 font=(FONT_FAMILY, 12, "bold")).pack(side="left", padx=14, pady=8)
        if self._mode == "edit" and self._orig_yaml_name:
            tk.Label(hdr, text=self._orig_yaml_name, bg=CLR["hdr_bg"],
                     fg="#90CAF9", font=(FONT_FAMILY, 9)).pack(side="right", padx=14)

        # Plan info bar
        self._build_plan_info_bar()

        # Main split: test list (left) | editor (right)
        main = tk.Frame(self, bg=CLR["bg"])
        main.pack(fill="both", expand=True, padx=12, pady=(8, 0))
        self._build_test_list(main)
        self._build_test_editor(main)

        # Footer
        footer = tk.Frame(self, bg=CLR["bg"])
        footer.pack(fill="x", padx=12, pady=8)
        lbl = "Save & Create" if self._mode == "new" else "Save Changes"
        ttk.Button(footer, text=f"💾  {lbl}", style="Run.TButton",
                   command=self._save).pack(side="left", padx=(0, 8))
        ttk.Button(footer, text="Cancel", style="Accent.TButton",
                   command=self.destroy).pack(side="left")
        tk.Label(footer,
                 text="Saved to testplans/  •  Immediately available in the main window.",
                 bg=CLR["bg"], fg="#9E9E9E", font=(FONT_FAMILY, 8)).pack(side="right")

    def _build_plan_info_bar(self):
        bar = tk.Frame(self, bg=CLR["panel_bg"], bd=1, relief="solid",
                       highlightbackground=CLR["border"], highlightthickness=1)
        bar.pack(fill="x", padx=12, pady=(8, 0))
        inner = tk.Frame(bar, bg=CLR["panel_bg"])
        inner.pack(fill="x", padx=10, pady=8)

        tk.Label(inner, text="Plan Name:", bg=CLR["panel_bg"],
                 font=FONT_BOLD, width=11, anchor="w").grid(row=0, column=0, sticky="w")
        tk.Entry(inner, textvariable=self.sv_plan_name, font=FONT, width=36,
                 relief="solid", bd=1).grid(row=0, column=1, sticky="w", padx=(4, 16))

        tk.Label(inner, text="Product:", bg=CLR["panel_bg"],
                 font=FONT_BOLD, width=9, anchor="w").grid(row=0, column=2, sticky="w")
        ttk.Combobox(inner, textvariable=self.sv_product_name,
                     values=[""] + list_product_configs(),
                     font=FONT, width=16).grid(row=0, column=3, sticky="w", padx=(4, 16))

        tk.Label(inner, text="Filename:", bg=CLR["panel_bg"],
                 font=FONT_BOLD, width=9, anchor="w").grid(row=0, column=4, sticky="w")
        state = "readonly" if self._mode == "edit" else "normal"
        tk.Entry(inner, textvariable=self.sv_filename, font=FONT, width=22,
                 relief="solid", bd=1, state=state).grid(row=0, column=5, sticky="w", padx=4)

    def _build_test_list(self, parent):
        left = tk.Frame(parent, bg=CLR["bg"], width=290)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        tk.Label(left, text="TESTS", bg=CLR["bg"], fg=CLR["accent"],
                 font=(FONT_FAMILY, 9, "bold")).pack(anchor="w", pady=(0, 3))

        card = tk.Frame(left, bg=CLR["panel_bg"], bd=1, relief="solid",
                        highlightbackground=CLR["border"], highlightthickness=1)
        card.pack(fill="both", expand=True)

        lf = tk.Frame(card, bg=CLR["panel_bg"])
        lf.pack(fill="both", expand=True, padx=4, pady=(4, 0))
        sb = tk.Scrollbar(lf, orient="vertical")
        self._lb = tk.Listbox(
            lf, yscrollcommand=sb.set,
            bg=CLR["panel_bg"], fg="#212121",
            selectbackground=CLR["accent"], selectforeground="white",
            font=("Consolas", 8),
            relief="flat", bd=0, highlightthickness=0, activestyle="none",
            selectmode="single",
        )
        sb.config(command=self._lb.yview)
        sb.pack(side="right", fill="y")
        self._lb.pack(side="left", fill="both", expand=True)
        self._lb.bind("<<ListboxSelect>>", self._on_list_select)

        # Toolbar — two rows so all buttons are always visible
        tb1 = tk.Frame(card, bg=CLR["panel_bg"])
        tb1.pack(fill="x", padx=4, pady=(4, 1))
        for text, cmd in [
            ("+ Add",   self._add_test),
            ("⧉ Dupe",  self._dupe_test),
        ]:
            ttk.Button(tb1, text=text, style="Accent.TButton",
                       command=cmd).pack(side="left", padx=(0, 2))

        tb2 = tk.Frame(card, bg=CLR["panel_bg"])
        tb2.pack(fill="x", padx=4, pady=(0, 4))
        for text, cmd in [
            ("↑ Up",    self._move_up),
            ("↓ Down",  self._move_down),
            ("✕ Del",   self._remove_test),
        ]:
            ttk.Button(tb2, text=text, style="Accent.TButton",
                       command=cmd).pack(side="left", padx=(0, 2))

    def _build_test_editor(self, parent):
        right = tk.Frame(parent, bg=CLR["bg"])
        right.pack(side="left", fill="both", expand=True)

        tk.Label(right, text="EDIT SELECTED TEST", bg=CLR["bg"], fg=CLR["accent"],
                 font=(FONT_FAMILY, 9, "bold")).pack(anchor="w", pady=(0, 3))

        self._editor_card = tk.Frame(right, bg=CLR["panel_bg"], bd=1, relief="solid",
                                     highlightbackground=CLR["border"], highlightthickness=1)
        self._editor_card.pack(fill="both", expand=True)

        self._no_test_lbl = tk.Label(
            self._editor_card,
            text="← Select a test from the list, or click  + Add  to create one.",
            bg=CLR["panel_bg"], fg="#9E9E9E", font=(FONT_FAMILY, 10, "italic"))
        self._no_test_lbl.pack(expand=True)

        self._nb = ttk.Notebook(self._editor_card)
        self._tab_basic = self._build_tab_basic(self._nb)
        self._tab_files = self._build_tab_files(self._nb)
        self._tab_flags = self._build_tab_flags_main(self._nb)
        self._tab_ble   = self._build_tab_board(self._nb, "ble",  "BLE Board")
        self._tab_wifi  = self._build_tab_board(self._nb, "wifi", "WiFi Board")

    # ------------------------------------------------------------------
    # Tab builders
    # ------------------------------------------------------------------

    def _build_tab_basic(self, nb) -> tk.Frame:
        f = tk.Frame(nb, bg=CLR["panel_bg"], padx=16, pady=12)
        nb.add(f, text="  Basic  ")
        tk.Label(f, text="Core test identity and execution settings",
                 bg=CLR["panel_bg"], fg="#757575",
                 font=(FONT_FAMILY, 8)).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        rows = [
            ("Test ID:",          "t_id",          None,                  10),
            ("Scenario:",         "t_scenario",    None,                  44),
            ("Delivery Method:",  "t_delivery",    self.DELIVERY_METHODS, 20),
            ("Reset Type:",       "t_reset_type",  self.RESET_TYPES,      12),
            ("Board # Override:", "t_board_number",None,                   8),
        ]
        for r, (label, key, opts, width) in enumerate(rows, start=1):
            tk.Label(f, text=label, bg=CLR["panel_bg"], font=FONT_BOLD,
                     anchor="w", width=18).grid(row=r, column=0, sticky="w", pady=5)
            if opts:
                w = ttk.Combobox(f, textvariable=self._sv[key],
                                 values=opts, font=FONT, width=width)
            else:
                w = tk.Entry(f, textvariable=self._sv[key], font=FONT, width=width,
                             relief="solid", bd=1,
                             highlightbackground=CLR["border"], highlightthickness=1)
            w.grid(row=r, column=1, sticky="w", padx=(0, 8))

        tk.Label(f, text="Board # Override: integer — leave blank to use product config default",
                 bg=CLR["panel_bg"], fg="#9E9E9E",
                 font=(FONT_FAMILY, 7)).grid(row=6, column=0, columnspan=3, sticky="w")

        # Delivery method legend
        legend = tk.Frame(f, bg=CLR["panel_bg"], pady=6)
        legend.grid(row=7, column=0, columnspan=3, sticky="w", pady=(12, 0))
        ttk.Separator(f, orient="horizontal").grid(row=8, column=0, columnspan=3,
                                                   sticky="ew", pady=(0, 6))
        tk.Label(legend, text="Delivery methods:", bg=CLR["panel_bg"],
                 font=(FONT_FAMILY, 8, "bold")).pack(side="left", padx=(0, 10))
        for method, desc in [
            ("SelfProgrammer", "Serial download via SelfProg_Tool.exe"),
            ("JFlash",         "SPI flash via SEGGER JFlashSPI_CL.exe"),
            ("InstallOnly",    "No update — just erase + flag check"),
        ]:
            tk.Label(legend, text=f"  {method}: {desc}",
                     bg=CLR["panel_bg"], fg="#555555",
                     font=(FONT_FAMILY, 7)).pack(side="left", padx=(0, 10))
        f.columnconfigure(1, weight=1)
        return f

    def _build_tab_files(self, nb) -> tk.Frame:
        f = tk.Frame(nb, bg=CLR["panel_bg"], padx=16, pady=12)
        nb.add(f, text="  Files  ")
        tk.Label(f, text="Firmware files for this test  (leave blank if not needed)",
                 bg=CLR["panel_bg"], fg="#757575",
                 font=(FONT_FAMILY, 8)).grid(row=0, column=0, columnspan=3,
                                             sticky="w", pady=(0, 10))
        for r, (label, key, hint) in enumerate([
            ("Flash SREC:", "t_flash_srec",
             "Initial firmware image (.srec) — flashes the device from scratch before the test.\n"
             "Leave blank if the device already has the correct base firmware."),
            ("Update Package:", "t_update_pkg",
             "Firmware update package (.bin / .sxcbin / .xcbin / .ucf) — used by JFlash or SelfProgrammer.\n"
             "Leave blank for InstallOnly tests or when no package is needed."),
        ], start=1):
            tk.Label(f, text=label, bg=CLR["panel_bg"], font=FONT_BOLD,
                     anchor="nw", width=18).grid(row=r * 3 - 2, column=0,
                                                 sticky="nw", pady=(10, 0))
            er = tk.Frame(f, bg=CLR["panel_bg"])
            er.grid(row=r * 3 - 2, column=1, sticky="ew", pady=(10, 0))
            tk.Entry(er, textvariable=self._sv[key], font=FONT, width=46,
                     relief="solid", bd=1,
                     highlightbackground=CLR["border"],
                     highlightthickness=1).pack(side="left", padx=(0, 6))
            ttk.Button(er, text="Browse…", style="Accent.TButton",
                       command=lambda k=key: self._browse_file(k)).pack(side="left")
            tk.Label(f, text=hint, bg=CLR["panel_bg"], fg="#9E9E9E",
                     font=(FONT_FAMILY, 7), wraplength=500,
                     justify="left").grid(row=r * 3 - 1, column=1, sticky="w", padx=2)
        f.columnconfigure(1, weight=1)
        return f

    def _build_tab_flags_main(self, nb) -> tk.Frame:
        f = tk.Frame(nb, bg=CLR["panel_bg"], padx=16, pady=12)
        nb.add(f, text="  Flags (Main)  ")
        tk.Label(f, text="Expected flag values after reset — Main Board",
                 bg=CLR["panel_bg"], fg="#757575",
                 font=(FONT_FAMILY, 8)).grid(row=0, column=0, columnspan=3,
                                             sticky="w", pady=(0, 12))
        self._build_flags_grid(f, "f_", start_row=1)
        return f

    def _build_tab_board(self, nb, board: str, board_label: str) -> tk.Frame:
        f = tk.Frame(nb, bg=CLR["panel_bg"], padx=16, pady=12)
        nb.add(f, text=f"  {board_label}  ")

        sv_en   = self._sv_ble_en  if board == "ble"  else self._sv_wifi_en
        dm_key  = f"t_delivery_{board}"
        pkg_key = f"t_update_pkg_{board}"
        fp      = "fb_" if board == "ble" else "fw_"

        tk.Checkbutton(
            f,
            text=f"Enable {board_label}  (this test uses the {board.upper()} board)",
            variable=sv_en, bg=CLR["panel_bg"], font=FONT_BOLD,
            command=lambda b=board, sv=sv_en: self._toggle_board_section(sv, b)
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        cont = tk.Frame(f, bg=CLR["panel_bg"])
        cont.grid(row=1, column=0, columnspan=3, sticky="nsew")
        setattr(self, f"_{board}_cont", cont)

        tk.Label(cont, text="Delivery Method:", bg=CLR["panel_bg"],
                 font=FONT_BOLD, anchor="w", width=18).grid(row=0, column=0, sticky="w", pady=5)
        ttk.Combobox(cont, textvariable=self._sv[dm_key],
                     values=self.DELIVERY_METHODS,
                     font=FONT, width=20).grid(row=0, column=1, sticky="w")

        tk.Label(cont, text="Update Package:", bg=CLR["panel_bg"],
                 font=FONT_BOLD, anchor="nw", width=18).grid(row=1, column=0, sticky="nw", pady=5)
        pr = tk.Frame(cont, bg=CLR["panel_bg"])
        pr.grid(row=1, column=1, sticky="ew")
        tk.Entry(pr, textvariable=self._sv[pkg_key], font=FONT, width=42,
                 relief="solid", bd=1,
                 highlightbackground=CLR["border"],
                 highlightthickness=1).pack(side="left", padx=(0, 6))
        ttk.Button(pr, text="Browse…", style="Accent.TButton",
                   command=lambda k=pkg_key: self._browse_file(k)).pack(side="left")

        ttk.Separator(cont, orient="horizontal").grid(row=2, column=0, columnspan=3,
                                                      sticky="ew", pady=10)
        tk.Label(cont, text=f"Expected Flags — {board_label}:",
                 bg=CLR["panel_bg"], fg=CLR["accent"],
                 font=(FONT_FAMILY, 9, "bold")).grid(row=3, column=0, columnspan=3,
                                                     sticky="w", pady=(0, 6))
        self._build_flags_grid(cont, fp, start_row=4)
        cont.columnconfigure(1, weight=1)

        self._toggle_board_section(sv_en, board)
        f.columnconfigure(0, weight=1)
        return f

    def _build_flags_grid(self, parent: tk.Frame, prefix: str, start_row: int = 0):
        rows = [
            ("FwUpdate_req:",        f"{prefix}req",     ["0", "255"],       False,
             "0 = no request  /  255 = pending"),
            ("FwUpdate_frez:",       f"{prefix}frez",    ["1", "0"],         False,
             "1 = normal  /  0 = frozen"),
            ("FwUpdate_actbin:",     f"{prefix}actbin",  ["0", "1"],         False,
             "0 = primary binary  /  1 = secondary binary"),
            ("FwUpdate_rollbk:",     f"{prefix}rollbk",  ["255", "0", "1"],  False,
             "255 = disabled  /  0 = enabled  /  1 = rollback pending"),
            ("SelfProg Error Code:", f"{prefix}errcode", self.ERROR_CODES,   True,
             "editable — type any custom hex code  (e.g. 0x20A0)"),
        ]
        for i, (label, sv_key, values, editable, hint) in enumerate(rows):
            tk.Label(parent, text=label, bg=CLR["panel_bg"], font=FONT_BOLD,
                     anchor="w", width=22).grid(row=start_row + i, column=0,
                                                sticky="w", pady=4)
            state = "normal" if editable else "readonly"
            ttk.Combobox(parent, textvariable=self._sv[sv_key],
                         values=values, font=FONT, width=14,
                         state=state).grid(row=start_row + i, column=1,
                                           sticky="w", padx=(0, 8))
            tk.Label(parent, text=hint, bg=CLR["panel_bg"], fg="#9E9E9E",
                     font=(FONT_FAMILY, 7)).grid(row=start_row + i, column=2, sticky="w")

    def _toggle_board_section(self, sv_en: tk.BooleanVar, board: str):
        cont = getattr(self, f"_{board}_cont", None)
        if cont is None:
            return
        if sv_en.get():
            cont.grid()
        else:
            cont.grid_remove()

    # ------------------------------------------------------------------
    # Test list management
    # ------------------------------------------------------------------

    def _rebuild_list(self):
        self._lb.delete(0, "end")
        for t in self._tests:
            tid    = str(t.get("id", ""))
            method = (t.get("delivery_method") or t.get("delivery_method_main") or
                      t.get("delivery_method_ble") or t.get("delivery_method_wifi") or "")
            short  = {"SelfProgrammer": "SelfProg", "JFlash": "JFlash",
                      "InstallOnly": "Install"}.get(method, method or "—")
            srec   = "● " if (t.get("flash_srec") or "").strip() else "  "
            scen   = (t.get("scenario") or "")[:30]
            self._lb.insert("end", f"{srec}{tid:<14}{short:<11}{scen}")

    def _on_list_select(self, _event=None):
        sel = self._lb.curselection()
        if not sel:
            return
        new_idx = sel[0]
        if new_idx == self._current_idx:
            return
        self._commit_current_test()
        self._select_test(new_idx)

    def _select_test(self, idx: int):
        if idx < 0 or idx >= len(self._tests):
            return
        self._current_idx = idx
        self._load_test_to_vars(self._tests[idx])
        self._lb.selection_clear(0, "end")
        self._lb.selection_set(idx)
        self._lb.see(idx)
        # Show the editor notebook (hide placeholder)
        self._no_test_lbl.pack_forget()
        self._nb.pack(fill="both", expand=True, padx=8, pady=8)

    def _add_test(self):
        self._commit_current_test()
        existing = {t.get("id") for t in self._tests}
        n = len(self._tests) + 1
        new_id = f"Test {n}"
        while new_id in existing:
            n += 1
            new_id = f"Test {n}"
        t = self._blank_test()
        t["id"] = new_id
        self._tests.append(t)
        self._rebuild_list()
        self._select_test(len(self._tests) - 1)

    def _dupe_test(self):
        if self._current_idx < 0:
            return
        self._commit_current_test()
        t = dict(self._tests[self._current_idx])
        t["id"] = t.get("id", "Test") + " (copy)"
        self._tests.insert(self._current_idx + 1, t)
        self._rebuild_list()
        self._select_test(self._current_idx + 1)

    def _remove_test(self):
        if self._current_idx < 0:
            return
        if len(self._tests) <= 1:
            messagebox.showinfo("Remove", "A plan must have at least one test.", parent=self)
            return
        tid = self._tests[self._current_idx].get("id", "")
        if not messagebox.askyesno("Remove Test", f"Remove  '{tid}'?", parent=self):
            return
        self._tests.pop(self._current_idx)
        new_idx = min(self._current_idx, len(self._tests) - 1)
        self._current_idx = -1
        self._rebuild_list()
        self._select_test(new_idx)

    def _move_up(self):
        if self._current_idx <= 0:
            return
        self._commit_current_test()
        i = self._current_idx
        self._tests[i], self._tests[i - 1] = self._tests[i - 1], self._tests[i]
        self._rebuild_list()
        self._select_test(i - 1)

    def _move_down(self):
        if self._current_idx < 0 or self._current_idx >= len(self._tests) - 1:
            return
        self._commit_current_test()
        i = self._current_idx
        self._tests[i], self._tests[i + 1] = self._tests[i + 1], self._tests[i]
        self._rebuild_list()
        self._select_test(i + 1)

    # ------------------------------------------------------------------
    # Load / Commit test data  ↔  StringVars
    # ------------------------------------------------------------------

    def _load_test_to_vars(self, t: dict):
        self._sv["t_id"].set(t.get("id", ""))
        self._sv["t_scenario"].set(t.get("scenario", ""))
        self._sv["t_delivery"].set(
            t.get("delivery_method") or t.get("delivery_method_main") or "")
        self._sv["t_reset_type"].set(t.get("reset_type", "install"))
        bn = t.get("board_number")
        self._sv["t_board_number"].set(str(bn) if bn is not None else "")
        self._sv["t_flash_srec"].set(t.get("flash_srec") or "")
        self._sv["t_update_pkg"].set(
            t.get("update_pkg") or t.get("update_pkg_main") or "")

        # Main flags
        self._load_flags(t.get("expected_flags_after_reset") or {}, "f_")

        # BLE
        ble_method = t.get("delivery_method_ble", "")
        ble_pkg    = t.get("update_pkg_ble", "")
        ble_flags  = t.get("expected_flags_after_reset_ble") or {}
        self._sv_ble_en.set(bool(ble_method or ble_pkg or ble_flags))
        self._sv["t_delivery_ble"].set(ble_method)
        self._sv["t_update_pkg_ble"].set(ble_pkg)
        self._load_flags(ble_flags, "fb_")
        self._toggle_board_section(self._sv_ble_en, "ble")

        # WiFi
        wifi_method = t.get("delivery_method_wifi", "")
        wifi_pkg    = t.get("update_pkg_wifi", "")
        wifi_flags  = t.get("expected_flags_after_reset_wifi") or {}
        self._sv_wifi_en.set(bool(wifi_method or wifi_pkg or wifi_flags))
        self._sv["t_delivery_wifi"].set(wifi_method)
        self._sv["t_update_pkg_wifi"].set(wifi_pkg)
        self._load_flags(wifi_flags, "fw_")
        self._toggle_board_section(self._sv_wifi_en, "wifi")

    def _load_flags(self, flags: dict, prefix: str):
        def _s(v): return str(v) if v is not None and v != "" else ""
        self._sv[f"{prefix}req"].set(_s(flags.get("FwUpdate_req", "")))
        self._sv[f"{prefix}frez"].set(_s(flags.get("FwUpdate_frez", "")))
        self._sv[f"{prefix}actbin"].set(_s(flags.get("FwUpdate_actbin", "")))
        self._sv[f"{prefix}rollbk"].set(_s(flags.get("FwUpdate_rollbk", "")))
        self._sv[f"{prefix}errcode"].set(_s(flags.get("SelfProg Error Code", "")))

    def _commit_current_test(self):
        if self._current_idx < 0 or self._current_idx >= len(self._tests):
            return
        t: dict = {}
        t["id"]       = self._sv["t_id"].get().strip()
        t["scenario"] = self._sv["t_scenario"].get().strip()

        delivery = self._sv["t_delivery"].get().strip()
        if delivery:
            t["delivery_method"] = delivery

        rt = self._sv["t_reset_type"].get().strip()
        if rt:
            t["reset_type"] = rt

        bn = self._sv["t_board_number"].get().strip()
        if bn:
            try:
                t["board_number"] = int(bn)
            except ValueError:
                pass

        t["flash_srec"] = self._sv["t_flash_srec"].get().strip()

        upkg = self._sv["t_update_pkg"].get().strip()
        if upkg:
            t["update_pkg"] = upkg

        flags = self._commit_flags("f_")
        if flags:
            t["expected_flags_after_reset"] = flags

        if self._sv_ble_en.get():
            dm = self._sv["t_delivery_ble"].get().strip()
            if dm:
                t["delivery_method_ble"] = dm
            pk = self._sv["t_update_pkg_ble"].get().strip()
            if pk:
                t["update_pkg_ble"] = pk
            fl = self._commit_flags("fb_")
            if fl:
                t["expected_flags_after_reset_ble"] = fl

        if self._sv_wifi_en.get():
            dm = self._sv["t_delivery_wifi"].get().strip()
            if dm:
                t["delivery_method_wifi"] = dm
            pk = self._sv["t_update_pkg_wifi"].get().strip()
            if pk:
                t["update_pkg_wifi"] = pk
            fl = self._commit_flags("fw_")
            if fl:
                t["expected_flags_after_reset_wifi"] = fl

        self._tests[self._current_idx] = t
        # Refresh list row in place
        self._rebuild_list()
        self._lb.selection_set(self._current_idx)

    def _commit_flags(self, prefix: str) -> dict:
        flags: dict = {}
        for sv_key, fname in [
            (f"{prefix}req",    "FwUpdate_req"),
            (f"{prefix}frez",   "FwUpdate_frez"),
            (f"{prefix}actbin", "FwUpdate_actbin"),
            (f"{prefix}rollbk", "FwUpdate_rollbk"),
        ]:
            v = self._sv[sv_key].get().strip()
            if v != "":
                flags[fname] = _flag_to_native(v)
        ec = self._sv[f"{prefix}errcode"].get().strip()
        if ec:
            flags["SelfProg Error Code"] = ec
        return flags

    # ------------------------------------------------------------------
    # Browse / Save
    # ------------------------------------------------------------------

    def _browse_file(self, sv_key: str):
        current = self._sv[sv_key].get()
        init_dir = (str(Path(current).parent)
                    if current and Path(current).parent.exists() else "C:\\")
        path = filedialog.askopenfilename(
            parent=self, title="Select file", initialdir=init_dir,
            filetypes=[("Firmware files", "*.srec *.bin *.sxcbin *.xcbin *.ucf"),
                       ("All files", "*.*")])
        if path:
            self._sv[sv_key].set(path)

    def _save(self):
        self._commit_current_test()

        plan_name = self.sv_plan_name.get().strip()
        if not plan_name:
            messagebox.showerror("Validation", "Plan Name is required.", parent=self)
            return

        filename = self.sv_filename.get().strip()
        if not filename:
            messagebox.showerror("Validation", "Filename is required.", parent=self)
            return
        if not filename.lower().endswith((".yaml", ".yml")):
            filename += ".yaml"
            self.sv_filename.set(filename)

        if not self._tests:
            messagebox.showerror("Validation", "At least one test is required.", parent=self)
            return

        ids = [t.get("id", "") for t in self._tests]
        if len(ids) != len(set(ids)):
            dup = next(i for i in ids if ids.count(i) > 1)
            messagebox.showerror("Validation",
                                 f"Test IDs must be unique.\nDuplicate: '{dup}'",
                                 parent=self)
            return

        dest = TESTPLANS_DIR / filename
        if self._mode == "new" and dest.exists():
            if not messagebox.askyesno("File Exists",
                                       f"'{filename}' already exists.\nOverwrite it?",
                                       parent=self):
                return

        data: dict = {"name": plan_name}
        pname = self.sv_product_name.get().strip()
        if pname:
            data["product_name"] = pname
        data["tests"] = self._tests

        TESTPLANS_DIR.mkdir(parents=True, exist_ok=True)
        dest.write_text(serialize_testplan(data), encoding="utf-8")

        messagebox.showinfo("Saved", f"✔  Test plan saved:\n{dest}", parent=self)
        self._parent._reload_testplans()
        if filename in list_testplans():
            self._parent.sv_testplan.set(filename)
            self._parent._on_testplan_changed()
        self.destroy()


# ---------------------------------------------------------------------------
# Product Config Editor Dialog
# ---------------------------------------------------------------------------

class ProductConfigDialog(tk.Toplevel):
    """Full editor for a product configuration JSON file.
    Also exposes the relay control COM port (shared across all products).
    """

    BAUD_OPTIONS    = ["9600", "19200", "38400", "57600", "115200"]
    DEVICE_OPTIONS  = ["RX65x", "RX66x", "RX651", "RX660", "RX671"]
    TOOL_OPTIONS    = ["e2l", "e2", "j-link"]
    IFACE_OPTIONS   = ["fine", "jtag"]

    def __init__(self, parent: "App", mode: str = "edit", product_name: str | None = None):
        super().__init__(parent)
        self._parent      = parent
        self._mode        = mode           # "edit" | "new"
        self._orig_name   = product_name   # None when mode=="new"

        title = "New Product Config" if mode == "new" else f"Edit Config — {product_name}"
        self.title(title)
        self.geometry("700x600")
        self.minsize(640, 540)
        self.configure(bg=CLR["bg"])
        self.resizable(True, True)
        self.grab_set()
        self.transient(parent)

        # Load existing data
        self._cfg: dict = {}
        if mode == "edit" and product_name:
            cfg_path = PRODUCTCONFIGS_DIR / f"{product_name}.json"
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as f:
                    self._cfg = json.load(f)

        # One StringVar per field + relay fields
        self._sv: dict[str, tk.StringVar] = {}
        self._entries: dict[str, tk.Widget] = {}
        self._init_vars()
        self._build_ui()
        self.focus_set()

    # ------------------------------------------------------------------
    def _init_vars(self):
        c = self._cfg
        defaults = {
            "product_name":     "",
            "id_code":          "",
            "rfp_exe":          r"C:\Program Files (x86)\Renesas Electronics\Programming Tools\Renesas Flash Programmer V3.21\rfp-cli.exe",
            "rfp_device":       "RX65x",
            "rfp_tool":         "e2l",
            "rfp_interface":    "fine",
            "jflash_exe":       r"C:\Program Files\SEGGER\JLink\JFlashSPI_CL.exe",
            "jflash_project":   r"C:\Software\J-Flash SPI_Projects\V9.12\jlinkflash.jflash",
            "selfprog_exe":     "",
            "serial_port":      "8",
            "serial_baud":      "38400",
            "board_number":     "48",
            "ble_board_number": "",
            "wifi_board_number":"",
            "relay_on_script":  "relaycontrol/relayon.py",
            "relay_off_script": "relaycontrol/relayoff.py",
        }
        for key, default in defaults.items():
            val = c.get(key)
            self._sv[key] = tk.StringVar(value=default if val is None else str(val))

        # Relay com/baud read from the actual relay scripts (global)
        relay_com, relay_baud = get_relay_settings()
        self._sv["relay_com_port"] = tk.StringVar(value=relay_com)
        self._sv["relay_baud"]     = tk.StringVar(value=str(relay_baud))

    # ------------------------------------------------------------------
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=CLR["hdr_bg"], height=46)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)
        icon = "✦  New Product Config" if self._mode == "new" else "✎  Edit Product Config"
        tk.Label(hdr, text=f"  {icon}", bg=CLR["hdr_bg"], fg=CLR["hdr_fg"],
                 font=(FONT_FAMILY, 12, "bold")).pack(side="left", padx=14, pady=8)
        if self._mode == "edit" and self._orig_name:
            tk.Label(hdr, text=f"{self._orig_name}.json", bg=CLR["hdr_bg"],
                     fg="#90CAF9", font=(FONT_FAMILY, 9)).pack(side="right", padx=14)

        # Notebook
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=(10, 0))
        self._build_tab_basic(nb)
        self._build_tab_rfp(nb)
        self._build_tab_jflash(nb)
        self._build_tab_selfprog(nb)
        self._build_tab_relay(nb)

        # Bottom buttons
        btn_frame = tk.Frame(self, bg=CLR["bg"])
        btn_frame.pack(fill="x", padx=12, pady=10)
        lbl = "Save & Create" if self._mode == "new" else "Save Changes"
        ttk.Button(btn_frame, text=f"💾  {lbl}", style="Run.TButton",
                   command=self._save).pack(side="left", padx=(0, 8))
        ttk.Button(btn_frame, text="Cancel", style="Accent.TButton",
                   command=self.destroy).pack(side="left")
        tk.Label(btn_frame, text="Config is saved to productconfigs/  •  Relay scripts are updated in-place.",
                 bg=CLR["bg"], fg="#9E9E9E", font=(FONT_FAMILY, 8)).pack(side="right")

    # ------------------------------------------------------------------
    def _tab_frame(self, nb: ttk.Notebook, title: str) -> tk.Frame:
        f = tk.Frame(nb, bg=CLR["bg"], padx=16, pady=14)
        nb.add(f, text=f"  {title}  ")
        return f

    def _field_row(self, parent: tk.Frame, row: int, label: str, key: str,
                   hint: str = "", browse: str = None,
                   combo_vals: list = None, width: int = 44) -> tk.Widget:
        """Render one label + input row. Returns the input widget."""
        tk.Label(parent, text=label, bg=CLR["bg"], font=FONT_BOLD,
                 anchor="w", width=17).grid(row=row * 2, column=0, sticky="nw", pady=(6, 0))

        if combo_vals:
            widget = ttk.Combobox(parent, textvariable=self._sv[key],
                                  values=combo_vals, font=FONT, width=width - 2)
            widget.grid(row=row * 2, column=1, sticky="ew", padx=(0, 6))
        else:
            widget = tk.Entry(parent, textvariable=self._sv[key], font=FONT,
                              width=width, relief="solid", bd=1,
                              highlightbackground=CLR["border"], highlightthickness=1)
            widget.grid(row=row * 2, column=1, sticky="ew", padx=(0, 6))

        if browse == "file":
            ttk.Button(parent, text="Browse…", style="Accent.TButton",
                       command=lambda k=key: self._browse_file(k)).grid(
                row=row * 2, column=2, sticky="w")

        if hint:
            tk.Label(parent, text=hint, bg=CLR["bg"], fg="#9E9E9E",
                     font=(FONT_FAMILY, 7)).grid(
                row=row * 2 + 1, column=1, sticky="w", padx=(2, 0))

        parent.columnconfigure(1, weight=1)
        self._entries[key] = widget
        return widget

    # ------------------------------------------------------------------
    def _build_tab_basic(self, nb):
        f = self._tab_frame(nb, "Basic")
        tk.Label(f, text="Core product identity settings", bg=CLR["bg"],
                 fg="#757575", font=(FONT_FAMILY, 8)).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        w_name = self._field_row(f, 1, "Product Name:", "product_name",
                                 hint="Determines the filename  →  productconfigs/{name}.json")
        self._field_row(f, 2, "ID Code:", "id_code",
                        hint="32 hex characters (16 bytes)  —  used by RFP for device authentication")

        # In edit mode the product name (= filename) is read-only
        if self._mode == "edit":
            w_name.config(state="readonly", disabledforeground="#757575")

    def _build_tab_rfp(self, nb):
        f = self._tab_frame(nb, "RFP Flash")
        tk.Label(f, text="Renesas Flash Programmer (rfp-cli.exe) settings", bg=CLR["bg"],
                 fg="#757575", font=(FONT_FAMILY, 8)).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        self._field_row(f, 1, "RFP CLI EXE:", "rfp_exe", browse="file",
                        hint="Full path to rfp-cli.exe")
        self._field_row(f, 2, "Device Family:", "rfp_device",
                        combo_vals=self.DEVICE_OPTIONS, hint="e.g. RX65x / RX66x")
        self._field_row(f, 3, "Tool:", "rfp_tool",
                        combo_vals=self.TOOL_OPTIONS, hint="e.g. e2l  (E2 emulator Lite)")
        self._field_row(f, 4, "Interface:", "rfp_interface",
                        combo_vals=self.IFACE_OPTIONS, hint="e.g. fine / jtag")

    def _build_tab_jflash(self, nb):
        f = self._tab_frame(nb, "J-Flash")
        tk.Label(f, text="SEGGER J-Flash SPI CLI settings", bg=CLR["bg"],
                 fg="#757575", font=(FONT_FAMILY, 8)).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        self._field_row(f, 1, "JFlash EXE:", "jflash_exe", browse="file",
                        hint="Full path to JFlashSPI_CL.exe")
        self._field_row(f, 2, "JFlash Project:", "jflash_project", browse="file",
                        hint="Full path to .jflash project file")

    def _build_tab_selfprog(self, nb):
        f = self._tab_frame(nb, "SelfProgrammer")
        tk.Label(f, text="SelfProg Tool executable and board / serial connection settings", bg=CLR["bg"],
                 fg="#757575", font=(FONT_FAMILY, 8)).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        self._field_row(f, 1, "SelfProg EXE:", "selfprog_exe", browse="file",
                        hint="Full path to SelfProg_Tool.exe")

        # Separator
        ttk.Separator(f, orient="horizontal").grid(
            row=5, column=0, columnspan=3, sticky="ew", pady=(10, 4))

        self._field_row(f, 3, "COM Port #:", "serial_port",
                        hint="Integer only  (e.g. 8  →  COM8)", width=10)
        self._field_row(f, 4, "Baud Rate:", "serial_baud",
                        combo_vals=self.BAUD_OPTIONS, hint="Download baud rate", width=12)

        ttk.Separator(f, orient="horizontal").grid(
            row=11, column=0, columnspan=3, sticky="ew", pady=(10, 4))

        self._field_row(f, 6, "Main Board #:", "board_number",
                        hint="Primary FEBE board number (integer)", width=10)
        self._field_row(f, 7, "BLE Board #:", "ble_board_number",
                        hint="Leave blank if no BLE board", width=10)
        self._field_row(f, 8, "WiFi Board #:", "wifi_board_number",
                        hint="Leave blank if no WiFi board", width=10)

    def _build_tab_relay(self, nb):
        f = self._tab_frame(nb, "Relay Control")
        tk.Label(f, text="Hardware relay for device power cycling", bg=CLR["bg"],
                 fg="#757575", font=(FONT_FAMILY, 8)).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        self._field_row(f, 1, "Relay ON Script:", "relay_on_script",
                        hint="Relative path to relayon.py")
        self._field_row(f, 2, "Relay OFF Script:", "relay_off_script",
                        hint="Relative path to relayoff.py")

        ttk.Separator(f, orient="horizontal").grid(
            row=6, column=0, columnspan=3, sticky="ew", pady=12)

        tk.Label(f, text="⚡  Relay Serial COM Port  (global — applies to both relay scripts)",
                 bg=CLR["bg"], fg=CLR["accent"],
                 font=(FONT_FAMILY, 9, "bold")).grid(
            row=7, column=0, columnspan=3, sticky="w", pady=(0, 8))

        tk.Label(f, text="COM Port:", bg=CLR["bg"], font=FONT_BOLD,
                 anchor="w", width=17).grid(row=8, column=0, sticky="w", pady=5)
        com_row = tk.Frame(f, bg=CLR["bg"])
        com_row.grid(row=8, column=1, sticky="w")
        com_entry = tk.Entry(com_row, textvariable=self._sv["relay_com_port"], font=FONT,
                             width=10, relief="solid", bd=1,
                             highlightbackground=CLR["border"], highlightthickness=1)
        com_entry.pack(side="left", padx=(0, 6))
        tk.Label(com_row, text="e.g.  COM10", bg=CLR["bg"],
                 fg="#9E9E9E", font=(FONT_FAMILY, 8)).pack(side="left")

        tk.Label(f, text="Baud Rate:", bg=CLR["bg"], font=FONT_BOLD,
                 anchor="w", width=17).grid(row=9, column=0, sticky="w", pady=5)
        ttk.Combobox(f, textvariable=self._sv["relay_baud"],
                     values=["9600", "19200", "38400", "115200"],
                     font=FONT, width=10).grid(row=9, column=1, sticky="w")

        tk.Label(f,
                 text="⚠  Changes here overwrite  relaycontrol/relayon.py  and  relaycontrol/relayoff.py\n"
                      "    These relay scripts are shared across all product configs.",
                 bg=CLR["bg"], fg="#E65100",
                 font=(FONT_FAMILY, 8)).grid(row=10, column=0, columnspan=3, sticky="w", pady=(10, 0))

    # ------------------------------------------------------------------
    def _browse_file(self, key: str):
        current = self._sv[key].get()
        init_dir = str(Path(current).parent) if current and Path(current).parent.exists() else str(ROOT)
        path = filedialog.askopenfilename(parent=self, title=f"Select file", initialdir=init_dir)
        if path:
            self._sv[key].set(path)

    # ------------------------------------------------------------------
    def _save(self):
        product_name = self._sv["product_name"].get().strip()
        if not product_name:
            messagebox.showerror("Validation Error", "Product Name is required.", parent=self)
            return

        id_code = self._sv["id_code"].get().strip()
        if id_code and (len(id_code) != 32 or not all(
                c in "0123456789abcdefABCDEF" for c in id_code)):
            messagebox.showerror("Validation Error",
                                 "ID Code must be exactly 32 hexadecimal characters.",
                                 parent=self)
            return

        for fld in ("serial_port", "board_number"):
            v = self._sv[fld].get().strip()
            if v:
                try:
                    int(v)
                except ValueError:
                    messagebox.showerror("Validation Error",
                                         f"'{fld}' must be an integer.", parent=self)
                    return

        cfg_path = PRODUCTCONFIGS_DIR / f"{product_name}.json"
        if self._mode == "new" and cfg_path.exists():
            if not messagebox.askyesno(
                    "Config Exists",
                    f"A config for '{product_name}' already exists.\nOverwrite it?",
                    parent=self):
                return

        def _int_or_none(key: str):
            v = self._sv[key].get().strip()
            return int(v) if v else None

        data: dict = {
            "product_name":   product_name,
            "id_code":        id_code,
            "rfp_exe":        self._sv["rfp_exe"].get().strip(),
            "rfp_device":     self._sv["rfp_device"].get().strip(),
            "rfp_tool":       self._sv["rfp_tool"].get().strip(),
            "rfp_interface":  self._sv["rfp_interface"].get().strip(),
            "jflash_exe":     self._sv["jflash_exe"].get().strip(),
            "jflash_project": self._sv["jflash_project"].get().strip(),
            "selfprog_exe":   self._sv["selfprog_exe"].get().strip(),
            "relay_on_script":  self._sv["relay_on_script"].get().strip(),
            "relay_off_script": self._sv["relay_off_script"].get().strip(),
            "serial_port":    _int_or_none("serial_port"),
            "serial_baud":    _int_or_none("serial_baud") or 38400,
            "board_number":   _int_or_none("board_number"),
        }
        for opt in ("ble_board_number", "wifi_board_number"):
            v = _int_or_none(opt)
            if v is not None:
                data[opt] = v

        PRODUCTCONFIGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        # Update relay scripts if COM/baud changed
        relay_com = self._sv["relay_com_port"].get().strip().upper()
        try:
            relay_baud = int(self._sv["relay_baud"].get().strip())
        except ValueError:
            relay_baud = 9600
        if relay_com:
            try:
                set_relay_settings(relay_com, relay_baud)
            except Exception as exc:
                messagebox.showwarning("Relay Update Warning",
                                       f"Config saved, but relay scripts could not be updated:\n{exc}",
                                       parent=self)

        messagebox.showinfo("Saved", f"✔  Config saved:\n{cfg_path}", parent=self)
        self._parent._refresh_config_selector()
        self._parent._update_config_display(product_name)
        self._parent._update_relay_display()
        self.destroy()


# ---------------------------------------------------------------------------
# Main Application Window
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VP SecureFW Test Framework")
        self.geometry("1020x780")
        self.minsize(820, 620)
        self.configure(bg=CLR["bg"])

        # State
        self._proc: subprocess.Popen | None = None
        self._run_thread: threading.Thread | None = None
        self._output_queue: queue.Queue[str | None] = queue.Queue()
        self._polling = False

        # StringVars
        self.sv_testplan = tk.StringVar()
        self.sv_only_test = tk.StringVar(value="— All Tests —")
        self.sv_start_from = tk.StringVar(value="— Beginning —")
        self.sv_repeat = tk.StringVar(value="1")
        self.sv_email = tk.StringVar()
        self.sv_status = tk.StringVar(value="Idle  —  select a test plan to get started")

        self._build_ui()
        self._refresh_reports()
        self._refresh_config_selector()

        # Populate testplan dropdown
        plans = list_testplans()
        self._cb_testplan["values"] = plans
        if plans:
            self.sv_testplan.set(plans[0])
            self._on_testplan_changed()

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        self._style_widgets()

        # ── Header bar ──────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=CLR["hdr_bg"], height=52)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)
        tk.Label(
            hdr,
            text="  VP SecureFW  Test Framework",
            bg=CLR["hdr_bg"],
            fg=CLR["hdr_fg"],
            font=(FONT_FAMILY, 14, "bold"),
        ).pack(side="left", padx=16, pady=10)
        tk.Label(
            hdr,
            text="Firmware Validation & Automation Suite",
            bg=CLR["hdr_bg"],
            fg="#90CAF9",
            font=(FONT_FAMILY, 9),
        ).pack(side="right", padx=18, pady=10)

        # ── Main content area (left + right columns) ─────────────────────
        main = tk.Frame(self, bg=CLR["bg"])
        main.pack(fill="both", expand=True, padx=12, pady=(10, 0))

        left_col = tk.Frame(main, bg=CLR["bg"])
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 6))

        right_col = tk.Frame(main, bg=CLR["bg"])
        right_col.pack(side="right", fill="both", expand=False, padx=(6, 0))

        # ── LEFT: Test Plan Selection ───────────────────────────────────
        self._build_plan_section(left_col)

        # ── LEFT: Run Options ──────────────────────────────────────────
        self._build_options_section(left_col)

        # ── LEFT: Run Controls ─────────────────────────────────────────
        self._build_controls(left_col)

        # ── LEFT: Console Output ───────────────────────────────────────
        self._build_console(left_col)

        # ── RIGHT: Product Config Info ─────────────────────────────────
        self._build_config_panel(right_col)

        # ── RIGHT: Relay Control ────────────────────────────────────────
        self._build_relay_panel(right_col)

        # ── RIGHT: Reports ─────────────────────────────────────────────
        self._build_reports_panel(right_col)

        # ── Status bar ─────────────────────────────────────────────────
        status_bar = tk.Frame(self, bg=CLR["status_bg"], height=28, relief="flat",
                              bd=0, highlightbackground=CLR["border"], highlightthickness=1)
        status_bar.pack(fill="x", side="bottom")
        status_bar.pack_propagate(False)
        tk.Label(
            status_bar,
            textvariable=self.sv_status,
            bg=CLR["status_bg"],
            fg=CLR["accent"],
            font=(FONT_FAMILY, 9),
            anchor="w",
        ).pack(side="left", padx=10, pady=4)

    def _style_widgets(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("TCombobox",
                        fieldbackground=CLR["panel_bg"],
                        background=CLR["panel_bg"],
                        foreground="#212121",
                        arrowcolor=CLR["accent"],
                        bordercolor=CLR["border"],
                        relief="flat")

        style.configure("TSpinbox",
                        fieldbackground=CLR["panel_bg"],
                        background=CLR["panel_bg"],
                        foreground="#212121",
                        arrowcolor=CLR["accent"],
                        bordercolor=CLR["border"])

        style.configure("Accent.TButton",
                        background=CLR["accent"],
                        foreground="white",
                        font=FONT_BOLD,
                        padding=(8, 5),
                        relief="flat",
                        borderwidth=0)
        style.map("Accent.TButton",
                  background=[("active", CLR["accent_hover"]), ("disabled", "#90A4AE")])

        style.configure("Run.TButton",
                        background=CLR["run_btn"],
                        foreground="white",
                        font=(FONT_FAMILY, 11, "bold"),
                        padding=(14, 7),
                        relief="flat",
                        borderwidth=0)
        style.map("Run.TButton",
                  background=[("active", "#388E3C"), ("disabled", "#A5D6A7")])

        style.configure("Stop.TButton",
                        background=CLR["stop_btn"],
                        foreground="white",
                        font=(FONT_FAMILY, 11, "bold"),
                        padding=(14, 7),
                        relief="flat",
                        borderwidth=0)
        style.map("Stop.TButton",
                  background=[("active", "#D32F2F"), ("disabled", "#EF9A9A")])

        style.configure("Card.TFrame",
                        background=CLR["panel_bg"],
                        relief="flat",
                        borderwidth=1)

        style.configure("TLabel",
                        background=CLR["bg"],
                        foreground="#212121",
                        font=FONT)
        style.configure("Card.TLabel",
                        background=CLR["panel_bg"],
                        foreground="#212121",
                        font=FONT)
        style.configure("SectionHeader.TLabel",
                        background=CLR["bg"],
                        foreground=CLR["accent"],
                        font=(FONT_FAMILY, 9, "bold"))

    def _section_frame(self, parent, title: str) -> tk.Frame:
        """Helper: creates a titled card frame."""
        outer = tk.Frame(parent, bg=CLR["bg"])
        outer.pack(fill="x", pady=(0, 8))

        # Title label
        tk.Label(outer, text=title, bg=CLR["bg"], fg=CLR["accent"],
                 font=(FONT_FAMILY, 9, "bold")).pack(anchor="w", padx=2, pady=(0, 3))

        # Card
        card = tk.Frame(outer, bg=CLR["panel_bg"], bd=1,
                        relief="solid",
                        highlightbackground=CLR["border"],
                        highlightthickness=1)
        card.pack(fill="x")
        return card

    def _build_plan_section(self, parent):
        card = self._section_frame(parent, "TEST PLAN")
        row = tk.Frame(card, bg=CLR["panel_bg"])
        row.pack(fill="x", padx=10, pady=10)

        tk.Label(row, text="Test Plan File:", bg=CLR["panel_bg"],
                 font=FONT_BOLD, width=14, anchor="w").pack(side="left")

        self._cb_testplan = ttk.Combobox(
            row, textvariable=self.sv_testplan,
            state="readonly", font=FONT, width=36)
        self._cb_testplan.pack(side="left", padx=(0, 6))
        self._cb_testplan.bind("<<ComboboxSelected>>", lambda _: self._on_testplan_changed())

        ttk.Button(row, text="Browse…", style="Accent.TButton",
                   command=self._browse_testplan).pack(side="left", padx=(0, 6))
        ttk.Button(row, text="↺ Reload", style="Accent.TButton",
                   command=self._reload_testplans).pack(side="left")

        # Second row: plan editor buttons
        row2 = tk.Frame(card, bg=CLR["panel_bg"])
        row2.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(row2, text="✎  Edit Plan", style="Accent.TButton",
                   command=lambda: self._open_testplan_editor("edit")).pack(side="left", padx=(0, 6))
        ttk.Button(row2, text="+  New Plan", style="Accent.TButton",
                   command=lambda: self._open_testplan_editor("new")).pack(side="left", padx=(0, 6))
        ttk.Button(row2, text="✕  Delete Plan", style="Stop.TButton",
                   command=self._delete_testplan).pack(side="left")
        tk.Label(row2, text="  Create or fully edit a test plan YAML using the visual editor",
                 bg=CLR["panel_bg"], fg="#9E9E9E",
                 font=(FONT_FAMILY, 7)).pack(side="left", padx=(8, 0))

    def _build_options_section(self, parent):
        card = self._section_frame(parent, "RUN OPTIONS")
        grid = tk.Frame(card, bg=CLR["panel_bg"])
        grid.pack(fill="x", padx=10, pady=10)

        # Row 0: Only Test
        tk.Label(grid, text="Only Test:", bg=CLR["panel_bg"],
                 font=FONT_BOLD, width=14, anchor="w").grid(row=0, column=0, sticky="w", pady=4)
        self._cb_only = ttk.Combobox(
            grid, textvariable=self.sv_only_test,
            state="readonly", font=FONT, width=32)
        self._cb_only.grid(row=0, column=1, sticky="w", padx=(0, 12))
        tk.Label(grid, text="Run a single specific test only",
                 bg=CLR["panel_bg"], fg="#757575", font=(FONT_FAMILY, 8)).grid(
            row=0, column=2, sticky="w")

        # Row 1: Start From
        tk.Label(grid, text="Start From:", bg=CLR["panel_bg"],
                 font=FONT_BOLD, width=14, anchor="w").grid(row=1, column=0, sticky="w", pady=4)
        self._cb_start = ttk.Combobox(
            grid, textvariable=self.sv_start_from,
            state="readonly", font=FONT, width=32)
        self._cb_start.grid(row=1, column=1, sticky="w", padx=(0, 12))
        tk.Label(grid, text="Run this test and all subsequent tests",
                 bg=CLR["panel_bg"], fg="#757575", font=(FONT_FAMILY, 8)).grid(
            row=1, column=2, sticky="w")

        # Row 2: Repeat
        tk.Label(grid, text="Repeat:", bg=CLR["panel_bg"],
                 font=FONT_BOLD, width=14, anchor="w").grid(row=2, column=0, sticky="w", pady=4)
        repeat_frame = tk.Frame(grid, bg=CLR["panel_bg"])
        repeat_frame.grid(row=2, column=1, sticky="w")
        ttk.Spinbox(repeat_frame, textvariable=self.sv_repeat,
                    from_=1, to=99, width=6, font=FONT).pack(side="left")
        tk.Label(repeat_frame, text=" times  (a separate report is generated per run)",
                 bg=CLR["panel_bg"], fg="#757575", font=(FONT_FAMILY, 8)).pack(side="left")

        # Row 3: Email
        tk.Label(grid, text="Send Report To:", bg=CLR["panel_bg"],
                 font=FONT_BOLD, width=14, anchor="w").grid(row=3, column=0, sticky="w", pady=4)
        email_frame = tk.Frame(grid, bg=CLR["panel_bg"])
        email_frame.grid(row=3, column=1, columnspan=2, sticky="w")
        tk.Entry(email_frame, textvariable=self.sv_email, font=FONT,
                 width=34, relief="solid", bd=1,
                 highlightbackground=CLR["border"],
                 highlightthickness=1).pack(side="left")
        tk.Label(email_frame, text="  optional — requires GMAIL_SENDER & GMAIL_APP_PASSWORD env vars",
                 bg=CLR["panel_bg"], fg="#757575", font=(FONT_FAMILY, 8)).pack(side="left")

    def _build_controls(self, parent):
        frame = tk.Frame(parent, bg=CLR["bg"])
        frame.pack(fill="x", pady=(0, 6))

        self._btn_run = ttk.Button(
            frame, text="▶  Run Tests", style="Run.TButton",
            command=self._start_run)
        self._btn_run.pack(side="left", padx=(0, 10))

        self._btn_stop = ttk.Button(
            frame, text="■  Stop", style="Stop.TButton",
            command=self._stop_run, state="disabled")
        self._btn_stop.pack(side="left", padx=(0, 10))

        ttk.Button(
            frame, text="Clear Console", style="Accent.TButton",
            command=self._clear_console).pack(side="left")

        # Progress indicator
        self._progress = ttk.Progressbar(frame, mode="indeterminate", length=180)
        self._progress.pack(side="right", padx=(0, 4))

    def _build_console(self, parent):
        outer = tk.Frame(parent, bg=CLR["bg"])
        outer.pack(fill="both", expand=True, pady=(0, 8))
        tk.Label(outer, text="CONSOLE OUTPUT", bg=CLR["bg"], fg=CLR["accent"],
                 font=(FONT_FAMILY, 9, "bold")).pack(anchor="w", padx=2, pady=(0, 3))

        self._console = scrolledtext.ScrolledText(
            outer,
            bg=CLR["console_bg"],
            fg=CLR["console_fg"],
            font=FONT_MONO,
            relief="flat",
            bd=0,
            wrap="word",
            state="disabled",
            insertbackground=CLR["console_fg"],
        )
        self._console.pack(fill="both", expand=True)

        # Colour tags for console text
        self._console.tag_configure("pass",   foreground="#4EC9B0")
        self._console.tag_configure("fail",   foreground="#F44747")
        self._console.tag_configure("warn",   foreground="#CE9178")
        self._console.tag_configure("info",   foreground="#9CDCFE")
        self._console.tag_configure("header", foreground="#DCDCAA", font=(FONT_MONO[0], FONT_MONO[1], "bold"))
        self._console.tag_configure("dim",    foreground="#808080")

    def _build_config_panel(self, parent):
        outer = tk.Frame(parent, bg=CLR["bg"])
        outer.pack(fill="x", pady=(0, 8))

        # Header row: title + Edit + New buttons
        hdr_row = tk.Frame(outer, bg=CLR["bg"])
        hdr_row.pack(fill="x", padx=2, pady=(0, 3))
        tk.Label(hdr_row, text="PRODUCT CONFIG", bg=CLR["bg"], fg=CLR["accent"],
                 font=(FONT_FAMILY, 9, "bold")).pack(side="left")
        self._btn_edit_cfg = ttk.Button(hdr_row, text="✎ Edit", style="Accent.TButton",
                                        command=lambda: self._open_config_editor("edit"))
        self._btn_edit_cfg.pack(side="right", padx=(4, 0))
        ttk.Button(hdr_row, text="+ New", style="Accent.TButton",
                   command=lambda: self._open_config_editor("new")).pack(side="right")

        # Config selector dropdown
        sel_row = tk.Frame(outer, bg=CLR["bg"])
        sel_row.pack(fill="x", padx=2, pady=(0, 4))
        tk.Label(sel_row, text="Config:", bg=CLR["bg"],
                 font=FONT, fg="#424242").pack(side="left")
        self.sv_cfg_selector = tk.StringVar()
        self._cb_cfg = ttk.Combobox(sel_row, textvariable=self.sv_cfg_selector,
                                    state="readonly", font=FONT, width=20)
        self._cb_cfg.pack(side="left", padx=(4, 0))
        self._cb_cfg.bind("<<ComboboxSelected>>",
                          lambda _: self._update_config_display(self.sv_cfg_selector.get()))

        # Card with details
        card = tk.Frame(outer, bg=CLR["panel_bg"], bd=1, relief="solid",
                        highlightbackground=CLR["border"], highlightthickness=1)
        card.pack(fill="x")

        self._cfg_text = tk.Text(
            card, bg=CLR["panel_bg"], fg="#424242",
            font=(FONT_FAMILY, 8), relief="flat", bd=0,
            wrap="word", state="disabled", height=13, width=32,
        )
        self._cfg_text.pack(fill="both", padx=8, pady=8)
        self._cfg_text.tag_configure("key",  foreground=CLR["accent"],  font=(FONT_FAMILY, 8, "bold"))
        self._cfg_text.tag_configure("val",  foreground="#424242")
        self._cfg_text.tag_configure("none", foreground="#9E9E9E", font=(FONT_FAMILY, 8, "italic"))

        self._refresh_config_selector()

    def _build_relay_panel(self, parent):
        outer = tk.Frame(parent, bg=CLR["bg"])
        outer.pack(fill="x", pady=(0, 8))
        tk.Label(outer, text="RELAY CONTROL  (shared)", bg=CLR["bg"], fg=CLR["accent"],
                 font=(FONT_FAMILY, 9, "bold")).pack(anchor="w", padx=2, pady=(0, 3))

        card = tk.Frame(outer, bg=CLR["panel_bg"], bd=1, relief="solid",
                        highlightbackground=CLR["border"], highlightthickness=1)
        card.pack(fill="x")

        inner = tk.Frame(card, bg=CLR["panel_bg"])
        inner.pack(fill="x", padx=10, pady=8)

        # COM Port row
        tk.Label(inner, text="COM Port:", bg=CLR["panel_bg"],
                 font=FONT_BOLD, width=10, anchor="w").grid(row=0, column=0, sticky="w")
        self.sv_relay_com = tk.StringVar()
        com_entry = tk.Entry(inner, textvariable=self.sv_relay_com, font=FONT,
                             width=8, relief="solid", bd=1,
                             highlightbackground=CLR["border"], highlightthickness=1)
        com_entry.grid(row=0, column=1, sticky="w", padx=(4, 8))

        # Baud row
        tk.Label(inner, text="Baud:", bg=CLR["panel_bg"],
                 font=FONT_BOLD, width=6, anchor="w").grid(row=0, column=2, sticky="w")
        self.sv_relay_baud = tk.StringVar()
        ttk.Combobox(inner, textvariable=self.sv_relay_baud,
                     values=["9600", "19200", "38400", "115200"],
                     font=FONT, width=7, state="normal").grid(row=0, column=3, sticky="w")

        # Apply button
        ttk.Button(inner, text="⚡ Apply", style="Accent.TButton",
                   command=self._apply_relay_settings).grid(row=1, column=0, columnspan=4,
                                                            sticky="w", pady=(6, 0))

        tk.Label(inner, text="Updates relaycontrol/relayon.py & relayoff.py",
                 bg=CLR["panel_bg"], fg="#9E9E9E",
                 font=(FONT_FAMILY, 7)).grid(row=2, column=0, columnspan=4, sticky="w", pady=(2, 0))

        self._update_relay_display()

    def _build_reports_panel(self, parent):
        outer = tk.Frame(parent, bg=CLR["bg"])
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="GENERATED REPORTS", bg=CLR["bg"], fg=CLR["accent"],
                 font=(FONT_FAMILY, 9, "bold")).pack(anchor="w", padx=2, pady=(0, 3))

        card = tk.Frame(outer, bg=CLR["panel_bg"], bd=1,
                        relief="solid",
                        highlightbackground=CLR["border"],
                        highlightthickness=1)
        card.pack(fill="both", expand=True)

        list_frame = tk.Frame(card, bg=CLR["panel_bg"])
        list_frame.pack(fill="both", expand=True, padx=6, pady=(6, 0))

        scrollbar = tk.Scrollbar(list_frame, orient="vertical")
        self._lb_reports = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            bg=CLR["panel_bg"],
            fg="#212121",
            selectbackground=CLR["accent"],
            selectforeground="white",
            font=(FONT_FAMILY, 8),
            relief="flat",
            bd=0,
            highlightthickness=0,
            activestyle="none",
        )
        scrollbar.config(command=self._lb_reports.yview)
        scrollbar.pack(side="right", fill="y")
        self._lb_reports.pack(side="left", fill="both", expand=True)
        self._lb_reports.bind("<Double-Button-1>", lambda _: self._open_report())

        btn_row = tk.Frame(card, bg=CLR["panel_bg"])
        btn_row.pack(fill="x", padx=6, pady=6)
        ttk.Button(btn_row, text="Open Report", style="Accent.TButton",
                   command=self._open_report).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="↺ Refresh", style="Accent.TButton",
                   command=self._refresh_reports).pack(side="left")

    # ------------------------------------------------------------------
    # Test Plan / Config Helpers
    # ------------------------------------------------------------------

    def _on_testplan_changed(self, *_):
        name = self.sv_testplan.get()
        ids = load_testplan_ids(name)
        all_opt = "— All Tests —"
        beg_opt = "— Beginning —"

        only_vals = [all_opt] + ids
        start_vals = [beg_opt] + ids

        self._cb_only["values"] = only_vals
        self._cb_start["values"] = start_vals
        self.sv_only_test.set(all_opt)
        self.sv_start_from.set(beg_opt)

        # Auto-select the matching product config in the selector
        cfg = load_product_config_for_plan(name)
        if cfg:
            pname = cfg.get("product_name", "")
            if pname in self._cb_cfg["values"]:
                self.sv_cfg_selector.set(pname)
                self._update_config_display(pname)
            else:
                self._update_config_display_from_cfg(cfg)
        else:
            self._clear_config_display()

        count = len(ids)
        self.sv_status.set(
            f"Loaded: {name}  —  {count} test{'s' if count != 1 else ''} found"
        )

    def _refresh_config_selector(self):
        """Repopulate the config selector dropdown from disk."""
        configs = list_product_configs()
        self._cb_cfg["values"] = configs
        # Keep current selection if still valid
        cur = self.sv_cfg_selector.get()
        if cur not in configs:
            if configs:
                self.sv_cfg_selector.set(configs[0])
                self._update_config_display(configs[0])
            else:
                self.sv_cfg_selector.set("")
                self._clear_config_display()
        # Update edit button state
        self._btn_edit_cfg.config(state="normal" if configs else "disabled")

    def _update_config_display(self, product_name: str):
        """Load config from disk by product name and render it."""
        if not product_name:
            self._clear_config_display()
            return
        cfg_path = PRODUCTCONFIGS_DIR / f"{product_name}.json"
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self._update_config_display_from_cfg(cfg)
        else:
            self._clear_config_display()

    def _update_config_display_from_cfg(self, cfg: dict):
        self._cfg_text.config(state="normal")
        self._cfg_text.delete("1.0", "end")

        fields = [
            ("Product",       cfg.get("product_name", "—")),
            ("ID Code",       cfg.get("id_code", "—")),
            ("RFP Device",    cfg.get("rfp_device", "—")),
            ("RFP Tool",      cfg.get("rfp_tool", "—")),
            ("RFP Interface", cfg.get("rfp_interface", "—")),
            ("COM Port",      f"COM{cfg.get('serial_port', '—')}"),
            ("Baud Rate",     str(cfg.get("serial_baud", "—"))),
            ("Board #",       str(cfg.get("board_number", "—"))),
        ]
        if cfg.get("ble_board_number") is not None:
            fields.append(("BLE Board #", str(cfg["ble_board_number"])))
        if cfg.get("wifi_board_number") is not None:
            fields.append(("WiFi Board #", str(cfg["wifi_board_number"])))

        exe_fields = [
            ("RFP EXE",      cfg.get("rfp_exe", "—")),
            ("JFlash EXE",   cfg.get("jflash_exe", "—")),
            ("JFlash Proj",  cfg.get("jflash_project", "—")),
            ("SelfProg EXE", cfg.get("selfprog_exe", "—")),
        ]

        for k, v in fields:
            self._cfg_text.insert("end", f"{k}:\n", "key")
            self._cfg_text.insert("end", f"  {v}\n", "val")
        self._cfg_text.insert("end", "\n")
        for k, v in exe_fields:
            self._cfg_text.insert("end", f"{k}:\n", "key")
            short = Path(v).name if v and v != "—" else v
            self._cfg_text.insert("end", f"  {short}\n", "val")

        self._cfg_text.config(state="disabled")

    def _clear_config_display(self):
        self._cfg_text.config(state="normal")
        self._cfg_text.delete("1.0", "end")
        self._cfg_text.insert("end", "No product config found.", "none")
        self._cfg_text.config(state="disabled")

    def _update_relay_display(self):
        """Read relay scripts and update the relay panel fields."""
        com, baud = get_relay_settings()
        self.sv_relay_com.set(com)
        self.sv_relay_baud.set(str(baud))

    def _apply_relay_settings(self):
        """Write the relay COM port / baud from the quick-set panel to both relay scripts."""
        com = self.sv_relay_com.get().strip().upper()
        if not re.match(r'^COM\d+$', com):
            messagebox.showerror("Invalid COM Port",
                                 "COM port must be in the form  COM<n>  (e.g. COM10).")
            return
        try:
            baud = int(self.sv_relay_baud.get().strip())
        except ValueError:
            messagebox.showerror("Invalid Baud Rate", "Baud rate must be an integer.")
            return
        try:
            set_relay_settings(com, baud)
            self.sv_status.set(f"Relay scripts updated  →  {com}  @  {baud} baud")
        except Exception as exc:
            messagebox.showerror("Error", f"Could not update relay scripts:\n{exc}")

    def _open_config_editor(self, mode: str):
        """Open the ProductConfigDialog. mode='edit' or 'new'."""
        if mode == "edit":
            product_name = self.sv_cfg_selector.get()
            if not product_name:
                messagebox.showinfo("No Config Selected",
                                    "Please select a product config from the dropdown first.")
                return
            ProductConfigDialog(self, mode="edit", product_name=product_name)
        else:
            ProductConfigDialog(self, mode="new", product_name=None)

    def _reload_testplans(self):
        plans = list_testplans()
        self._cb_testplan["values"] = plans
        current = self.sv_testplan.get()
        if current not in plans and plans:
            self.sv_testplan.set(plans[0])
            self._on_testplan_changed()
        self.sv_status.set(f"Reloaded test plans  —  {len(plans)} found")

    def _open_testplan_editor(self, mode: str):
        if mode == "edit":
            yaml_name = self.sv_testplan.get()
            if not yaml_name or not (TESTPLANS_DIR / yaml_name).exists():
                messagebox.showinfo(
                    "No Test Plan Selected",
                    "Please select a test plan from the dropdown to edit.",
                    parent=self,
                )
                return
            TestPlanDialog(self, mode="edit", yaml_name=yaml_name)
        else:
            TestPlanDialog(self, mode="new")

    def _delete_testplan(self):
        yaml_name = self.sv_testplan.get()
        if not yaml_name:
            messagebox.showinfo("No Test Plan Selected",
                                "Please select a test plan to delete.", parent=self)
            return
        path = TESTPLANS_DIR / yaml_name
        if not path.exists():
            messagebox.showerror("Not Found", f"'{yaml_name}' no longer exists.", parent=self)
            self._reload_testplans()
            return
        if not messagebox.askyesno(
            "Delete Test Plan",
            f"Permanently delete  '{yaml_name}'?\n\nThis cannot be undone.",
            icon="warning", parent=self
        ):
            return
        path.unlink()
        self._reload_testplans()
        self.sv_status.set(f"Deleted test plan: {yaml_name}")

    def _browse_testplan(self):
        path = filedialog.askopenfilename(
            title="Select Test Plan YAML",
            initialdir=str(TESTPLANS_DIR),
            filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")],
        )
        if not path:
            return
        p = Path(path)
        # If the file is inside the testplans/ folder, just show the name
        try:
            rel = p.relative_to(TESTPLANS_DIR)
            name = rel.name
            plans = list_testplans()
            if name not in plans:
                plans.append(name)
                plans.sort()
            self._cb_testplan["values"] = plans
            self.sv_testplan.set(name)
        except ValueError:
            # File is outside the testplans folder — use full path
            plans = self._cb_testplan["values"]
            if str(p) not in plans:
                updated = list(plans) + [str(p)]
                self._cb_testplan["values"] = updated
            self.sv_testplan.set(str(p))

        self._on_testplan_changed()

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    def _refresh_reports(self):
        self._lb_reports.delete(0, "end")
        for name in list_reports():
            self._lb_reports.insert("end", name)

    def _open_report(self):
        sel = self._lb_reports.curselection()
        if not sel:
            messagebox.showinfo("Open Report", "Please select a report from the list.")
            return
        name = self._lb_reports.get(sel[0])
        path = REPORTS_DIR / name
        if not path.exists():
            messagebox.showerror("Not Found", f"Report file not found:\n{path}")
            return
        os.startfile(str(path))

    # ------------------------------------------------------------------
    # Run / Stop
    # ------------------------------------------------------------------

    def _build_command(self) -> list[str]:
        """Construct the runtestplan.py command from UI selections."""
        yaml_name = self.sv_testplan.get().strip()
        if not yaml_name:
            raise ValueError("No test plan selected.")

        # Determine YAML path — could be a name in testplans/ or an absolute path
        p = Path(yaml_name)
        if p.is_absolute() and p.exists():
            yaml_path = str(p)
        else:
            yaml_path = str(TESTPLANS_DIR / yaml_name)

        cmd = [sys.executable, str(ROOT / "runtestplan.py"), yaml_path]

        only_test = self.sv_only_test.get()
        if only_test and not only_test.startswith("—"):
            cmd += ["--only-test", only_test]

        start_from = self.sv_start_from.get()
        if start_from and not start_from.startswith("—"):
            # --only-test takes priority; don't set both
            if only_test.startswith("—"):
                cmd += ["--start-from", start_from]

        try:
            repeat = int(self.sv_repeat.get())
            if repeat > 1:
                cmd += ["--repeat", str(repeat)]
        except ValueError:
            pass

        email = self.sv_email.get().strip()
        if email:
            cmd += ["--send-report-to", email]

        return cmd

    def _start_run(self):
        try:
            cmd = self._build_command()
        except ValueError as e:
            messagebox.showerror("Configuration Error", str(e))
            return

        self._console_append("\n" + "=" * 70 + "\n", "header")
        self._console_append("  STARTING TEST RUN\n", "header")
        self._console_append("  Command: " + " ".join(cmd) + "\n", "dim")
        self._console_append("=" * 70 + "\n\n", "header")

        self._btn_run.config(state="disabled")
        self._btn_stop.config(state="normal")
        self._progress.start(10)
        self.sv_status.set("Running…")

        self._run_thread = threading.Thread(
            target=self._run_subprocess, args=(cmd,), daemon=True)
        self._run_thread.start()

        self._polling = True
        self._poll_output()

    def _stop_run(self):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._console_append("\n[GUI] Stop requested — process terminated.\n", "warn")
            except Exception as e:
                self._console_append(f"\n[GUI] Could not terminate process: {e}\n", "fail")
        self._btn_stop.config(state="disabled")

    def _run_subprocess(self, cmd: list[str]):
        """Runs in a worker thread. Puts lines into the output queue."""
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(ROOT),
                shell=False,
            )
            for line in self._proc.stdout:
                self._output_queue.put(line)
            self._proc.wait()
        except Exception as exc:
            self._output_queue.put(f"[GUI ERROR] {exc}\n")
        finally:
            self._output_queue.put(None)  # Sentinel

    def _poll_output(self):
        """Called periodically on the main thread to drain the output queue."""
        try:
            while True:
                line = self._output_queue.get_nowait()
                if line is None:
                    # Run finished
                    self._on_run_finished()
                    return
                self._console_append_auto(line)
        except queue.Empty:
            pass

        if self._polling:
            self.after(80, self._poll_output)

    def _on_run_finished(self):
        self._polling = False
        self._progress.stop()
        self._btn_run.config(state="normal")
        self._btn_stop.config(state="disabled")
        rc = self._proc.returncode if self._proc else "?"
        self._console_append(f"\n{'='*70}\n", "header")
        self._console_append(f"  Run finished  (exit code: {rc})\n", "header")
        self._console_append(f"{'='*70}\n", "header")
        self.sv_status.set(f"Finished  —  exit code: {rc}")
        self._refresh_reports()

    # ------------------------------------------------------------------
    # Console Output
    # ------------------------------------------------------------------

    def _tag_for_line(self, line: str) -> str:
        """Heuristic colour tag based on line content."""
        low = line.lower()
        if any(k in low for k in ("✓ passed", "all tests completed", "ok — report generated")):
            return "pass"
        if any(k in low for k in ("✗ failed", "[error]", "error_occurred", "completed with errors")):
            return "fail"
        if any(k in low for k in ("[warn]", "[retry]", "failed, retrying", "[info]")):
            return "warn"
        if any(k in low for k in (">>> test:", "run ", "===")):
            return "header"
        if any(k in low for k in ("[*]", "[ok]", "report generated", "log files deleted")):
            return "info"
        return ""

    def _console_append_auto(self, line: str):
        tag = self._tag_for_line(line)
        self._console_append(line, tag)

    def _console_append(self, text: str, tag: str = ""):
        self._console.config(state="normal")
        if tag:
            self._console.insert("end", text, tag)
        else:
            self._console.insert("end", text)
        self._console.see("end")
        self._console.config(state="disabled")

    def _clear_console(self):
        self._console.config(state="normal")
        self._console.delete("1.0", "end")
        self._console.config(state="disabled")

    # ------------------------------------------------------------------
    # Window Close
    # ------------------------------------------------------------------

    def _on_close(self):
        if self._proc and self._proc.poll() is None:
            if not messagebox.askyesno(
                "Tests Running",
                "A test run is in progress.\nDo you want to stop it and exit?",
            ):
                return
            try:
                self._proc.terminate()
            except Exception:
                pass
        self._polling = False
        self.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
