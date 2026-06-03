# -*- coding: utf-8 -*-
r"""
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

CASE E: SREC present + delivery_method: InstallOnly
    1) RFP flash SREC
    2) Relay ON
    3) J-Flash erasechip + readchip + relayoff
    4) SelfProg flag check with --install

CASE D: delivery_method: JFlash (NO SREC)
    1) Relay ON
    2) J-Flash update package
    3) SelfProg flag check with --install

CASE E: SREC present + delivery_method: InstallOnly
    1) RFP flash SREC
    2) SelfProg flag check with --install

Usage:
    python runtestplan.py <path_to_yaml_testplan>

Notes:
- Looks for optional product config JSON at:
        productconfigs/<ProductName>.json
    If missing, uses built-in defaults based on your transcripts.
"""
from pathlib import Path
import json
from typing import Tuple
import sys
import subprocess

# --- YAML dependency (PyYAML) ------------------------------------------------
try:
    import yaml  # pip install pyyaml
except ImportError:
    print("[ERROR] PyYAML is required. Please run:  pip install pyyaml")
    sys.exit(1)

# -----------------------------------------------------------------------------
# Email helper
# -----------------------------------------------------------------------------
def send_report_email(report_path: Path, recipient: str):
    """
    Send the generated report as an email attachment via Gmail SMTP.

    Credentials are read from environment variables to avoid storing secrets:
        GMAIL_SENDER        - your Gmail address (e.g. you@gmail.com)
        GMAIL_APP_PASSWORD  - a Gmail App Password (16-char, no spaces)
                              Generate one at: https://myaccount.google.com/apppasswords

    If either variable is absent you will be prompted interactively.
    """
    import smtplib
    import os
    import getpass
    from email.message import EmailMessage

    # Try process env first, then fall back to the persistent User-level store
    # (needed when the terminal was not restarted after setting the variables).
    def _get_env(key: str) -> str:
        val = os.environ.get(key, "").strip()
        if not val:
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as reg:
                    val, _ = winreg.QueryValueEx(reg, key)
                    val = (val or "").strip()
            except Exception:
                pass
        return val

    sender = _get_env("GMAIL_SENDER")
    if not sender:
        sender = input("[EMAIL] Sender Gmail address: ").strip()

    password = _get_env("GMAIL_APP_PASSWORD")
    if not password:
        password = getpass.getpass("[EMAIL] Gmail App Password (input hidden): ")

    msg = EmailMessage()
    msg["Subject"] = f"Test Report: {report_path.name}"
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(
        f"Please find the attached test report: {report_path.name}\n\n"
        "This report was generated automatically by runtestplan.py."
    )

    with open(report_path, "rb") as fh:
        msg.add_attachment(
            fh.read(),
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=report_path.name,
        )

    print(f"[EMAIL] Sending report to {recipient} ...")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, password)
            smtp.send_message(msg)
        print(f"[EMAIL] Report sent successfully to {recipient}.")
    except smtplib.SMTPAuthenticationError:
        print("[EMAIL] Authentication failed. Make sure you are using a Gmail App Password, not your regular password.")
        print("        Generate one at: https://myaccount.google.com/apppasswords")
    except Exception as exc:
        print(f"[EMAIL] Failed to send report: {exc}")

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent

