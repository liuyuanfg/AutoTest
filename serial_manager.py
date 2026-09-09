"""
串口管理器，用于 GNSS 模块批量测试。

打开一个或多个串口，读取 NMEA 数据流，根据配置参数采集 GGA/GSV 样本。
支持命令发送与响应检测、启动信息等待、调试日志记录。

Serial port manager for batch GNSS module testing.

Opens one or more serial ports, reads incoming NMEA data streams,
and collects GGA/GSV samples according to configured parameters.
Supports command send/response detection, boot info waiting, debug logging.
"""
from __future__ import annotations

import os
import time
import logging
from typing import Optional, Callable, List
from threading import Thread, Event, Lock

import serial
import serial.tools.list_ports

from nmea_parser import NMEAParser
from app_paths import get_app_dir

logger = logging.getLogger(__name__)


class SerialModule:
    """
    Wraps a single serial port connected to a GNSS module under test.

    Runs a background reader thread that feeds lines to an NMEAParser.
    """

    def __init__(
        self,
        module_id: str,
        port: str,
        baudrate: int = 9600,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: int = 1,
        timeout: float = 1.0,
        description: str = "",
    ) -> None:
        self.module_id = module_id
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self.description = description

        self.parser = NMEAParser()
        self._ser: Optional[serial.Serial] = None
        self._reader_thread: Optional[Thread] = None
        self._stop_event = Event()
        self._external_stop: Optional[Event] = None  # injected from outside

        # Debug: save all received raw data per port
        self._debug_file: Optional[object] = None

        # Collect raw boot / power-on messages for later parsing
        self._boot_lines: List[str] = []
        self._boot_lines_max = 2000

        # Command-response mechanism
        self._cmd_responses: List[str] = []  # lines matching pending command prefixes
        self._cmd_prefix: Optional[str] = None
        self._cmd_response_event = Event()

        # Thread safety for parser access
        self._lock = Lock()

    @property
    def _should_stop(self) -> bool:
        return self._stop_event.is_set() or (self._external_stop is not None and self._external_stop.is_set())

    def request_stop(self) -> None:
        """Signal the module to stop reading / collecting."""
        self._stop_event.set()

    def set_external_stop(self, event: Optional[Event]) -> None:
        """Wire an external threading.Event for co-ordinated stop."""
        self._external_stop = event

    # ── public API ─────────────────────────────────────────────

    def open(self) -> bool:
        """Open the serial port and start background reading."""
        try:
            self._ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=self.timeout,
            )
        except serial.SerialException as exc:
            logger.error("[%s] Failed to open %s: %s", self.module_id, self.port, exc)
            return False

        # Open debug/trace file for this port
        try:
            debug_dir = os.path.join(get_app_dir(), "debug")
            os.makedirs(debug_dir, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            safe_id = "".join(c for c in self.module_id if c.isalnum() or c in "_-")
            fname = f"{safe_id}_{self.port.replace(':', '_')}_{ts}.log"
            self._debug_file = open(os.path.join(debug_dir, fname), "w", encoding="utf-8")
            self._debug_file.write(f"# Debug log for {self.module_id} @ {self.port}\n")
            self._debug_file.write(f"# Baud: {self.baudrate}  Opened: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            self._debug_file.write(f"# {'='*60}\n\n")
            self._debug_file.flush()
        except Exception:
            self._debug_file = None

        self._stop_event.clear()
        self._reader_thread = Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        logger.info("[%s] Opened %s @ %d baud", self.module_id, self.port, self.baudrate)
        return True

    def close(self) -> None:
        """Stop reading and close the serial port."""
        self._stop_event.set()
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=3.0)
        if self._ser and self._ser.is_open:
            try:
                self._ser.close()
            except Exception:
                pass
        if self._debug_file:
            try:
                self._debug_file.write(f"\n# Closed: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                self._debug_file.close()
            except Exception:
                pass
            self._debug_file = None
        logger.info("[%s] Closed %s", self.module_id, self.port)

    def send_command(self, cmd: str, timeout: float = 5.0, response_prefix: Optional[str] = None) -> Optional[str]:
        """
        Send a text command over the serial port and wait for a response line.
        The background reader thread detects matching responses via _cmd_prefix.
        If response_prefix is given, use that instead of the command itself.
        Returns the response line, or None on timeout.
        """
        if not self._ser or not self._ser.is_open:
            return None

        resp_prefix = response_prefix or cmd.strip()

        # Register the expected response prefix with the reader thread
        with self._lock:
            self._cmd_prefix = resp_prefix
            self._cmd_response_event.clear()

        # Send the command
        try:
            self._ser.write((cmd + "\r\n").encode("ascii"))
            self._ser.flush()
        except Exception:
            with self._lock:
                self._cmd_prefix = None
            return None

        # Wait for the reader thread to detect the response
        if self._cmd_response_event.wait(timeout=timeout):
            with self._lock:
                if self._cmd_responses:
                    resp = self._cmd_responses.pop(0)
                    self._cmd_prefix = None
                    return resp
                self._cmd_prefix = None
        else:
            # Timeout: try polling _boot_lines as fallback
            with self._lock:
                self._cmd_prefix = None
                for line in reversed(self._boot_lines):
                    if line.strip().upper().startswith(resp_prefix.upper()):
                        return line

        return None

    def send_command_retry(
        self, cmd: str, timeout: float = 3.0, retries: int = 3,
        response_prefix: Optional[str] = None, delay_between: float = 1.0
    ) -> Optional[str]:
        """
        Send a command with retries if no response is received.
        Useful for boot-phase commands where the module may not be ready yet.
        """
        for attempt in range(retries):
            resp = self.send_command(cmd, timeout, response_prefix)
            if resp:
                return resp
            if attempt < retries - 1:
                logger.info("[%s] Retry %d/%d for %s", self.module_id, attempt + 2, retries, cmd.split(",")[0])
                time.sleep(delay_between)
        return None

    def wait_for_data(self, timeout: float, callback: Optional[Callable[[str], None]] = None) -> bool:
        """
        Block until at least one valid GGA/GSV sentence has been received,
        indicating the module has powered on and is outputting data.

        Returns True if data was received within *timeout* seconds.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not self._should_stop:
            with self._lock:
                has_data = len(self.parser.gga_data) > 0 or len(self.parser.gsv_groups) > 0
            if has_data:
                return True
            if callback:
                callback(f"[{self.module_id}] waiting for power-on data ... {int(deadline - time.monotonic())}s left")
            time.sleep(0.5)
        return False

    def wait_for_boot_info(self, timeout: float, callback: Optional[Callable[[str], None]] = None) -> bool:
        """
        Block until boot messages (FW/ChipID/SN) are detected in the data stream.
        Used after sending $XTSFWLOAD to wait for the module to reboot.

        Returns True if boot info was received within *timeout* seconds.
        """
        from boot_parser import BootParser
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not self._should_stop:
            with self._lock:
                boot_lines = list(self._boot_lines)
            info = BootParser.parse(boot_lines)
            if info.found_any:
                return True
            if callback:
                callback(f"[{self.module_id}] waiting for boot info ... {int(deadline - time.monotonic())}s left")
            time.sleep(0.5)
        return False

    def collect_samples(
        self,
        sample_count: int = 0,
        sample_duration: int = 0,
        callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Collect *sample_count* complete NMEA cycles, or run for *sample_duration* seconds.

        A cycle is detected by the parser: RMC (new cycle) after GGA + completed GSV group.
        """
        if sample_duration > 0:
            deadline = time.monotonic() + sample_duration
            while time.monotonic() < deadline and not self._should_stop:
                if callback:
                    remaining = int(deadline - time.monotonic())
                    with self._lock:
                        cycles = self.parser.complete_cycles
                        gga_cnt = len(self.parser.gga_data)
                        gsv_cnt = len(self.parser.gsv_groups)
                    callback(f"[{self.module_id}] collecting ... {remaining}s | cycles:{cycles} GGA:{gga_cnt} GSV:{gsv_cnt}")
                time.sleep(1.0)
        elif sample_count > 0:
            while True:
                with self._lock:
                    cycles = self.parser.complete_cycles
                    cur_gga = len(self.parser.gga_data)
                    cur_gsv = len(self.parser.gsv_groups)
                if cycles >= sample_count or self._should_stop:
                    break
                if callback:
                    callback(f"[{self.module_id}] collecting {cycles}/{sample_count} cycles | GGA:{cur_gga} GSV:{cur_gsv}")
                time.sleep(0.2)

    def get_statistics(self) -> dict:
        """Return a snapshot of collected statistics (thread-safe)."""
        with self._lock:
            self.parser.flush_pending_gsv()
            return {
                "gga_samples": len(self.parser.gga_data),
                "gsv_groups": len(self.parser.gsv_groups),
                "gga_data": self.parser.gga_data,
                "gsv_groups": self.parser.gsv_groups,
                "boot_lines": list(self._boot_lines),
            }

    def get_boot_lines(self) -> List[str]:
        """Return collected raw boot messages (thread-safe)."""
        with self._lock:
            return list(self._boot_lines)

    # ── internal ───────────────────────────────────────────────

    def _read_loop(self) -> None:
        """Background thread: continuous blocking read from serial port."""
        if self._ser:
            self._ser.timeout = 0.2  # short timeout for responsive reads
        leftover = b""
        line_count = 0
        while not self._should_stop:
            try:
                if self._ser and self._ser.is_open:
                    data = self._ser.read(4096)
                    if data:
                        leftover += data
                        while b"\n" in leftover:
                            line, leftover = leftover.split(b"\n", 1)
                            try:
                                decoded = line.decode("ascii", errors="ignore").strip()
                            except Exception:
                                continue
                            if decoded:
                                # Write raw line to debug log (flush every 200 lines)
                                if self._debug_file:
                                    try:
                                        self._debug_file.write(f"{decoded}\n")
                                        line_count += 1
                                        if line_count % 200 == 0:
                                            self._debug_file.flush()
                                    except Exception:
                                        pass
                                with self._lock:
                                    self.parser.parse_line(decoded)
                                    if len(self._boot_lines) < self._boot_lines_max:
                                        self._boot_lines.append(decoded)
                                    # Check for pending command response
                                    if self._cmd_prefix and decoded.strip().upper().startswith(self._cmd_prefix.upper()):
                                        self._cmd_responses.append(decoded)
                                        self._cmd_response_event.set()
                else:
                    time.sleep(0.01)
            except (serial.SerialException, OSError) as exc:
                logger.error("[%s] Serial read error: %s", self.module_id, exc)
                time.sleep(1.0)
            except Exception:
                time.sleep(0.05)


def enumerate_ports() -> List[str]:
    """Return list of available COM port device names."""
    ports = serial.tools.list_ports.comports()
    return [p.device for p in sorted(ports)]
