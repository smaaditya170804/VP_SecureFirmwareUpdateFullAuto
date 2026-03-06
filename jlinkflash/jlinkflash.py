# -*- coding: utf-8 -*-
"""
Flash SPI NOR using SEGGER J-Flash SPI Command Line (JFlashSPI_CL.exe)

Example (same as your CMD):
    python flash_spi.py ^
      --jflash "C:\\Program Files\\SEGGER\\JLink\\JFlashSPI_CL.exe" ^
      --project "C:\\Software\\J-Flash SPI_Projects\\V9.12\\jlinkflash.jflash" ^
      --image  "C:\\GBP_Testing\\bbGBP-IEC-62443-4-2_binaries-prerelease-V43.34.01.00026\\Releases\\SaVerAdvPlus_SB_binaries\\VP_SET_1\\11122244V02.01.00.00001_R_K_TSIP_BL_02_01_00_00001_EXT_UpdPkg.bin" ^
      --addr 0x0 --erasechip --programverify --connect
"""

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

def build_cmd(a: argparse.Namespace) -> list[str]:
    """
    Compose JFlashSPI_CL command line equivalent to:
    JFlashSPI_CL.exe -openprj"...\jlinkflash.jflash" -connect -erasechip \
                     -open <image> <addr> -programverify
    """
    exe = a.jflash or "JFlashSPI_CL.exe"
    cmd = [exe]

    # open the project first (creates Default.jflash if not present)
    cmd += ["-openprj", a.project]

    if a.connect:
        cmd += ["-connect"]

    if a.erasechip:
        cmd += ["-erasechip"]

    # open image and base address
    cmd += ["-open", a.image, hex(a.addr).lower()]

    if a.programverify:
        cmd += ["-programverify"]
    elif a.program:
        cmd += ["-program"]

    # Optional close (CLI usually closes automatically)
    if a.closeprj:
        cmd += ["-closeprj"]

    return cmd


def main():
    p = argparse.ArgumentParser(description="SEGGER J-Flash SPI CLI wrapper")
    p.add_argument("--jflash", help="Full path to JFlashSPI_CL.exe (omit if in PATH)")
    p.add_argument("--project", required=True, help="Path to .jflash project")
    p.add_argument("--image",   required=True, help="Path to .bin/.hex/.mot image")
    p.add_argument("--addr",    type=lambda x: int(x, 0), default=0x0, help="Base address (e.g., 0x0)")
    p.add_argument("--connect", action="store_true", help="Add -connect")
    p.add_argument("--erasechip", action="store_true", help="Add -erasechip")
    p.add_argument("--program", action="store_true", help="Add -program (if you don't want verify)")
    p.add_argument("--programverify", action="store_true", default=True,
                   help="Add -programverify (default)")
    p.add_argument("--closeprj", action="store_true", help="Add -closeprj at end")
    p.add_argument("--logdir", default="logs", help="Folder for logs")
    args = p.parse_args()

    # Basic checks
    proj = Path(args.project)
    img  = Path(args.image)
    if not proj.exists():
        print(f"[ERROR] Project file not found: {proj}")
        sys.exit(2)
    if not img.exists():
        print(f"[ERROR] Image not found: {img}")
        sys.exit(2)

    # Build command
    cmd = build_cmd(args)

    # Prepare log
    Path(args.logdir).mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = Path(args.logdir) / f"jflashspi_{stamp}.log"

    print("=== J-Flash SPI CLI command ===============================")
    print(" ".join(f'"{c}"' if " " in c else c for c in cmd))
    print("===========================================================")
    print(f"[INFO] Project : {proj}")
    print(f"[INFO] Image   : {img}")
    print(f"[INFO] Address : 0x{args.addr:08X}")
    print(f"[INFO] Log     : {log_path}\n")

    # Launch and stream output
    try:
        with open(log_path, "wb") as logf:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,   # keep bytes, we will decode safely
                shell=False
            )

            while True:
                chunk = proc.stdout.readline()
                if not chunk:
                    break
                line = chunk.decode("utf-8", errors="replace")
                print(line, end="")
                logf.write(chunk)
                logf.flush()

            proc.wait()

    except FileNotFoundError:
        print("[ERROR] JFlashSPI_CL.exe not found. Pass --jflash or add to PATH.")
        sys.exit(127)

    rc = proc.returncode
    if rc == 0:
        print(f"\n[SUCCESS] J-Flash SPI finished OK. Log: {log_path}")
    else:
        print(f"\n[FAIL] J-Flash SPI returned {rc}. See log: {log_path}")
    sys.exit(rc)


if __name__ == "__main__":
    main()