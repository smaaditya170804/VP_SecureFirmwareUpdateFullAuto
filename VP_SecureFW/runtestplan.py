# -*- coding: utf-8 -*-
"""
C:\VP_SecureFW\runtestplan.py

Universal testplan runner implementing the exact flows demonstrated by Mithun:

CASE A: SREC present + delivery_method: JFlash
    1) RFP flash SREC
    2) Relay ON
    3) J-Flash update package (jlinkflash.py handles reconnect+readchip+relay-off)
    4) SelfProg flag check with --install

CASE B: delivery_method: SelfProgrammer (NO SREC)
    1) SelfProgrammer download update package
    2) SelfProg flag check with --install

CASE C: delivery_method: InstallOnly (NO SREC)
    1) SelfProg flag check with --install

CASE D: delivery_method: JFlash (NO SREC)
    1) Relay ON
    2) J-Flash update package
    3) SelfProg flag check with --install

Usage:
    python runtestplan.py <path_to_yaml_testplan>

Notes:
- Looks for optional product config JSON at:
    productconfigs/<ProductName>.json
  If missing, uses built-in defaults based on your transcripts.
"""

import sys
import subprocess
from pathlib import Path
import json

# --- YAML dependency (PyYAML) ------------------------------------------------
try:
    import yaml  # pip install pyyaml
except ImportError:
    print("[ERROR] PyYAML is required. Please run:  pip install pyyaml")
    sys.exit(1)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent

def run_cmd(cmd_list, cwd=None, stop_on_error=True, echo=True):
    """Run a command (list form). Returns exit code, optionally aborts on error."""
    if echo:
        here = f"(cwd: {cwd})" if cwd else ""
        pretty = " ".join(f'"{c}"' if " " in str(c) else str(c) for c in cmd_list)
        print(f"\n>>> {pretty} {here}".strip())
    rc = subprocess.call(cmd_list, cwd=str(cwd) if cwd else None, shell=False)
    if stop_on_error and rc != 0:
        print(f"[FAIL] Command returned {rc}. Aborting.")
        sys.exit(rc)
    return rc

def load_yaml(yaml_path: Path):
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"[ERROR] Failed to read YAML: {yaml_path}\n{e}")
        sys.exit(2)

def detect_product_name(testplan_name: str) -> str:
    # Heuristic: first token of the 'name' is the product (e.g., "SaverAdvPlus VP Firmware...")
    return (testplan_name or "SaverAdvPlus").split()[0]

def load_product_config(product_name: str) -> dict:
    cfg_path = ROOT / "productconfigs" / f"{product_name}.json"
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            print(f"[INFO] Loaded product config: {cfg_path}")
            return cfg

    # Fallback defaults (from your commands)
    print("[WARN] Product config JSON not found. Using built-in defaults.")
    return {
        "product_name": product_name,
        "id_code": "45D6136794F8BA46F7B3435164E0DA29",
        "rfp_device": "RX65x",
        "rfp_tool": "e2l",
        "rfp_interface": "fine",
        "rfp_exe": r"C:\Program Files (x86)\Renesas Electronics\Programming Tools\Renesas Flash Programmer V3.21\rfp-cli.exe",
        "jflash_exe": r"C:\Program Files\SEGGER\JLink\JFlashSPI_CL.exe",
        "jflash_project": r"C:\Software\J-Flash SPI_Projects\V9.12\jlinkflash.jflash",
        "selfprog_exe": r"C:\GBP_Testing\Release_Test\Release_Test\SelfProg_Tool.exe",
        "serial_port": 8,
        "serial_baud": 38400,
        "board_number": 48
    }

# -----------------------------------------------------------------------------
# Flows
# -----------------------------------------------------------------------------
def rfp_flash_srec(cfg: dict, srec_path: str):
    """RFP flash the SREC image (Case A: step 1)."""
    script = ROOT / "rfpflash" / "rfpflash.py"
    cmd = [
        "python", str(script),
        "--rfp", cfg.get("rfp_exe", r"rfp-cli.exe"),
        "--device", cfg.get("rfp_device", "RX65x"),
        "--tool", cfg.get("rfp_tool", "e2l"),
        "--interface", cfg.get("rfp_interface", "fine"),
        "--file", srec_path,
        "--id", cfg.get("id_code", ""),
        "--run"
    ]
    run_cmd(cmd)

def relay_on():
    """Turn ON J-Link power using your relay control (Case A: step 2)."""
    script = ROOT / "relaycontrol" / "relayon.py"
    cmd = ["python", str(script)]
    run_cmd(cmd)

