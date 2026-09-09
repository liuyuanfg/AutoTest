"""
GNSS 模块批量自动化测试工具 (GNSS Module Batch Automation Test Tool)

CLI 入口，用于 GNSS 模块的批量串口测试。
解析 NMEA-0183 GGA/GSV/RMC 语句，计算信噪比统计，生成 PDF 测试报告。
支持并行测试、判定标准评估、中英文切换。

Main entry point for batch serial-port testing of GNSS modules.
Parses NMEA-0183 GGA/GSV/RMC sentences, computes SNR statistics,
and generates a PDF test report.
"""
from __future__ import annotations

import os
import sys
import time
import random
import logging
import argparse
import threading
from typing import List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import yaml

from serial_manager import SerialModule, enumerate_ports
from statistics_calculator import StatisticsCalculator, ModuleResult, BandStats
from report_generator import ReportGenerator
from boot_parser import BootParser
from criteria import Criteria
from app_paths import get_config_path, get_app_dir

logger = logging.getLogger("autotest")


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def progress_callback(msg: str) -> None:
    """Print progress messages to stdout (overwritable line)."""
    print(f"\r{' ' * 78}\r{msg}", end="", flush=True)


def run_module_test(
    mod_cfg: dict,
    serial_defaults: dict,
    test_cfg: dict,
    log_cb: Optional[Callable[[str], None]] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
    criteria: Optional[Criteria] = None,
    stop_event: Optional[threading.Event] = None,
) -> ModuleResult:
    """Run the full test flow for one module.

    Args:
        mod_cfg: Module configuration dict (id, port, baudrate, description).
        serial_defaults: Default serial settings.
        test_cfg: Test parameters (timeout, sample_count, etc.).
        log_cb: Optional callback for log messages (defaults to print).
        progress_cb: Optional callback for progress updates (defaults to stdout line).
    """
    _log = log_cb or (lambda msg: print(msg))
    _progress = progress_cb or progress_callback

    module_id = mod_cfg["id"]
    port = mod_cfg["port"]
    description = mod_cfg.get("description", "")

    mod = SerialModule(
        module_id=module_id,
        port=port,
        baudrate=mod_cfg.get("baudrate", serial_defaults.get("baudrate", 9600)),
        bytesize=mod_cfg.get("bytesize", serial_defaults.get("bytesize", 8)),
        parity=mod_cfg.get("parity", serial_defaults.get("parity", "N")),
        stopbits=mod_cfg.get("stopbits", serial_defaults.get("stopbits", 1)),
        timeout=mod_cfg.get("timeout", serial_defaults.get("timeout", 1.0)),
        description=description,
    )
    if stop_event:
        mod.set_external_stop(stop_event)

    t_start = time.monotonic()

    # 1. Open serial port
    _log(f"\n[{module_id}] Opening {port} ...")
    if not mod.open():
        _log(f"[{module_id}] FAILED to open {port}")
        return ModuleResult(
            module_id=module_id, port=port, description=description,
            success=False, error_message=f"Failed to open serial port {port}",
        )

    # Allow module to initialise before sending commands
    time.sleep(0.5)

    # 1b. Query version info via $XTSMONVER (with retries)
    _log(f"[{module_id}] Querying \$XTSMONVER ...")
    xtsmonver_resp = mod.send_command_retry(
        "$XTSMONVER", timeout=3.0, retries=3, delay_between=1.0,
    )
    xtsmonver_info = BootParser.parse_xtsmonver(xtsmonver_resp or "") if xtsmonver_resp else {}
    if xtsmonver_info.get("fw"):
        _log(f"[{module_id}] XTSMONVER → FW={xtsmonver_info['fw']} SN={xtsmonver_info.get('sn','?')}")
    else:
        _log(f"[{module_id}] XTSMONVER: no response (non-fatal)")

    # 1c. Enable COM2 AGNSS data output (with retries)
    _log(f"[{module_id}] Sending \$XTSCFGPRT to enable COM2 AGNSS ...")
    xtscfg_resp = mod.send_command_retry(
        "$XTSCFGPRT,1,,H40000007,", timeout=3.0, retries=3,
        response_prefix="$XTSCMDOk", delay_between=1.0,
    )
    if xtscfg_resp:
        _log(f"[{module_id}] XTSCFGPRT → OK")
    else:
        _log(f"[{module_id}] XTSCFGPRT: no response (non-fatal)")

    # 1d. Reboot module via $XTSFWLOAD and wait for boot info
    if test_cfg.get("send_xtsfwload", True):
        _log(f"[{module_id}] Sending \$XTSFWLOAD to reboot module ...")
        mod.send_command("$XTSFWLOAD", timeout=2.0)
        boot_timeout = test_cfg.get("boot_wait_timeout", 30)
        got_boot = mod.wait_for_boot_info(timeout=boot_timeout, callback=_progress)
        if got_boot:
            _log(f"[{module_id}] Boot info received after reboot")
        else:
            _log(f"[{module_id}] No boot info after reboot (non-fatal)")

    try:
        # 2. Wait for power-on data
        poweron_timeout = test_cfg.get("wait_poweron_timeout", 60)
        _log(f"[{module_id}] Waiting for power-on data (timeout: {poweron_timeout}s) ...")
        got_data = mod.wait_for_data(timeout=poweron_timeout, callback=_progress)

        if not got_data:
            _log(f"[{module_id}] No data received within timeout")
            return ModuleResult(
                module_id=module_id, port=port, description=description,
                success=False,
                error_message=f"No NMEA data received within {poweron_timeout}s timeout",
            )

        # 3. Collect samples
        collect_mode = test_cfg.get("collect_mode", "count")
        sample_count = test_cfg.get("sample_count", 50)
        sample_duration = test_cfg.get("sample_duration", 0)

        if collect_mode == "duration" and sample_duration > 0:
            _log(f"[{module_id}] Collecting for {sample_duration}s ...")
            mod.collect_samples(sample_duration=sample_duration, callback=_progress)
        else:
            _log(f"[{module_id}] Collecting {sample_count} data cycles ...")
            mod.collect_samples(sample_count=sample_count, callback=_progress)

        # 4. Get statistics
        stats = mod.get_statistics()
        boot_info = BootParser.parse(stats.get("boot_lines", []))
        # Fallback: use XTSMONVER fields if not found in boot messages
        if xtsmonver_info:
            if not boot_info.fw_version:
                boot_info.fw_version = xtsmonver_info.get("fw", "")
            if not boot_info.sn:
                boot_info.sn = xtsmonver_info.get("sn", "")
        duration = time.monotonic() - t_start

        result = StatisticsCalculator.compute(
            module_id=module_id,
            port=port,
            description=description,
            gga_data=stats["gga_data"],
            gsv_groups=stats["gsv_groups"],
            duration=duration,
            boot_info=boot_info,
            criteria=criteria,
        )
        return result

    finally:
        mod.close()