def run_cmd(cmd_list, cwd=None, stop_on_error=True, echo=False, suppress_output=True):
    """Run a command (list form). Returns exit code, optionally aborts on error."""
    if echo:
        here = f"(cwd: {cwd})" if cwd else ""
        pretty = " ".join(f'"{c}"' if " " in str(c) else str(c) for c in cmd_list)
        print(f"\n>>> {pretty} {here}".strip())
    
    if suppress_output:
        rc = subprocess.call(cmd_list, cwd=str(cwd) if cwd else None, shell=False, 
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        rc = subprocess.call(cmd_list, cwd=str(cwd) if cwd else None, shell=False)
    
    if stop_on_error and rc != 0:
        print(f"[ERROR] Command returned {rc}.")
        return rc
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
            return cfg

    # Fallback defaults (from your commands)
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


def get_enabled_boards(cfg: dict):
    boards = [("main", cfg.get("board_number", 48))]
    if cfg.get("ble_board_number") is not None:
        boards.append(("ble", cfg.get("ble_board_number")))
    if cfg.get("wifi_board_number") is not None:
        boards.append(("wifi", cfg.get("wifi_board_number")))
    return boards

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
    print("  [*] Running RFP flash SREC...")
    rc = run_cmd(cmd, stop_on_error=False)
    if rc != 0:
        print(f"  [ERROR] RFP flash failed with exit code {rc}.")
    return rc

def relay_on():
    """Turn ON J-Link power using your relay control (Case A: step 2)."""
    script = ROOT / "relaycontrol" / "relayon.py"
    cmd = ["python", str(script)]
    print("  [*] Turning relay ON...")
    rc = run_cmd(cmd, stop_on_error=False)
    if rc != 0:
        print(f"  [ERROR] Relay ON failed with exit code {rc}.")
    return rc

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
    print("  [*] Running J-Flash update...")
    rc = run_cmd(cmd, stop_on_error=False)
    if rc != 0:
        print(f"  [ERROR] J-Flash update failed with exit code {rc}.")
    return rc

def jflash_erase_and_reconnect(cfg: dict):
    """Run J-Flash erasechip + readchip + relayoff for InstallOnly with SREC."""
    exe = cfg.get("jflash_exe", r"JFlashSPI_CL.exe")
    project = cfg.get("jflash_project", r"jlinkflash.jflash")
    
    print("  [*] Running J-Flash erasechip...")
    cmd_erase = [exe, "-openprj", project, "-connect", "-erasechip"]
    rc = run_cmd(cmd_erase, stop_on_error=False)
    if rc != 0:
        print(f"  [ERROR] J-Flash erasechip failed with exit code {rc}.")
        return rc
    
    print("  [*] Running readchip + relayoff...")
    p_readchip = subprocess.Popen(
        [exe, "-openprj", project, "-connect", "-readchip"],
        stdout=subprocess.DEVNULL,  # Suppress output
        stderr=subprocess.STDOUT,
        text=True,
        shell=False
    )
    
    relay_dir = ROOT / "relaycontrol"
    relay_script = relay_dir / "relayoff.py"
    subprocess.Popen(
        f'start cmd /c "cd /d {relay_dir} && python {relay_script}"',
        shell=True
    )
    
    p_readchip.wait()
    return p_readchip.returncode

def selfprog_download(cfg: dict, update_pkg: str, board_number: int, board_label: str = "main"):
    """SelfProgrammer download update package."""
    script = ROOT / "selfprogrammer" / "selfprogrammerdownload.py"
    cmd = [
        "python", str(script),
        "--exe", cfg.get("selfprog_exe", r"SelfProg_Tool.exe"),
        "--port", str(cfg.get("serial_port", 8)),
        "--baud", str(cfg.get("serial_baud", 38400)),
        "--board", str(board_number),
        "--bin", update_pkg,
        "--backend"
    ]
    print(f"  [*] Running SelfProgrammer download [{board_label.upper()} board]...")
    # Use subprocess.Popen to provide 'y' input for same version prompt
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=str(ROOT))
    stdout, _ = proc.communicate(input=b'y\n')
    rc = proc.returncode
    if rc != 0:
        print(f"  [ERROR] SelfProgrammer download failed with exit code {rc}.")
        # Print output for debugging
        try:
            output = stdout.decode("utf-8", errors="replace")
            print(output)
        except Exception:
            pass
    return rc

