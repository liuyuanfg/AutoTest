"""
Boot message parser for TC1720 GNSS module power-on print messages.

Extracts:
  - Firmware version (FW)
  - ROM version
  - Bootloader version
  - Chip ID
  - Serial Number (SN)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class BootInfo:
    """Parsed boot/power-on information from a GNSS module."""
    fw_version: str = ""
    rom_version: str = ""
    bootloader_version: str = ""
    chip_id: str = ""
    sn: str = ""
    raw_messages: List[str] = field(default_factory=list)

    @property
    def found_any(self) -> bool:
        return bool(self.fw_version or self.chip_id or self.bootloader_version or self.rom_version or self.sn)


class BootParser:
    """Parse raw serial boot messages for TC1720 module info."""

    # ── regex patterns ──────────────────────────────────────────

    RE_FW_INLINE = re.compile(
        r"\$TC1720\s+ROM\s+(\d+)\s+FW\s+\$(TC1720_[\w.]+)",
        re.IGNORECASE,
    )
    RE_FW_STANDALONE = re.compile(r"\$(TC1720_[\w.]+)\$")
    RE_CHIPID = re.compile(r"\$ChipID\s*,?\s*(\d+)", re.IGNORECASE)
    RE_BOOTLOADER = re.compile(r"bootloader\s+V?([\d.]+)", re.IGNORECASE)
    RE_ROM_STANDALONE = re.compile(r"ROM\s+(\d+)", re.IGNORECASE)
    RE_XTSMONVER = re.compile(
        r"\$XTSMONVER\s*,?\s*\$?([\w.]+)",
        re.IGNORECASE,
    )
    RE_SN = re.compile(r"\$SN\s*,?\s*([^*\s]+)", re.IGNORECASE)
    RE_XTSCMDOK = re.compile(r"\$XTSCMDOk", re.IGNORECASE)

    @classmethod
    def parse(cls, lines: List[str]) -> BootInfo:
        """Parse a list of raw boot message lines and return BootInfo."""
        info = BootInfo(raw_messages=list(lines))

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Pattern 1: $TC1720 ROM 83 FW $TC1720_v4_powerTest_0.271$
            m = cls.RE_FW_INLINE.search(stripped)
            if m:
                info.rom_version = m.group(1)
                info.fw_version = m.group(2)
                continue

            # Pattern 2: $ChipID,37
            m = cls.RE_CHIPID.search(stripped)
            if m:
                info.chip_id = m.group(1)
                continue

            # Pattern 2b: $SN,<serial_number>
            m = cls.RE_SN.search(stripped)
            if m:
                info.sn = m.group(1)
                continue

            # Pattern 3: bootloader V5.0.0
            m = cls.RE_BOOTLOADER.search(stripped)
            if m:
                info.bootloader_version = m.group(1)
                continue

            # Pattern 4: $TC1720_v4_powerTest_0.271$ (standalone FW)
            if not info.fw_version:
                m = cls.RE_FW_STANDALONE.search(stripped)
                if m:
                    info.fw_version = m.group(1)
                    continue

            # Pattern 5: ROM 83 (standalone)
            if not info.rom_version:
                m = cls.RE_ROM_STANDALONE.search(stripped)
                if m:
                    info.rom_version = m.group(1)

            # Pattern 6: $XTSMONVER,<FW>,<ChipID>,<SN> — only use FW and SN
            m = cls.RE_XTSMONVER.search(stripped)
            if m:
                if not info.fw_version:
                    info.fw_version = m.group(1)
                sn = cls._extract_xtsmonver_sn(stripped)
                if not info.sn and sn:
                    info.sn = sn

        return info

    @staticmethod
    def _extract_xtsmonver_sn(line: str) -> str:
        """Extract the SN field (3rd comma field) from an XTSMONVER response."""
        parts = line.strip().split(",")
        if len(parts) >= 4:
            sn = parts[3].split("*")[0].strip()
            return sn
        return ""

    @classmethod
    def parse_xtsmonver(cls, response: str) -> dict:
        """Parse a $XTSMONVER response. Returns {'fw':..., 'sn':...} (ChipID ignored)."""
        result = {"fw": "", "sn": ""}
        m = cls.RE_XTSMONVER.search(response)
        if m:
            result["fw"] = m.group(1)
        result["sn"] = cls._extract_xtsmonver_sn(response)
        return result