def summarise_result(result: ModuleResult) -> str:
    """Return a one-line summary string for a ModuleResult."""
    status = "PASS" if result.overall_pass else "FAIL"
    bi = result.boot_info
    parts = [
        f"  {result.module_id:12s} | {status:4s}",
        f"SN={bi.sn}" if bi and bi.sn else "",
        f"FW={bi.fw_version}" if bi and bi.fw_version else "",
        f"BL={bi.bootloader_version}" if bi and bi.bootloader_version else "",
        f"FixQ={result.fix_quality}",
        f"SatUsed={result.positioned_satellites:2d}",
        f"SatsTracked={result.total_tracked_sats:2d}",
        f"HDOP={result.last_hdop:.2f}",
    ]
    if result.criteria_violations:
        parts.append(f"VIOLATED: {', '.join(result.criteria_violations[:2])}")
    return " | ".join(p for p in parts if p)


# ═══════════════════════════════════════════════════════════════════════
#  Simulation mode — generates fake NMEA data for dry-run testing
# ═══════════════════════════════════════════════════════════════════════

_SAMPLE_GGA = (
    "GPGGA,{time},4807.038,N,01131.000,E,1,{sats},{hdop:.1f},{alt:.1f},M,46.9,M,,"
)
_SAMPLE_RMC = (
    "GPRMC,{time},A,4807.038,N,01131.000,E,0.0,0.0,{date},0.0,W"
)
_SAMPLE_GSV_GROUPS: dict = {
    "GP": (  # talker → (num_msg, satellites_generator)
        3,
        lambda: [
            (3, 3, 111, 00), (4, 43, 287, 39), (6, 41, 227, 40), (9, 25, 310, 0),
            (11, 63, 68, 43), (17, 25, 159, 39), (19, 61, 305, 42), (22, 21, 211, 37),
            (23, 2, 315, 0), (26, 34, 69, 41), (27, 11, 50, 37), (28, 6, 189, 33),
        ],
    ),
    "GL": (
        2,
        lambda: [
            (65, 12, 145, 28), (66, 5, 313, 0), (72, 31, 20, 35), (73, 54, 163, 39),
            (74, 53, 317, 41), (80, 18, 233, 30),
        ],
    ),
    "GA": (
        2,
        lambda: [
            (1, 40, 280, 38), (2, 55, 150, 42), (3, 10, 80, 0), (4, 70, 200, 45),
            (5, 30, 310, 33), (6, 60, 45, 39),
        ],
    ),
}