def selfprog_flagcheck_install(cfg: dict, expected_flags: dict = None, wait_sec=30, retries=5, interval=2, board_label: str = "main", reset_type: str = "install"):
    """SelfProg flag check with --install (Case A, B, C, D). Returns (rc, ad_path, ar_path, test_passed)."""
    script = ROOT / "selfprogrammer" / "selfproflagcheck.py"
    logs_dir = ROOT / "selfprogrammer" / "logs"
    # ensure logs directory exists and capture files created by this run
    logs_dir.mkdir(parents=True, exist_ok=True)
    before = set(logs_dir.iterdir())
    cmd = [
        "python", str(script),
        "--exe", cfg.get("selfprog_exe", r"SelfProg_Tool.exe"),
        "--logdir", str(logs_dir),
        "--reset-type", reset_type,
        "--wait", str(wait_sec),
        "--retries", str(retries),
        "--interval", str(interval),
        "--port", str(cfg.get("serial_port", 8)),
        "--baud", str(cfg.get("serial_baud", 38400)),
        "--board", str(cfg.get("board_number", 48)),
        "--quiet"
    ]
    print(f"  [*] Running SelfProg flag check with {reset_type} [{board_label.upper()} board]...")
    rc = run_cmd(cmd, stop_on_error=False, suppress_output=False)
    # determine which log files were created
    after = set(logs_dir.iterdir())
    new = after - before
    ad_path = None
    ar_path = None
    for p in new:
        name = p.name.lower()
        if "after_download" in name:
            ad_path = p
        elif "after_reset" in name:
            ar_path = p
    if rc != 0:
        print(f"  [ERROR] SelfProg flag check failed with exit code {rc}.")
    
    # Check test pass/fail by comparing flags
    test_passed = True
    if expected_flags and ar_path:
        from selfprogrammer import selfprogflagcheckparser as parser
        ar_text = parser.load_text(ar_path)
        ar_data = parser.parse_pairs(ar_text)
        
        print("\n  [DEBUG] Flag Comparison:")
        for field_key, expected_val in expected_flags.items():
            # Try to find the field in ar_data, handling different case variations
            actual_val = "—"
            for key in ar_data.keys():
                if key.replace(" ", "").lower() == field_key.replace(" ", "").lower():
                    actual_val = ar_data[key]
                    break
            
            actual_normalized = parser.normalize_flag_value(actual_val)
            expected_normalized = parser.normalize_flag_value(str(expected_val))
            matches = actual_normalized == expected_normalized
            status = "✓" if matches else "✗"
            print(f"    {status} {field_key}: expected={expected_normalized}, actual={actual_normalized}")
            
            if not matches:
                test_passed = False
    
    return rc, ad_path, ar_path, test_passed

