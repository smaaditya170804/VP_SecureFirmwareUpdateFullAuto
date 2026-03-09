# -*- coding: utf-8 -*-
r"""
selfprogflagcheckparser.py
Parses two SelfProg_Tool /readflag logs and prints a compact table.

It extracts:
  - FwUpdate_req
  - FwUpdate_frez
  - FwUpdate_actbin
  - FwUpdate_rollbk
  - SelfProg Error Code
  - Current Firmware Version (computed from actbin and Version*/BuildNumber*)

Usage:
    python .\selfprogflagcheckparser.py --after-download <log1> --after-reset <log2>
"""

import argparse
import re
from pathlib import Path
from typing import Dict, Tuple

FIELD_KEYS = [
    "FwUpdate_req",
    "FwUpdate_frez",
    "FwUpdate_actbin",
    "FwUpdate_rollbk",
    "SelfProg Error Code",
]

# Regex helpers for lines like:
#   FwUpdate_req    : 1
#   Version0-X      : 2
#   BuildNumber0-X  : 00001
#   SelfProg Error Code     : 0x000000AF (FWU_SUCCESS)
LINE_RE = re.compile(r"^\s*([A-Za-z0-9 _\-]+?)\s*:\s*(.+?)\s*$", re.MULTILINE)


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def parse_pairs(text: str) -> Dict[str, str]:
    data: Dict[str, str] = {}
    for m in LINE_RE.finditer(text or ""):
        key = m.group(1).strip().replace("\t", " ")
        val = m.group(2).strip()
        data[key] = val
    return data


def to_int(val: str, default: int = 0) -> int:
    if val is None:
        return default
    s = val.strip()
    # Handle hex like 0x000000AF
    if s.lower().startswith("0x"):
        try:
            return int(s, 16)
        except Exception:
            return default
    # plain integer
    try:
        return int(s)
    except Exception:
        return default


def extract_version(data: Dict[str, str]) -> Tuple[str, int]:
    """
    Decide active version using FwUpdate_actbin:
      if 0 -> use Version0-X/Y/Z and BuildNumber0-X
      if 1 -> use Version1-X/Y/Z and BuildNumber1-X
    Returns (version_string, actbin)
    """
    actbin = to_int(data.get("FwUpdate_actbin"), 0)

    if actbin == 0:
        vx = to_int(data.get("Version0-X"), 0)
        vy = to_int(data.get("Version0-Y"), 0)
        vz = to_int(data.get("Version0-Z"), 0)
        bn = data.get("BuildNumber0-X", "00000").strip()
    else:
        vx = to_int(data.get("Version1-X"), 0)
        vy = to_int(data.get("Version1-Y"), 0)
        vz = to_int(data.get("Version1-Z"), 0)
        bn = data.get("BuildNumber1-X", "00000").strip()

    # Keep build as provided (preserves leading zeros)
    version = f"{vx}.{vy}.{vz}.{bn}"
    return version, actbin


def extract_selfprog_error(data: Dict[str, str]) -> str:
    """
    From a line like 'SelfProg Error Code : 0x000000AF (FWU_SUCCESS)',
    keep both the hex and the mnemonic if present.
    """
    raw = data.get("SelfProg Error Code", "")
    # already contains hex + (text) usually; normalize spaces
    return " ".join(raw.split())


def make_table(rows):
    """
    Very small table printer: compute column widths and render.
    rows: list of [field, after_download, after_reset]
    """
    col_w = [0, 0, 0]
    for r in rows:
        for i, cell in enumerate(r):
            col_w[i] = max(col_w[i], len(cell))

    sep = "+-" + "-+-".join("-" * w for w in col_w) + "-+"
    def row_fmt(vals):
        return "| " + " | ".join(v.ljust(col_w[i]) for i, v in enumerate(vals)) + " |"

    out = []
    out.append(sep)
    out.append(row_fmt(["Field", "After Download", "After Reset"]))
    out.append(sep)
    for r in rows:
        out.append(row_fmt(r))
    out.append(sep)
    return "\n".join(out)