def _nmea_checksum(s: str) -> str:
    c = 0
    for ch in s:
        c ^= ord(ch)
    return f"{c:02X}"


def _build_gsv_sentences(talker: str, sats: list) -> List[str]:
    """Build a complete GSV group with valid checksums."""
    num_msg, sat_gen = _SAMPLE_GSV_GROUPS.get(talker, (1, lambda: []))
    all_sats = sats if sats else sat_gen()
    total = len(all_sats)
    sentences = []
    for msg_num in range(1, num_msg + 1):
        start = (msg_num - 1) * 4
        chunk = all_sats[start:start + 4]
        fields = [str(num_msg), str(msg_num), str(total)]
        for sat in chunk:
            fields.extend(str(x) for x in sat)
        base = f"{talker}GSV,{','.join(fields)}"
        cs = _nmea_checksum(base)
        sentences.append(f"${base}*{cs}")
    return sentences


def simulate_module_test(
    mod_cfg: dict,
    test_cfg: dict,
    log_cb: Optional[Callable[[str], None]] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
    criteria: Optional[Criteria] = None,
    stop_event: Optional[threading.Event] = None,
) -> ModuleResult:
    """Simulate a module test by generating synthetic NMEA data."""
    _log = log_cb or (lambda msg: print(msg))
    _progress = progress_cb or progress_callback

    module_id = mod_cfg["id"]
    port = mod_cfg["port"]
    description = mod_cfg.get("description", "")
    t_start = time.monotonic()

    _log(f"\n[{module_id}] [SIMULATE] Generating synthetic NMEA data for {port} ...")

    # Simulate boot messages
    fake_boot_lines = [
        "$TC1720 ROM 83 FW $TC1720_v4_0.289$; signal 10 0x8ca25 meas 1000 nav 1 sleepT 0, userCfg 0",
        "$ChipID,000000000123",
        "$SN,711000000001",
        "",
        "bootloader V5.0.0",
        "$TC1720_v4_powerTest_0.271$",
        "$XTSMONVER,TC1720_v4_0.271,37,711000000001",
        "$XTSCFGPRT,1,,H40000007,OK",
        "$XTSCMDOk",
    ]
    boot_info = BootParser.parse(fake_boot_lines)
    _log(f"[{module_id}] Boot: FW={boot_info.fw_version}, Bootloader={boot_info.bootloader_version}, ChipID={boot_info.chip_id}")

    # Simulate power-on delay
    time.sleep(0.8)
    _log(f"[{module_id}] Power-on data detected (simulated)")

    sample_count = test_cfg.get("sample_count", 10)
    gga_list = []
    gsv_list = []

    from nmea_parser import NMEAParser

    for cycle in range(sample_count):
        if stop_event and stop_event.is_set():
            _log(f"[{module_id}] Stop requested — ending collection early")
            break
        pp = NMEAParser()

        # Generate RMC (marks start of new cycle)
        hh = 120000 + cycle
        rmc_raw = _SAMPLE_RMC.format(time=f"{hh}.00", date="250525")
        rmc_cs = _nmea_checksum(rmc_raw)
        pp.parse_line(f"${rmc_raw}*{rmc_cs}")

        # Generate GGA
        raw = _SAMPLE_GGA.format(
            time=f"{hh}.00", sats=8 + random.randint(-2, 3),
            hdop=0.8 + random.random() * 0.4, alt=545.0 + random.random() * 10,
        )
        cs = _nmea_checksum(raw)
        pp.parse_line(f"${raw}*{cs}")
        if pp.gga_data:
            gga_list.append(pp.gga_data[0])

        # Generate GSV for each constellation
        for talker in _SAMPLE_GSV_GROUPS:
            sats = _SAMPLE_GSV_GROUPS[talker][1]()
            # Add some jitter to SNR per cycle
            snr_mod = cycle * 0.5
            sats = [(p, e, a, max(0, min(55, s + int(snr_mod % 8 - 4)))) for p, e, a, s in sats]
            sentences = _build_gsv_sentences(talker, sats)
            for s in sentences:
                pp.parse_line(s)
        gsv_list.extend(pp.gsv_groups)

        _progress(f"[{module_id}] collecting {cycle + 1}/{sample_count} cycles | GGA:{len(gga_list)} GSV:{len(gsv_list)}")
        time.sleep(0.05)

    duration = time.monotonic() - t_start
    result = StatisticsCalculator.compute(
        module_id=module_id, port=port, description=description,
        gga_data=gga_list, gsv_groups=gsv_list, duration=duration,
        boot_info=boot_info, criteria=criteria,
    )
    return result