def execute_test(t: dict, cfg: dict) -> Tuple[bool, bool, list]:
    """
    Execute a single test and return (error_occurred, test_passed, board_results).
    """
    flash_srec = t.get("flash_srec")
    reset_type = str(t.get("reset_type", "install")).strip().lower()
    if reset_type not in ("install", "reset"):
        print(f"  [WARN] Invalid reset_type '{reset_type}' in test '{t.get('id', 'Unknown')}'. Using 'install'.")
        reset_type = "install"

    error_occurred = False
    test_passed = True
    board_results = []

    # Step 1: If SREC is provided, flash it first
    if flash_srec:
        if rfp_flash_srec(cfg, flash_srec) != 0:
            error_occurred = True

    # Step 2: Run per-board flow for all enabled boards
    enabled_boards = get_enabled_boards(cfg)
    for board_label, board_number in enabled_boards:
        if board_label == "main":
            has_board_scoped_non_main = any(
                key in t
                for key in (
                    "delivery_method_ble",
                    "update_pkg_ble",
                    "expected_flags_after_reset_ble",
                    "delivery_method_wifi",
                    "update_pkg_wifi",
                    "expected_flags_after_reset_wifi",
                )
            )

            method = t.get("delivery_method_main", t.get("delivery_method", ""))
            update_pkg = t.get("update_pkg_main", t.get("update_pkg"))
            expected_flags = t.get("expected_flags_after_reset_main", t.get("expected_flags_after_reset", {}))

            has_explicit_main_keys = any(
                key in t
                for key in (
                    "delivery_method_main",
                    "update_pkg_main",
                    "expected_flags_after_reset_main",
                )
            )

            # Legacy unscoped fields represent MAIN only when they carry MAIN payload/expectation
            # (or when there are no board-scoped BLE/WIFI fields in the test).
            has_legacy_main_payload = any(
                key in t
                for key in (
                    "update_pkg",
                    "expected_flags_after_reset",
                )
            )

            board_requested = (
                has_explicit_main_keys
                or has_legacy_main_payload
                or (not has_board_scoped_non_main and "delivery_method" in t)
            )
            update_key = "update_pkg"
            expected_key = "expected_flags_after_reset"
        else:
            method_key = f"delivery_method_{board_label}"
            update_key = f"update_pkg_{board_label}"
            expected_key = f"expected_flags_after_reset_{board_label}"
            method = t.get(method_key, t.get("delivery_method", ""))
            update_pkg = t.get(update_key)
            expected_flags = t.get(expected_key, {})
            board_requested = any(
                key in t
                for key in (
                    method_key,
                    update_key,
                    expected_key,
                )
            )

        if not board_requested:
            continue

        print(f"\n  --- BOARD: {board_label.upper()} (board_number={board_number}) ---")

        board_error = False
        board_flag_summary = ""
        board_passed = True

        if method == "JFlash":
            if relay_on() != 0:
                board_error = True
            if not update_pkg:
                print(f"  [ERROR] {update_key} is required for JFlash tests.")
                board_error = True
            elif jflash_update(cfg, update_pkg) != 0:
                board_error = True
        elif method == "SelfProgrammer":
            if not update_pkg:
                print(f"  [ERROR] {update_key} is required for SelfProgrammer tests.")
                board_error = True
            elif selfprog_download(cfg, update_pkg, board_number, board_label) != 0:
                board_error = True
        elif method == "InstallOnly":
            if relay_on() != 0:
                board_error = True
            if jflash_erase_and_reconnect(cfg) != 0:
                board_error = True
        elif method:
            print(f"  [ERROR] Unknown delivery_method for {board_label}: '{method}'")
            board_error = True

        if board_error:
            print(f"  [WARN] Skipping SelfProg flag check for {board_label.upper()} due to delivery failure.")
            board_passed = False
            test_passed = False
            error_occurred = True
            board_results.append({
                "board_label": board_label,
                "board_number": board_number,
                "delivery": method,
                "update_pkg": update_pkg or "",
                "expected_flags": expected_flags,
                "test_passed": False,
                "flag_summary": board_flag_summary,
            })
            continue

        rc, ad, ar, board_passed = selfprog_flagcheck_install(
            cfg,
            expected_flags,
            board_label=board_label,
            reset_type=reset_type,
        )
        if rc != 0:
            board_error = True
        else:
            import io, contextlib
            from selfprogrammer import selfprogflagcheckparser as parser
            buf = io.StringIO()
            if ad and ar:
                with contextlib.redirect_stdout(buf):
                    parser.summarize(ad, ar, expected_flags if expected_flags else None)
                board_flag_summary = buf.getvalue()

        if board_error or not board_passed:
            test_passed = False
        if board_error:
            error_occurred = True

        board_results.append({
            "board_label": board_label,
            "board_number": board_number,
            "delivery": method,
            "update_pkg": update_pkg or "",
            "expected_flags": expected_flags,
            "test_passed": board_passed and not board_error,
            "flag_summary": board_flag_summary,
        })

    return error_occurred, test_passed, board_results

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    import argparse
    
    ap = argparse.ArgumentParser(
        description="Run test plans from YAML with optional filtering",
        usage="python runtestplan.py <path_to_yaml_testplan> [--only-test TEST_ID] [--start-from TEST_ID] [--repeat N]"
    )
    ap.add_argument("testplan", help="Path to the YAML testplan file")
    ap.add_argument("--only-test", dest="only_test", default=None, help="Run only a specific test ID")
    ap.add_argument("--start-from", dest="start_from", default=None, help="Start from a specific test ID and run remaining tests")
    ap.add_argument("--repeat", type=int, default=1, metavar="N",
                    help="Run the entire testplan N times (default: 1). A report is generated after each completed run.")
    ap.add_argument(
        "--send-report-to",
        dest="send_report_to",
        default=None,
        metavar="EMAIL",
        help=(
            "Email address to send the generated report to via Gmail SMTP. "
            "Set GMAIL_SENDER and GMAIL_APP_PASSWORD environment variables to avoid interactive prompts."
        ),
    )

    args = ap.parse_args()
    
    testplan_path = Path(args.testplan).resolve()
    if not testplan_path.exists():
        print(f"[ERROR] Testplan not found: {testplan_path}")
        sys.exit(2)

    tp = load_yaml(testplan_path)
    # Allow overriding the product name in the YAML (preferred)
    product_name = tp.get("product_name") or tp.get("product")

    # If not explicitly set, try inferring from the testplan filename (e.g. LY_VP_SET1.yaml)
    if not product_name:
        candidate = testplan_path.stem.split("_")[0]
        cfg_path = ROOT / "productconfigs" / f"{candidate}.json"
        if cfg_path.exists():
            product_name = candidate

    # Fallback to the embedded name field in the YAML
    if not product_name:
        product_name = detect_product_name(tp.get("name", "SaverAdvPlus"))
    cfg = load_product_config(product_name)

    all_tests = tp.get("tests", [])
    if not all_tests:
        print("[WARN] No tests found in YAML.")
        sys.exit(0)

    if args.repeat < 1:
        print("[ERROR] --repeat must be 1 or greater.")
        sys.exit(2)

    # Build the filtered test list once — the same list is reused for every run.
    if args.only_test:
        tests = [t for t in all_tests if t.get("id") == args.only_test]
        if not tests:
            print(f"[ERROR] Test ID '{args.only_test}' not found in testplan.")
            sys.exit(2)
        print(f"[INFO] Running only test: {args.only_test}\n")
    elif args.start_from:
        start_idx = None
        for idx, t in enumerate(all_tests):
            if t.get("id") == args.start_from:
                start_idx = idx
                break
        if start_idx is None:
            print(f"[ERROR] Test ID '{args.start_from}' not found in testplan.")
            sys.exit(2)
        tests = all_tests[start_idx:]
        print(f"[INFO] Starting from test: {args.start_from}\n")
    else:
        tests = all_tests

    run_summaries = []  # [(run_num, overall_error), ...]

    for run_num in range(1, args.repeat + 1):
        if args.repeat > 1:
            print(f"\n{'='*60}")
            print(f"RUN {run_num} of {args.repeat}")
            print(f"{'='*60}\n")

        # collect results for report
        results = []
        overall_error = False
        last_srec_test_idx = None
        test_idx = 0
        last_failed_no_srec_idx = None
        last_failed_no_srec_retry_count = 0

        while test_idx < len(tests):
            t = tests[test_idx]
            tid = t.get("id", "Unknown")
            scenario = t.get("scenario", "")
            flash_srec = t.get("flash_srec")

            # Track the last test that had flash_srec
            if flash_srec:
                last_srec_test_idx = test_idx

            print(f"\n>>> TEST: {tid}")

            # Execute test with retry logic
            retry_count = 0
            error_occurred = False
            test_passed = False
            board_results = []

            while retry_count < 3:
                error_occurred, test_passed, board_results = execute_test(t, cfg)
                
                if not error_occurred:
                    break
                
                retry_count += 1
                if retry_count < 3:
                    print(f"  [RETRY] Test failed, retrying ({retry_count}/3)...")

            # Print test result with pass/fail status
            if error_occurred:
                print(f">>> TEST: {tid} - COMPLETED WITH ERRORS\n")
                
                # If this test has no flash_srec and it errored, restart from last srec test with 3 cycle retries
                if not flash_srec and last_srec_test_idx is not None:
                    # Check if this is the same failed test as before
                    if last_failed_no_srec_idx == test_idx:
                        last_failed_no_srec_retry_count += 1
                        if last_failed_no_srec_retry_count < 3:
                            print(f"  [INFO] Test {tid} failed again. Restarting from last SREC test (cycle {last_failed_no_srec_retry_count + 1}/3)...")
                            test_idx = last_srec_test_idx
                            overall_error = True
                            continue
                        else:
                            print(f"  [INFO] Test {tid} failed 3 times. Moving to next test.")
                            last_failed_no_srec_idx = None
                            last_failed_no_srec_retry_count = 0
                    else:
                        # First failure for this test without srec
                        last_failed_no_srec_idx = test_idx
                        last_failed_no_srec_retry_count = 1
                        print(f"  [INFO] No SREC in this test. Restarting from last SREC test (cycle 1/3)...")
                        test_idx = last_srec_test_idx
                        overall_error = True
                        continue
            else:
                status_symbol = "✓ PASSED" if test_passed else "✗ FAILED"
                print(f">>> TEST: {tid} - {status_symbol}\n")
                # Reset failed no-srec tracking when a test passes
                if not flash_srec:
                    last_failed_no_srec_idx = None
                    last_failed_no_srec_retry_count = 0

            # record result
            results.append({
                "id": tid,
                "scenario": scenario,
                "delivery": t.get("delivery_method", ""),
                "flash_srec": flash_srec or "",
                "update_pkg": t.get("update_pkg") or "",
                "error": error_occurred,
                "test_passed": test_passed,
                "board_results": board_results,
            })
            if error_occurred:
                overall_error = True

            test_idx += 1

        # if every test succeeded, create report and clean logs
        if not overall_error:
            try:
                from openpyxl import Workbook
                from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            except ImportError:
                print("[WARN] openpyxl not installed; skipping report generation.")
            else:
                reports_dir = ROOT / "reports"
                reports_dir.mkdir(parents=True, exist_ok=True)
                ts = __import__("datetime").datetime.now().strftime("%Y%m%d-%H%M%S")
                # Include run index in the filename when --repeat > 1 so each run
                # gets its own uniquely-named report file.
                if args.repeat > 1:
                    report_name = f"{testplan_path.stem}_{ts}_run{run_num}of{args.repeat}.xlsx"
                else:
                    report_name = f"{testplan_path.stem}_{ts}.xlsx"
                wb = Workbook()
                ws = wb.active
                ws.title = "Results"
                
                # Setup styles
                header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
                header_font = Font(bold=True, color="FFFFFF")
                flag_header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
                flag_header_font = Font(bold=True)
                thin_border = Border(
                    left=Side(style='thin'),
                    right=Side(style='thin'),
                    top=Side(style='thin'),
                    bottom=Side(style='thin')
                )
                
                # Main headers
                headers = ["Test ID", "Scenario", "Delivery", "Flash SREC", "Update Package", "Error", "Status"]
                ws.append(headers)
                for cell in ws[1]:
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                    cell.border = thin_border
                
                # Set initial column widths for main data
                ws.column_dimensions['A'].width = 12
                ws.column_dimensions['B'].width = 35
                ws.column_dimensions['C'].width = 18
                ws.column_dimensions['D'].width = 35
                ws.column_dimensions['E'].width = 35
                ws.column_dimensions['F'].width = 10
                ws.column_dimensions['G'].width = 12
                
                # Rows with main test data
                row_num = 2
                for r in results:
                    main_board = None
                    for br in r.get("board_results", []):
                        if br.get("board_label") == "main":
                            main_board = br
                            break

                    ws[f'A{row_num}'].value = r["id"]
                    ws[f'B{row_num}'].value = r["scenario"]
                    ws[f'C{row_num}'].value = (main_board or {}).get("delivery", r["delivery"])
                    ws[f'D{row_num}'].value = r["flash_srec"]
                    ws[f'E{row_num}'].value = (main_board or {}).get("update_pkg", r["update_pkg"])
                    ws[f'F{row_num}'].value = "Yes" if r["error"] else "No"
                    ws[f'G{row_num}'].value = "✓ PASSED" if r.get("test_passed", False) else "✗ FAILED"
                    
                    # Color code the status column
                    status_cell = ws[f'G{row_num}']
                    if r.get("test_passed", False):
                        status_cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
                        status_cell.font = Font(bold=True, color="006100")
                    else:
                        status_cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
                        status_cell.font = Font(bold=True, color="9C0006")
                    
                    for col in ['A', 'B', 'C', 'D', 'E', 'F', 'G']:
                        cell = ws[f'{col}{row_num}']
                        cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
                        cell.border = thin_border
                    
                    row_num += 1
                
                # Create flag summary details sheet
                flag_sheet = wb.create_sheet("Flag Summary")
                flag_row = 1
                
                for r in results:
                    # Test ID header for this test
                    test_id_cell = flag_sheet[f'A{flag_row}']
                    test_id_cell.value = f"Test ID: {r['id']}"
                    test_id_cell.font = Font(bold=True, size=12)
                    test_id_cell.fill = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")
                    flag_sheet.merge_cells(f'A{flag_row}:E{flag_row}')
                    test_id_cell.border = thin_border
                    flag_row += 1

                    for br in r.get("board_results", []):
                        board_label = br.get("board_label", "main")
                        board_number = br.get("board_number", "")
                        board_pass = br.get("test_passed", False)
                        board_header = f"Board: {board_label.upper()} (#{board_number}) - {'PASS' if board_pass else 'FAIL'}"
                        board_cell = flag_sheet[f'A{flag_row}']
                    board_cell.value = board_header
                    board_cell.font = Font(bold=True)
                    board_cell.fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
                    flag_sheet.merge_cells(f'A{flag_row}:E{flag_row}')
                    board_cell.border = thin_border
                    flag_row += 1

                    if br.get("flag_summary"):
                        lines = br["flag_summary"].strip().split('\n')
                        for line in lines:
                            line_stripped = line.strip()
                            if not line_stripped or line_stripped.startswith('+'):
                                continue
                            if line_stripped.startswith('|'):
                                parts = [p.strip() for p in line_stripped.split('|')]
                                parts = [p for p in parts if p]
                                if len(parts) == 3:
                                    field_name = parts[0]
                                    val_download = parts[1]
                                    val_reset = parts[2]
                                    expected_val = "—"
                                    if br.get("expected_flags"):
                                        expected_val = str(br["expected_flags"].get(field_name, "—"))

                                    flag_sheet[f'A{flag_row}'].value = field_name
                                    flag_sheet[f'B{flag_row}'].value = val_download
                                    flag_sheet[f'C{flag_row}'].value = val_reset
                                    flag_sheet[f'D{flag_row}'].value = expected_val

                                    for col in ['A', 'B', 'C', 'D']:
                                        cell = flag_sheet[f'{col}{flag_row}']
                                        cell.border = thin_border
                                        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

                                    flag_row += 1
                    else:
                        flag_sheet[f'A{flag_row}'].value = "(No flag data available)"
                        flag_sheet[f'A{flag_row}'].font = Font(italic=True, color="808080")
                        flag_row += 1

                    flag_row += 1
                
                # Add blank row for separation
                flag_row += 1
            
            # Set column widths for flag summary sheet
            flag_sheet.column_dimensions['A'].width = 25
            flag_sheet.column_dimensions['B'].width = 20
            flag_sheet.column_dimensions['C'].width = 20
            flag_sheet.column_dimensions['D'].width = 20
            
            wb.save(str(reports_dir / report_name))
            print(f"[INFO] Report generated: {reports_dir / report_name}")
            # Send report by email if requested
            if args.send_report_to:
                send_report_email(reports_dir / report_name, args.send_report_to)
            # cleanup log files now that report exists
            for logdir in ROOT.rglob('logs'):
                if logdir.is_dir():
                    for f in logdir.iterdir():
                        try:
                            f.unlink()
                        except Exception:
                            pass
            print("[INFO] Log files deleted.")

        # Record outcome of this run before moving to the next
        run_summaries.append((run_num, overall_error))

        print("\n" + "="*60)
        if args.repeat > 1:
            print(f"RUN {run_num} of {args.repeat} COMPLETED")
        else:
            print("ALL TESTS COMPLETED")
        print("="*60 + "\n")

    # After all runs: print a summary table when --repeat > 1
    if args.repeat > 1:
        width = len(str(args.repeat))
        print("\n" + "="*60)
        print(f"REPEAT SUMMARY  ({args.repeat} run{'s' if args.repeat != 1 else ''})")
        print("="*60)
        for rn, err in run_summaries:
            status = "COMPLETED WITH ERRORS  (no report)" if err else "OK — report generated"
            print(f"  Run {rn:{width}}: {status}")
        print("="*60 + "\n")


if __name__ == "__main__":
    main()