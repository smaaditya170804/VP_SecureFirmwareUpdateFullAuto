# -*- coding: utf-8 -*-
"""
Wraps SelfProg_Tool.exe to program a BIN file in four steps:
  1) /c <COM>
  2) /baudrate -download <BAUD>
  3) /setboardnumber <BOARD>
  4) /d -file "<BIN>" [-backend]

Example (PowerShell line breaks use backtick ` ):
  python .\selfprog_flash.py `
    --exe "C:\GBP_Testing\Release_Test\Release_Test\SelfProg_Tool.exe" `
    --port 8 `
    --baud 38400 `
    --board 48 `
    --bin  "C:\path\to\file.bin" `
    --backend
"""

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path


def run_step(cmd: list[str], logf) -> int:
    """Run one SelfProg_Tool.exe command, stream to console and log."""
    print("\n>>>", " ".join(f'"{c}"' if " " in c else c for c in cmd))
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, shell=False
        )
    except FileNotFoundError:
        print("[ERROR] SelfProg_Tool.exe not found. Check --exe path.")
        return 127

    # Stream output
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        print(line, end="")
        logf.write(line)

    proc.wait()
    rc = proc.returncode
    print(f"[STEP EXIT CODE] {rc}")
    logf.write(f"[STEP EXIT CODE] {rc}\n")
    logf.flush()
    return rc


def main():
    ap = argparse.ArgumentParser(description="SelfProgrammer PC Tool wrapper")
    ap.add_argument("--exe", required=True, help="Full path to SelfProg_Tool.exe")
    ap.add_argument("--port", type=int, required=True, help="COM port number (e.g., 8)")
    ap.add_argument("--baud", type=int, required=True, help="Download baud rate (e.g., 38400)")
    ap.add_argument("--board", type=int, required=True, help="FEBE board number (e.g., 48)")
    ap.add_argument("--bin", required=True, help="Path to .bin file to download")
    ap.add_argument("--backend", action="store_true", help="Append -backend to /d step")
    ap.add_argument("--logdir", default="logs", help="Folder for logs (default: logs)")
    args = ap.parse_args()

    exe = Path(args.exe)
    image = Path(args.bin)

    if not exe.exists():
        print(f"[ERROR] Executable not found: {exe}")
        sys.exit(2)
    if not image.exists():
        print(f"[ERROR] BIN file not found: {image}")
        sys.exit(2)

    Path(args.logdir).mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = Path(args.logdir) / f"selfprog_{stamp}.log"

    print("=== SelfProgrammer Wrapper ===================================")
    print(f"[INFO] EXE   : {exe}")
    print(f"[INFO] COM   : {args.port}")
    print(f"[INFO] BAUD  : {args.baud}")
    print(f"[INFO] BOARD : {args.board}")
    print(f"[INFO] BIN   : {image}")
    print(f"[INFO] Log   : {log_path}")
    print("==============================================================\n")

    rc = 0
    with open(log_path, "w", encoding="utf-8") as logf:
        # 1) set COM port
        rc = run_step([str(exe), "/c", str(args.port)], logf)
        if rc != 0:
            print(f"[FAIL] Step /c failed. Log: {log_path}")
            sys.exit(rc)

        # 2) set download baudrate
        rc = run_step([str(exe), "/baudrate", "-download", str(args.baud)], logf)
        if rc != 0:
            print(f"[FAIL] Step /baudrate -download failed. Log: {log_path}")
            sys.exit(rc)

        # 3) set board number
        rc = run_step([str(exe), "/setboardnumber", str(args.board)], logf)
        if rc != 0:
            print(f"[FAIL] Step /setboardnumber failed. Log: {log_path}")
            sys.exit(rc)

        # 4) download
        dl_cmd = [str(exe), "/d", "-file", str(image)]
        if args.backend:
            dl_cmd.append("-backend")

        rc = run_step(dl_cmd, logf)
        # Done

    if rc == 0:
        print(f"\n[SUCCESS] Programming finished OK. Log: {log_path}")
    else:
        print(f"\n[FAIL] Programming returned {rc}. See log: {log_path}")
    sys.exit(rc)


if __name__ == "__main__":
    main()