"""
Statistics calculator for GNSS test results.

Extracts:
  - Number of positioning satellites (from GGA)
  - Per-frequency/constellation average / max SNR
  - Per-module summary
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from collections import defaultdict

from nmea_parser import GGAData, GSVGroup
from boot_parser import BootInfo
from criteria import Criteria


@dataclass
class BandStats:
    """Per-frequency-band SNR statistics."""
    band_name: str
    avg_snr: float = 0.0
    max_snr: float = 0.0
    tracked_satellites: int = 0
    total_in_view: int = 0


@dataclass
class ModuleResult:
    """Aggregated test result for a single module."""
    module_id: str
    port: str
    description: str
    success: bool = True
    error_message: str = ""

    # GGA-derived
    positioned_satellites: int = 0
    fix_quality: int = 0
    avg_hdop: float = 0.0
    last_hdop: float = 0.0
    avg_altitude: float = 0.0

    # GSV-derived, keyed by frequency-band label
    per_band: Dict[str, BandStats] = field(default_factory=dict)

    # Meta
    gga_count: int = 0
    gsv_group_count: int = 0
    duration_seconds: float = 0.0

    # Which bands are primary (first signal ID per constellation)
    primary_bands: Set[str] = field(default_factory=set)

    # Boot / power-on info
    boot_info: BootInfo = field(default_factory=BootInfo)

    # Criteria evaluation
    criteria_pass: bool = True
    criteria_violations: List[str] = field(default_factory=list)

    @property
    def overall_pass(self) -> bool:
        """True if data collection succeeded AND all criteria passed."""
        return self.success and self.criteria_pass

    @property
    def total_tracked_sats(self) -> int:
        """Sum of tracked satellites across primary bands only."""
        return sum(b.tracked_satellites for name, b in self.per_band.items() if name in self.primary_bands)

    @property
    def band_names(self) -> List[str]:
        return list(self.per_band.keys())


class StatisticsCalculator:
    """Compute aggregate statistics from raw NMEA data."""

    @staticmethod
    def compute(
        module_id: str,
        port: str,
        description: str,
        gga_data: List[GGAData],
        gsv_groups: List[GSVGroup],
        duration: float,
        boot_info: Optional[BootInfo] = None,
        criteria: Optional[Criteria] = None,
    ) -> ModuleResult:
        """Build a ModuleResult from collected GGA / GSV data."""
        result = ModuleResult(
            module_id=module_id,
            port=port,
            description=description,
            gga_count=len(gga_data),
            gsv_group_count=len(gsv_groups),
            duration_seconds=duration,
            boot_info=boot_info or BootInfo(),
        )

        if not gga_data:
            result.success = False
            result.error_message = "No GGA sentences collected"
            return result

        # ── GGA aggregation ────────────────────────────────────
        result.positioned_satellites = max(g.num_satellites for g in gga_data)
        # Fix quality priority: 4 > 5 > 3 > 2 > 1
        _fix_priority = {4: 5, 5: 4, 3: 3, 2: 2, 1: 1, 0: 0}
        result.fix_quality = max(gga_data, key=lambda g: _fix_priority.get(g.quality, 0)).quality
        hdop_vals = [g.hdop for g in gga_data if g.hdop > 0.05 and g.quality > 0]
        alt_vals = [g.altitude for g in gga_data if g.altitude > 0]
        result.avg_hdop = statistics.mean(hdop_vals) if hdop_vals else 0.0
        result.last_hdop = hdop_vals[-1] if hdop_vals else 0.0
        result.avg_altitude = statistics.mean(alt_vals) if alt_vals else 0.0

        # ── GSV aggregation per band ──────────────────────────
        band_groups: Dict[str, List[GSVGroup]] = defaultdict(list)
        for gsv in gsv_groups:
            band_groups[gsv.band_name].append(gsv)

        # Determine primary band per constellation (first signal ID seen)
        first_signal: Dict[str, Optional[int]] = {}
        primary_bands: Set[str] = set()
        for gsv in gsv_groups:
            tid = gsv.talker_id
            sid = gsv.signal_id
            if tid not in first_signal:
                first_signal[tid] = sid
            if first_signal[tid] == sid:
                primary_bands.add(gsv.band_name)
        result.primary_bands = primary_bands

        for band_name, groups in band_groups.items():
            # Deduplicate by PRN — keep best SNR per satellite across all cycles
            prn_snr: Dict[int, float] = {}
            total_in_view = 0
            for grp in groups:
                total_in_view = max(total_in_view, grp.total_sats_in_view)
                for sat in grp.satellites:
                    if sat.snr > 0:
                        prn_snr[sat.prn] = max(prn_snr.get(sat.prn, 0.0), sat.snr)

            unique_snrs = list(prn_snr.values())

            result.per_band[band_name] = BandStats(
                band_name=band_name,
                avg_snr=statistics.mean(unique_snrs) if unique_snrs else 0.0,
                max_snr=max(unique_snrs) if unique_snrs else 0.0,
                tracked_satellites=len(unique_snrs),
                total_in_view=total_in_view,
            )

        if not result.per_band:
            result.success = False
            result.error_message = "No GSV data collected (no satellite SNR available)"

        # ── Evaluate criteria ──────────────────────────────────
        if criteria and criteria.is_enabled():
            result.criteria_pass, result.criteria_violations = criteria.evaluate(result)

        return result