def jflash_update(cfg: dict, update_pkg: str):
    """Run jlinkflash.py to program/verify update package (Case A: step 3, Case D step 2)."""
    script = ROOT / "jlinkflash" / "jlinkflash.py"
    cmd = [
        "python", str(script),
        "--jflash", cfg.get("jflash_exe", r"JFlashSPI_CL.exe"),
        "--project", cfg.get("jflash_project", r"jlinkflash.jflash"),
        "--image", update_pkg,
        "--addr", "0x0",
        "--connect",
        "--erasechip",
        "--programverify"
    ]
    run_cmd(cmd)

def selfprog_download(cfg: dict, update_pkg: str):
    """SelfProgrammer download update package (Case B)."""
    script = ROOT / "selfprogrammer" / "selfprogrammerdownload.py"
    cmd = [
        "python", str(script),
        "--exe", cfg.get("selfprog_exe", r"SelfProg_Tool.exe"),
        "--port", str(cfg.get("serial_port", 8)),
        "--baud", str(cfg.get("serial_baud", 38400)),
        "--board", str(cfg.get("board_number", 48)),
        "--bin", update_pkg,
        "--backend"
    ]
    run_cmd(cmd)

def selfprog_flagcheck_install(cfg: dict, wait_sec=30, retries=5, interval=2):
    """SelfProg flag check with --install (Case A, B, C, D)."""
    script = ROOT / "selfprogrammer" / "selfproflagcheck.py"
    logs_dir = ROOT / "selfprogrammer" / "logs"
    cmd = [
        "python", str(script),
        "--exe", cfg.get("selfprog_exe", r"SelfProg_Tool.exe"),
        "--logdir", str(logs_dir),
        "--install",
        "--wait", str(wait_sec),
        "--retries", str(retries),
        "--interval", str(interval)
    ]
    run_cmd(cmd)

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print("Usage: python runtestplan.py <path_to_yaml_testplan>")
        sys.exit(1)

    testplan_path = Path(sys.argv[1]).resolve()
    if not testplan_path.exists():
        print(f"[ERROR] Testplan not found: {testplan_path}")
        sys.exit(2)

    tp = load_yaml(testplan_path)
    product_name = detect_product_name(tp.get("name", "SaverAdvPlus"))
    cfg = load_product_config(product_name)

    print("\n============================================================")
    print(f" RUNNING TEST PLAN : {testplan_path.name}")
    print(f" PRODUCT          : {product_name}")
    print("============================================================\n")

    tests = tp.get("tests", [])
    if not tests:
        print("[WARN] No tests found in YAML.")
        sys.exit(0)

    for t in tests:
        tid = t.get("id", "Unknown")
        scenario = t.get("scenario", "")
        method = t.get("delivery_method", "")
        flash_srec = t.get("flash_srec")
        update_pkg = t.get("update_pkg")

        print("\n------------------------------------------------------------")
        print(f"TEST: {tid}")
        print(f"Scenario      : {scenario}")
        print(f"Delivery      : {method}")
        print(f"SREC (optional): {flash_srec or '-'}")
        print(f"Update package: {update_pkg or '-'}")
        print("------------------------------------------------------------")

        # CASE A: SREC present + JFlash delivery
        if flash_srec and method == "JFlash":
            print("\n[CASE A] SREC present + JFlash delivery method")
            rfp_flash_srec(cfg, flash_srec)        # Step 1
            relay_on()                              # Step 2
            if not update_pkg:
                print("[ERROR] update_pkg is required for JFlash tests.")
                sys.exit(3)
            jflash_update(cfg, update_pkg)          # Step 3
            selfprog_flagcheck_install(cfg)         # Step 4

        # CASE D: JFlash NO SREC
        elif method == "JFlash" and not flash_srec:
            print("\n[CASE D] JFlash (no SREC)")
            if not update_pkg:
                print("[ERROR] update_pkg is required for JFlash tests.")
                sys.exit(3)
            relay_on()                              # Step 1
            jflash_update(cfg, update_pkg)          # Step 2
            selfprog_flagcheck_install(cfg)         # Step 3

        # CASE B: SelfProgrammer (NO SREC)
        elif method == "SelfProgrammer":
            print("\n[CASE B] SelfProgrammer (no SREC)")
            if not update_pkg:
                print("[ERROR] update_pkg is required for SelfProgrammer tests.")
                sys.exit(3)
            selfprog_download(cfg, update_pkg)
            selfprog_flagcheck_install(cfg)

        # CASE C: InstallOnly (NO SREC)
        elif method == "InstallOnly":
            print("\n[CASE C] InstallOnly (no SREC)")
            selfprog_flagcheck_install(cfg)

        else:
            # Guard rails: if a test gives SREC but not JFlash, or unknown method
            if flash_srec and method != "JFlash":
                print(f"[ERROR] SREC provided but delivery_method is '{method}'. Expected 'JFlash'.")
                sys.exit(3)
            print(f"[ERROR] Unsupported or missing delivery_method: '{method}'")
            sys.exit(3)

    print("\n============ ALL TESTS COMPLETED SUCCESSFULLY ============\n")


if __name__ == "__main__":
    main()