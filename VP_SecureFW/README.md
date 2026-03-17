# VP SecureFW Test Framework

A comprehensive firmware testing and validation framework for embedded devices, specifically designed for Renesas RX series microcontrollers with secure firmware update capabilities.

## Overview

This framework automates the testing of firmware update processes across multiple delivery methods (J-Flash, Self-Programmer, Install-Only) with robust retry logic and detailed reporting. It supports both SREC-based initial flashing and incremental update package deployment.

### Key Features

- **Multiple Delivery Methods**: J-Flash, Self-Programmer, and Install-Only testing
- **SREC Support**: Initial device programming with Renesas Flash Programmer
- **Intelligent Retry Logic**: Automatic retries for failed tests with sequence restarts
- **Comprehensive Reporting**: Excel reports with detailed flag comparisons
- **Product Flexibility**: Easy configuration for new products via JSON configs
- **Hardware Integration**: Relay control for power cycling during tests

## Project Structure

```
VP_SecureFW/
├── runtestplan.py              # Main test orchestration script
├── productconfigs/             # Product-specific configurations
│   └── <ProductName>.json
├── testplans/                  # Test plan definitions
│   └── <ProductName>.yaml
├── rfpflash/                   # Renesas Flash Programmer interface
│   ├── rfpflash.py
│   └── logs/
├── jlinkflash/                 # SEGGER J-Link interface
│   ├── jlinkflash.py
│   └── logs/
├── selfprogrammer/             # Self-programmer tool interface
│   ├── selfproflagcheck.py
│   ├── selfprogflagcheckparser.py
│   ├── selfprogrammerdownload.py
│   └── logs/
├── relaycontrol/               # Hardware relay control
│   ├── relayon.py
│   └── relayoff.py
├── reports/                    # Generated test reports
└── logs/                       # General logging directory
```

## Installation & Setup

### Prerequisites

- **Python 3.8+**
- **PyYAML**: `pip install pyyaml`
- **openpyxl**: `pip install openpyxl` (for Excel reports)
- **Hardware Tools**:
  - Renesas Flash Programmer V3.21+
  - SEGGER J-Link software
  - Self-Programmer Tool (product-specific)
- **Hardware**: Target device with appropriate debug/programming interfaces

### Initial Setup

1. Clone or copy the framework to your local machine
2. Install Python dependencies:
   ```bash
   pip install pyyaml openpyxl
   ```
3. Verify hardware tool installations and paths

## Configuration for New Products

### 1. Create Product Configuration

Create a JSON file in `productconfigs/` named `<ProductName>.json`:

```json
{
  "product_name": "YourProduct",
  "id_code": "YOUR_DEVICE_ID_CODE",

  "rfp_exe": "C:\\Path\\To\\rfp-cli.exe",
  "rfp_device": "RX65x",
  "rfp_tool": "e2l",
  "rfp_interface": "fine",

  "jflash_exe": "C:\\Path\\To\\JFlashSPI_CL.exe",
  "jflash_project": "C:\\Path\\To\\jlinkflash.jflash",

  "selfprog_exe": "C:\\Path\\To\\SelfProg_Tool.exe",

  "relay_on_script": "relaycontrol/relayon.py",
  "relay_off_script": "relaycontrol/relayoff.py",

  "serial_port": 8,
  "serial_baud": 38400,
  "board_number": 48
}
```

**Configuration Parameters:**

- `product_name`: Display name for the product
- `id_code`: Device ID code for RFP verification
- `rfp_*`: Renesas Flash Programmer settings
- `jflash_*`: J-Link flash tool settings
- `selfprog_exe`: Path to self-programmer executable
- `relay_*_script`: Python scripts for relay control
- `serial_*`: Serial communication settings
- `board_number`: Target board identifier

### 2. Create Test Plan

Create a YAML file in `testplans/` named `<ProductName>.yaml`:

```yaml
name: "Your Product Firmware Upgrade Test Suite"

tests:
  - id: "Test 1"
    scenario: "Initial firmware flash and update"
    delivery_method: "JFlash"
    flash_srec: "C:\\Path\\To\\InitialFirmware.srec"
    update_pkg: "C:\\Path\\To\\UpdatePackage.bin"
    expected_flags_after_reset:
      FwUpdate_req: 0
      FwUpdate_frez: 1
      FwUpdate_actbin: 0
      FwUpdate_rollbk: 255
      SelfProg Error Code: "0xAF"

  - id: "Test 2"
    scenario: "Self-programmer update only"
    delivery_method: "SelfProgrammer"
    update_pkg: "C:\\Path\\To\\AnotherUpdate.bin"
    expected_flags_after_reset:
      FwUpdate_req: 0
      FwUpdate_frez: 1
      FwUpdate_actbin: 1
      FwUpdate_rollbk: 255
      SelfProg Error Code: "0xAF"

  - id: "Test 3"
    scenario: "Install check without update"
    delivery_method: "InstallOnly"
    flash_srec: "C:\\Path\\To\\BaseFirmware.srec"
    expected_flags_after_reset:
      FwUpdate_req: 255
      FwUpdate_frez: 1
      FwUpdate_actbin: 0
      FwUpdate_rollbk: 255
      SelfProg Error Code: "0x600"
```

**Test Configuration Parameters:**

- `id`: Unique test identifier
- `scenario`: Human-readable description
- `delivery_method`: One of: `JFlash`, `SelfProgrammer`, `InstallOnly`
- `flash_srec`: (Optional) Path to SREC file for initial flashing
- `update_pkg`: (Optional) Path to update package (required for JFlash/SelfProgrammer)
- `expected_flags_after_reset`: Expected flag values after test completion

