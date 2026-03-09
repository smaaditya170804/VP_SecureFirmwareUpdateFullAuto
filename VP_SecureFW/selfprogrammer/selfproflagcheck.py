# -*- coding: utf-8 -*-
"""
selfproflagcheck.py
Runs SelfProg_Tool.exe flag checks:
  - /readflag  --> "after download"
  - optional /install (if --install is specified)
  - /readflag  --> "after reset" (either after /install or after you manually reset)

Immediately invokes selfprogflagcheckparser.py to parse and print a table.

Usage (PowerShell; backtick is line continuation):
  python .\selfproflagcheck.py `
    --exe "C:\GBP_Testing\Release_Test\Release_Test\SelfProg_Tool.exe" `
    --logdir ".\logs" `
    --install `
    --wait 6 `          # seconds to wait before the 2nd /readflag
    --retries 5 `       # how many times to retry the 2nd /readflag
    --interval 2        # seconds between retries

If you do NOT want the script to send /install, omit --install.
In that case, it will pause and ask you to reset the device manually before the 2nd /readflag.
"""

import argparse
import datetime as dt
import subprocess
import sys
import time
from pathlib import Path

THIS_PY = Path(__file__).resolve()
PARSER = THIS_PY.with_name("selfprogflagcheckparser.py")


def run_and_capture(cmd, out_path, quiet=False):
    """Run a command, capture stdout/stderr to file and return (rc, text)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not quiet:
        print("\n>>>", " ".join(f'"{c}"' if " " in c else c for c in cmd))
    try:
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=False,
        )
    except FileNotFoundError:
        msg = f"[ERROR] Not found: {cmd[0]}"
        if not quiet:
            print(msg)
        out_path.write_text(msg, encoding="utf-8")
        return 127, msg

    lines = []
    with out_path.open("w", encoding="utf-8") as f:
        while True:
            line = p.stdout.readline()
            if not line:
                break
            if not quiet:
                print(line, end="")
            f.write(line)
            lines.append(line)
        p.wait()
        rc = p.returncode
        f.write(f"\n[EXIT CODE] {rc}\n")
    return rc, "".join(lines)


def looks_like_valid_flag_dump(text: str) -> bool:
    """Heuristic: did we really get a flags section?"""
    needles = [
        "Flag Information",
        "FwUpdate_req",
        "FwUpdate_frez",
        "FwUpdate_actbin",
        "Version0-X",
        "Version1-X",
        "SelfProg Error Code",
    ]
    t = text or ""
    return all(n in t for n in needles)


def main():
    ap = argparse.ArgumentParser(description="SelfProgrammer: read flags before/after reset and parse")
    ap.add_argument("--exe", required=True, help="Full path to SelfProg_Tool.exe")
    ap.add_argument("--logdir", default="logs", help="Directory for logs (default: logs)")
    ap.add_argument("--install", action="store_true",
                    help="Send /install between the two /readflag operations")
    ap.add_argument("--wait", type=int, default=6,
                    help="Seconds to wait after /install before 2nd /readflag (default: 6)")
    ap.add_argument("--retries", type=int, default=5,
                    help="Retries for 2nd /readflag (default: 5)")
    ap.add_argument("--interval", type=int, default=2,
                    help="Seconds between retries (default: 2)")
    ap.add_argument("--quiet", action="store_true",
                    help="Suppress tool output (only show final table)")
    args = ap.parse_args()

    exe = str(Path(args.exe))
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    logdir = Path(args.logdir)
    after_dl = logdir / f"readflag_after_download_{ts}.log"
    after_reset = logdir / f"readflag_after_reset_{ts}.log"
    install_log = logdir / f"install_{ts}.log"

    if not args.quiet:
        print("=== SelfProg Flag Check =======================================")
        print(f"[INFO] EXE   : {exe}")
        print(f"[INFO] Logs  : {logdir.resolve()}")
        print("===============================================================\n")

    # 1) /readflag  --> after download
    rc1, text1 = run_and_capture([exe, "/readflag"], after_dl, quiet=args.quiet)
    if rc1 != 0:
        if not args.quiet:
            print(f"\n[FAIL] /readflag failed (after download). See {after_dl}")
        # still attempt to parse what we have
    else:
        if not args.quiet:
            print(f"\n[OK] Saved 'after download' flags to {after_dl}")

    # 2) optional /install
    if args.install:
        rc_inst, _ = run_and_capture([exe, "/install"], install_log, quiet=args.quiet)
        if rc_inst != 0 and not args.quiet:
            print(f"[WARN] /install returned {rc_inst}. See {install_log}")
        # brief wait, then retries for 2nd readflag
        time.sleep(max(0, args.wait))

        text2 = ""
        rc2 = 1
        for i in range(max(1, args.retries)):
            rc2, text2 = run_and_capture([exe, "/readflag"], after_reset, quiet=args.quiet)
            if looks_like_valid_flag_dump(text2):
                break
            if not args.quiet:
                print(f"[INFO] 2nd /readflag did not look complete, retry {i+1}/{args.retries} …")
            time.sleep(max(1, args.interval))
    else:
        input("\n[Action] Reset/Power-cycle the device now, then press <Enter> to continue … ")
        rc2, text2 = run_and_capture([exe, "/readflag"], after_reset, quiet=args.quiet)

    if rc2 != 0:
        if not args.quiet:
            print(f"\n[WARN] /readflag failed (after reset). See {after_reset}")
    else:
        if not args.quiet:
            print(f"\n[OK] Saved 'after reset' flags to {after_reset}")

    # 3) Invoke the parser immediately
    if not args.quiet:
        print("\n=== Parsing and summarizing results ===\n")
    try:
        # use the same python interpreter
        cmd = [sys.executable, str(PARSER), "--after-download", str(after_dl), "--after-reset", str(after_reset)]
        p = subprocess.run(cmd, check=False)
        sys.exit(p.returncode)
    except FileNotFoundError:
        print(f"[ERROR] Parser not found: {PARSER}")
        print("Copy selfprogflagcheckparser.py next to this script.")
        sys.exit(127)


if __name__ == "__main__":
    main()