def summarize(ad_path: Path, ar_path: Path, expected_flags: Dict = None) -> Tuple[int, bool]:
    ad_text = load_text(ad_path)
    ar_text = load_text(ar_path)
    if not ad_text:
        print(f"[ERROR] Could not read {ad_path}")
        return 2, False
    if not ar_text:
        print(f"[ERROR] Could not read {ar_path}")
        return 2, False

    ad = parse_pairs(ad_text)
    ar = parse_pairs(ar_text)

    # Compute versions
    v_ad, actbin_ad = extract_version(ad)
    v_ar, actbin_ar = extract_version(ar)

    # Build the table rows
    rows = []

    for k in FIELD_KEYS:
        rows.append([
            k,
            ad.get(k, "—"),
            ar.get(k, "—"),
        ])

    rows.append(["Active Bin (computed)", str(actbin_ad), str(actbin_ar)])
    rows.append(["Current FW Version", v_ad, v_ar])
    rows.append(["Log Parsed From", str(ad_path.name), str(ar_path.name)])

    print("\nSelfProgrammer Flags Summary\n")
    print(make_table(rows))
    print("\nNotes:")
    print(" - 'Current FW Version' is derived from FwUpdate_actbin and Version*/BuildNumber* fields.")
    print(" - Values shown exactly as reported by the device/logs.\n")
    
    # Check if test passed by comparing with expected flags
    test_passed = True
    if expected_flags:
        print("\nExpected Flags After Reset Comparison\n")
        expected_rows = []
        for field_key, expected_val in expected_flags.items():
            # Try to find the field in ar_data, handling different case variations
            actual_val = "—"
            for key in ar.keys():
                if key.replace(" ", "").lower() == field_key.replace(" ", "").lower():
                    actual_val = ar[key]
                    break
            
            matches = normalize_flag_value(actual_val) == normalize_flag_value(str(expected_val))
            status = "✓" if matches else "✗"
            expected_rows.append([field_key, str(expected_val), actual_val, status])
            if not matches:
                test_passed = False
        
        print(make_expected_table(expected_rows))
    
    return 0, test_passed


def normalize_flag_value(val: str) -> str:
    """Normalize flag values for comparison (handle hex, decimals, etc)."""
    if not val or val == "—":
        return val
    
    val = val.strip()
    
    # Handle error codes with mnemonics (0x000000AF (FWU_SUCCESS) -> 175)
    if "(" in val and ")" in val:
        # Extract just the hex part before the mnemonic
        parts = val.split("(")
        hex_part = parts[0].strip()
        if hex_part.upper().startswith("0X"):
            try:
                hex_val = int(hex_part, 16)
                return str(hex_val)
            except Exception:
                pass
        return val.upper()
    
    # Handle hex values (0x000000AF -> 175 in decimal for numeric comparison)
    if val.upper().startswith("0X"):
        try:
            hex_val = int(val, 16)
            return str(hex_val)
        except Exception:
            return val.upper()
    
    # For regular integer/string comparison, normalize to uppercase for consistency
    return val.upper()


def make_expected_table(rows):
    """
    Print table for expected vs actual flag comparison.
    rows: list of [field, expected, actual, status]
    """
    col_w = [0, 0, 0, 0]
    for r in rows:
        for i, cell in enumerate(r):
            col_w[i] = max(col_w[i], len(cell))

    sep = "+-" + "-+-".join("-" * w for w in col_w) + "-+"
    def row_fmt(vals):
        return "| " + " | ".join(v.ljust(col_w[i]) for i, v in enumerate(vals)) + " |"

    out = []
    out.append(sep)
    out.append(row_fmt(["Field", "Expected", "Actual", "Match"]))
    out.append(sep)
    for r in rows:
        out.append(row_fmt(r))
    out.append(sep)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Parse two /readflag logs and display a summary table")
    ap.add_argument("--after-download", required=True, help="Path to 'after download' /readflag log")
    ap.add_argument("--after-reset", required=True, help="Path to 'after reset' /readflag log")
    ap.add_argument("--expected-flags", type=str, default=None, 
                    help="JSON string of expected flags after reset for pass/fail comparison")
    args = ap.parse_args()
    
    expected_flags = None
    if args.expected_flags:
        try:
            import json
            expected_flags = json.loads(args.expected_flags)
        except Exception as e:
            print(f"[WARN] Could not parse expected flags JSON: {e}")
    
    returncode, test_passed = summarize(Path(args.after_download), Path(args.after_reset), expected_flags)
    raise SystemExit(returncode)


if __name__ == "__main__":
    main()