# ═══════════════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GNSS Module Batch Auto Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py -c config.yaml          # Real test with serial ports
  python main.py -c config.yaml -s       # Dry-run with simulated data
  python main.py --list-ports            # Show available COM ports
        """,
    )
    parser.add_argument("-c", "--config", default=get_config_path(), help="Path to config YAML file")
    parser.add_argument("--list-ports", action="store_true", help="List available serial ports and exit")
    parser.add_argument("-s", "--simulate", action="store_true", help="Simulate test with synthetic NMEA data (no hardware needed)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose debug output")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # List ports and exit
    if args.list_ports:
        ports = enumerate_ports()
        print("Available COM ports:")
        for p in ports:
            print(f"  {p}")
        return

    # Load config
    config_path = args.config
    if not os.path.isabs(config_path):
        config_path = os.path.join(get_app_dir(), config_path)
    config = load_config(config_path)

    modules_cfg = config.get("modules", [])
    if not modules_cfg:
        print("ERROR: No modules configured in YAML file.")
        sys.exit(1)

    serial_defaults = config.get("serial", {})
    test_cfg = config.get("test", {})
    output_cfg = config.get("output", {})
    criteria = Criteria.from_dict(config.get("criteria"))

    print("=" * 60)
    print("  GNSS Module Batch Automation Test")
    print("=" * 60)
    print(f"  Modules to test: {len(modules_cfg)} (parallel)")
    for m in modules_cfg:
        print(f"    - {m['id']}  ({m['port']})")
    print()

    # ── Run all modules in parallel ──
    results: List[ModuleResult] = []
    stop_event = threading.Event()

    # Handle Ctrl+C in CLI
    def _on_keyboard_interrupt(sig, frame):
        print("\nStopping tests ...")
        stop_event.set()
    original_sigint = __import__("signal").signal(__import__("signal").SIGINT, _on_keyboard_interrupt)

    def _run_one(mod_cfg: dict) -> ModuleResult:
        if args.simulate:
            return simulate_module_test(mod_cfg, test_cfg, criteria=criteria, stop_event=stop_event)
        else:
            return run_module_test(mod_cfg, serial_defaults, test_cfg, criteria=criteria, stop_event=stop_event)

    with ThreadPoolExecutor(max_workers=len(modules_cfg)) as executor:
        future_map = {executor.submit(_run_one, m): m for m in modules_cfg}
        for future in as_completed(future_map):
            mod_cfg = future_map[future]
            try:
                result = future.result()
            except Exception as exc:
                result = ModuleResult(
                    module_id=mod_cfg.get("id", "?"),
                    port=mod_cfg.get("port", "?"),
                    description=mod_cfg.get("description", ""),
                    success=False,
                    error_message=str(exc),
                )
            results.append(result)
            print(summarise_result(result))

    # Restore original module order for the report
    id_order = {m.get("id", ""): i for i, m in enumerate(modules_cfg)}
    results.sort(key=lambda r: id_order.get(r.module_id, 999))
    __import__("signal").signal(__import__("signal").SIGINT, original_sigint)

    # ── Generate PDF report ──
    print(f"\n{'─' * 40}")
    print("Generating PDF report ...")
    report_dir = output_cfg.get("report_dir", "./reports")
    if not os.path.isabs(report_dir):
        report_dir = os.path.join(get_app_dir(), report_dir)
    report_gen = ReportGenerator(
        output_dir=report_dir,
        prefix=output_cfg.get("report_prefix", "GNSS_Test_Report"),
        batch_no=config.get("meta", {}).get("batch_no", ""),
        tester=config.get("meta", {}).get("tester", ""),
    )
    report_path = report_gen.generate(results)
    print(f"Report saved: {os.path.abspath(report_path)}")

    # ── Final console summary ──
    print(f"\n{'=' * 60}")
    print("  TEST COMPLETE")
    print(f"{'=' * 60}")
    pass_count = sum(1 for r in results if r.overall_pass)
    fail_count = len(results) - pass_count
    print(f"  Total: {len(results)}  |  PASS: {pass_count}  |  FAIL: {fail_count}")
    for r in results:
        print(summarise_result(r))
    print()


if __name__ == "__main__":
    main()
