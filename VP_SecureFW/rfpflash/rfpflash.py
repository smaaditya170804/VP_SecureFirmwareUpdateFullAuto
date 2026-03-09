# -*- coding: utf-8 -*-
"""
Flash an RX device using Renesas Flash Programmer CLI (rfp-cli.exe)

Example:
    python flash_rx.py ^
        --rfp "C:\\Program Files (x86)\\Renesas Electronics\\Programming Tools\\Renesas Flash Programmer V3.21\\rfp-cli.exe" ^
        --device RX65x --tool e2l --interface fine ^
        --file "C:\\path\\to\\image.srec" ^
        --id 45D6136794F8BA46F7B3435164E0DA29 ^
        --run

If RFP is already in PATH, you can omit --rfp.
"""

import argparse
import datetime as _dt
import os
import subprocess
import sys
from pathlib import Path

def build_cmd(args) -> list[str]:
    cmd = []

    # rfp-cli.exe
    rfp = args.rfp or "rfp-cli.exe"
    cmd.append(rfp)

    # Required options (based on your working command)
    #   -device RX65x
    #   -tool e2l
    #   -if fine
    #   -file "<srec>"
    #   -a (auto)
    #   -run (optional)
    #   and it will prompt for ID code - we pass it via stdin.
    cmd.extend(["-device", args.device])
    cmd.extend(["-tool", args.tool])
    cmd.extend(["-if", args.interface])
    cmd.extend(["-file", args.file])
    if args.auto:
        cmd.append("-a")
    if args.run:
        cmd.append("-run")

    return cmd


def main():
    parser = argparse.ArgumentParser(description="Flash RX with Renesas Flash Programmer CLI")
    parser.add_argument("--rfp", help="Full path to rfp-cli.exe (omit if in PATH)")
    parser.add_argument("--device", default="RX65x", help="Device family (default: RX65x)")
    parser.add_argument("--tool", default="e2l", help="Tool name (e.g. e2l for E2 emulator Lite)")
    parser.add_argument("--interface", default="fine", help="Interface (e.g. fine)")
    parser.add_argument("--file", required=True, help="Path to .srec / .mot / .hex image")
    parser.add_argument("--id", required=True, help="16-byte ID Code in hex, no spaces")
    parser.add_argument("--auto", action="store_true", default=True, help="Use -a (auto) [default on]")
    parser.add_argument("--run", action="store_true", help="Execute target after programming (-run)")
    parser.add_argument("--logdir", default="logs", help="Directory to write logs")
    parser.add_argument("--baud", type=int, help="Optional: override RFP speed (bps)")
    args = parser.parse_args()

    # Validate inputs
    image = Path(args.file)
    if not image.exists():
        print(f"[ERROR] Image file not found: {image}")
        sys.exit(2)

    if len(args.id) != 32 or any(ch not in "0123456789abcdefABCDEF" for ch in args.id):
        print("[ERROR] --id must be 32 hex characters (16 bytes). Example: 45D6...DA29")
        sys.exit(2)

    # Build command
    cmd = build_cmd(args)

    # Prepare logging
    Path(args.logdir).mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = Path(args.logdir) / f"rfp_{stamp}.log"

    print("=== RFP CLI command ===========================================")
    print(" ".join(f'"{c}"' if " " in c else c for c in cmd))
    print("===============================================================")
    print(f"[INFO] Image : {image}")
    print(f"[INFO] ID    : {args.id}")
    print(f"[INFO] Log   : {log_path}\n")

    # The CLI prompts: "Enter ID Code (16 Bytes)? "
    # We'll provide it via stdin with a trailing newline.
    id_code_line = (args.id + "\n").encode("ascii")

    # If you need to force a specific speed, RFP GUI sets bps.
    # rfp-cli has no direct "-speed" option in older releases; if your environment
    # requires it, define that in the RFP project settings or tool config beforehand.

    # Launch process
    with open(log_path, "wb") as logf:
        try:
            # Stream output live AND log it.
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,   # keep bytes, we will decode per line
                shell=False
            )

            # Send ID code once the tool prompts; simplest is to just send up front.
            # RFP will buffer until it needs it.
            proc.stdin.write(id_code_line)
            proc.stdin.flush()

            # Read output line-by-line
            while True:
                buf = proc.stdout.readline()
                if not buf:
                    break
                # echo to console
                try:
                    line = buf.decode("utf-8", errors="replace")
                except Exception:
                    line = str(buf)
                print(line, end="")
                # write to log
                logf.write(buf)
                logf.flush()

            proc.wait()

        except FileNotFoundError:
            print("[ERROR] rfp-cli.exe not found. Add it to PATH or pass --rfp \"C:\\path\\to\\rfp-cli.exe\"")
            sys.exit(127)

    rc = proc.returncode
    if rc == 0:
        print(f"\n[SUCCESS] RFP CLI finished OK. Log: {log_path}")
    else:
        print(f"\n[FAIL] RFP CLI returned {rc}. See log: {log_path}")
    sys.exit(rc)


if __name__ == "__main__":
    main()