### 3. Update Hardware Scripts (if needed)

The relay control scripts (`relaycontrol/relayon.py` and `relayoff.py`) may need modification for your specific hardware setup. These scripts typically control power relays for device reset/power cycling.

## Running Tests

### Basic Usage

```bash
python runtestplan.py testplans/YourProduct.yaml
```

### Advanced Options

```bash
# Run only specific test
python runtestplan.py testplans/YourProduct.yaml --only-test "Test 1"

# Start from specific test
python runtestplan.py testplans/YourProduct.yaml --start-from "Test 3"
```

### Test Execution Flow

The framework supports 5 different test scenarios:

#### CASE A: SREC + JFlash
1. Flash SREC using RFP
2. Turn relay ON (power on device)
3. Program update package via J-Link
4. Check self-programmer flags

#### CASE B: SelfProgrammer Only
1. Download update package via self-programmer
2. Check self-programmer flags

#### CASE C: InstallOnly (No SREC)
1. Check self-programmer flags (assumes device is already programmed)

#### CASE D: JFlash Only (No SREC)
1. Turn relay ON
2. Program update package via J-Link
3. Check self-programmer flags

#### CASE E: SREC + InstallOnly
1. Flash SREC using RFP
2. Turn relay ON (power on device)
3. J-Flash erasechip, then readchip + relayoff (no update package required)
4. Check self-programmer flags

## Unified Test Flow & Retry Logic

The framework uses a unified, flexible test execution logic:

- **If an SREC is provided, it is always flashed first.**
- **Delivery method** (JFlash, SelfProgrammer, InstallOnly) is then executed as specified.
- **Flag check is always performed last for every test.**
- **Any combination is supported:** SREC only, delivery method only, both, or neither (flag check only).

### SREC Tests (with `flash_srec`)
- **Individual Retries**: Failed tests retry up to 3 times at the same position
- **Scope**: Only the failing test is retried

### Non-SREC Tests (without `flash_srec`)
- **Sequence Restarts**: Failed tests trigger restart from the last SREC test
- **Cycle Retries**: Up to 3 complete cycles of (last SREC test → failing test)
- **Fresh State**: Each cycle ensures device is in a known state via SREC re-flash

### Example Retry Flow

```
Test 1 (SREC) → PASS
Test 2 (no SREC) → FAIL → Restart from Test 1
Test 1 (SREC) → PASS
Test 2 (no SREC) → FAIL → Restart from Test 1 (2nd cycle)
Test 1 (SREC) → PASS
Test 2 (no SREC) → FAIL → Give up after 3 cycles → Move to Test 3
```

## Output & Reporting


### Console Output

- Real-time test progress with status indicators
- Only high-level test step messages are shown (tool command output is suppressed for clarity)
- Detailed retry information
- Flag comparison results
- Error messages and diagnostics

### Excel Reports

Generated automatically in `reports/` directory when all tests pass:

- **Main Sheet**: Test summary with pass/fail status
- **Flag Summary Sheet**: Detailed flag comparisons for each test

### Log Files

- Individual tool logs in respective `logs/` directories
- Comprehensive execution logs for debugging

## Expected Flag Values

The framework validates device state by comparing actual flag values against expected values:

### Common Flags

- `FwUpdate_req`: Update request status (0 = no request, 255 = request pending)
- `FwUpdate_frez`: Freeze status (1 = normal, 0 = frozen)
- `FwUpdate_actbin`: Active binary (0 = primary, 1 = secondary)
- `FwUpdate_rollbk`: Rollback status (255 = disabled, 0 = enabled)
- `SelfProg Error Code`: Operation result (hex codes like "0xAF" = success)

### Flag Validation

- Hex values are automatically normalized (e.g., "0xAF" → 175)
- Mnemonic suffixes are parsed (e.g., "0x000000AF (FWU_SUCCESS)" → 175)
- Case-insensitive string comparison for non-numeric flags

## Troubleshooting

### Common Issues

1. **Tool Not Found**: Verify paths in product config JSON
2. **Device Connection Failed**: Check hardware connections and power
3. **Flag Mismatches**: Review expected values in test plan YAML
4. **Serial Communication**: Verify port/baud settings


### Prompt Automation

- The framework automatically responds to interactive prompts (e.g., "Do you want to program the same version again? Press y to continue...") for seamless unattended execution.

### Debug Mode

Run individual components manually:

```bash
# Test RFP flashing
python rfpflash/rfpflash.py --rfp "path/to/rfp-cli.exe" --device RX65x --tool e2l --interface fine --file "path/to/file.srec" --id YOUR_ID --run

# Test self-programmer flags
python selfprogrammer/selfproflagcheck.py --exe "path/to/SelfProg_Tool.exe" --logdir logs --install --wait 30 --retries 5 --interval 2
```

### Log Analysis

Check log files in:
- `rfpflash/logs/`
- `jlinkflash/logs/`
- `selfprogrammer/logs/`
- `logs/`

## Extending the Framework

### Adding New Delivery Methods

1. Update `execute_test()` function in `runtestplan.py`
2. Add new CASE in the main logic
3. Update documentation

### Custom Hardware Control

Modify `relaycontrol/relayon.py` and `relayoff.py` for your specific relay hardware.

### New Flag Types

Extend `normalize_flag_value()` in `selfprogrammer/selfprogflagcheckparser.py` for custom flag formats.

## Support

For issues or questions:
1. Check log files for detailed error information
2. Verify hardware connections and tool installations
3. Review test plan and product configuration syntax
4. Test individual components manually

## License

This framework is provided as-is for firmware testing purposes. Ensure compliance with your organization's software development and testing policies.