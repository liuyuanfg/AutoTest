"""
Pass/fail criteria evaluator for GNSS module test results.

Defines configurable thresholds and evaluates ModuleResult against them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional


@dataclass
class PerBandCriteria:
    """Per-frequency-band thresholds."""
    min_tracked: int = 0
    min_avg_snr: float = 0.0
    min_max_snr: float = 0.0

    def is_enabled(self) -> bool:
        return self.min_tracked > 0 or self.min_avg_snr > 0 or self.min_max_snr > 0


@dataclass
class Criteria:
    """User-defined pass/fail criteria for GNSS tests."""

    min_fix_quality: int = 0
    min_positioned_satellites: int = 0
    max_hdop: float = 0.0
    min_max_snr: float = 0.0       # highest SNR overall (across all bands)
    min_avg_snr: float = 0.0       # average SNR overall (across all bands)
    per_band: Dict[str, PerBandCriteria] = field(default_factory=dict)

    def is_enabled(self) -> bool:
        """Return True if any criterion has a non-zero threshold."""
        if self.min_fix_quality > 0:
            return True
        if self.min_positioned_satellites > 0:
            return True
        if self.max_hdop > 0:
            return True
        if self.min_max_snr > 0:
            return True
        if self.min_avg_snr > 0:
            return True
        for bc in self.per_band.values():
            if bc.is_enabled():
                return True
        return False

    def evaluate(self, result) -> Tuple[bool, List[str]]:
        """
        Evaluate a ModuleResult against these criteria.

        Returns (passed, list_of_violation_messages).
        If criteria are not enabled, always returns (True, []).
        """
        if not self.is_enabled():
            return True, []

        violations: List[str] = []

        # ── Global criteria ────────────────────────────────────
        if self.min_fix_quality > 0 and result.fix_quality < self.min_fix_quality:
            violations.append(
                f"Fix Quality {result.fix_quality} < min {self.min_fix_quality}"
            )

        if self.min_positioned_satellites > 0 and result.positioned_satellites < self.min_positioned_satellites:
            violations.append(
                f"Positioning Satellites {result.positioned_satellites} < min {self.min_positioned_satellites}"
            )

        if self.max_hdop > 0 and result.last_hdop > self.max_hdop:
            violations.append(
                f"Last HDOP {result.last_hdop:.2f} > max {self.max_hdop:.2f}"
            )

        if self.min_max_snr > 0:
            # highest max_snr across all bands
            best = max((s.max_snr for s in result.per_band.values()), default=0.0)
            if best < self.min_max_snr:
                violations.append(
                    f"Highest Max SNR {best:.1f} < min {self.min_max_snr:.1f}"
                )

        if self.min_avg_snr > 0:
            # average of per-band avg_snr values
            band_avgs = [s.avg_snr for s in result.per_band.values() if s.tracked_satellites > 0]
            overall = sum(band_avgs) / len(band_avgs) if band_avgs else 0.0
            if overall < self.min_avg_snr:
                violations.append(
                    f"Overall Avg SNR {overall:.1f} < min {self.min_avg_snr:.1f}"
                )

        # ── Per-band criteria ──────────────────────────────────
        for band_name, bc in self.per_band.items():
            if not bc.is_enabled():
                continue
            band_stat = result.per_band.get(band_name)
            if band_stat is None:
                violations.append(f"[{band_name}] No data collected for this band")
                continue

            if bc.min_tracked > 0 and band_stat.tracked_satellites < bc.min_tracked:
                violations.append(
                    f"[{band_name}] Tracked {band_stat.tracked_satellites} < min {bc.min_tracked}"
                )

            if bc.min_avg_snr > 0 and band_stat.avg_snr < bc.min_avg_snr:
                violations.append(
                    f"[{band_name}] Avg SNR {band_stat.avg_snr:.1f} < min {bc.min_avg_snr:.1f}"
                )

            if bc.min_max_snr > 0 and band_stat.max_snr < bc.min_max_snr:
                violations.append(
                    f"[{band_name}] Max SNR {band_stat.max_snr:.1f} < min {bc.min_max_snr:.1f}"
                )

        return len(violations) == 0, violations

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> Criteria:
        """Build Criteria from a config dict."""
        if not data:
            return cls()

        per_band: Dict[str, PerBandCriteria] = {}
        for band_name, bc_data in data.get("per_band", {}).items():
            per_band[band_name] = PerBandCriteria(
                min_tracked=bc_data.get("min_tracked", 0),
                min_avg_snr=float(bc_data.get("min_avg_snr", 0)),
                min_max_snr=float(bc_data.get("min_max_snr", 0)),
            )

        return cls(
            min_fix_quality=data.get("min_fix_quality", 0),
            min_positioned_satellites=data.get("min_positioned_satellites", 0),
            max_hdop=float(data.get("max_hdop", 0)),
            min_max_snr=float(data.get("min_max_snr", 0)),
            min_avg_snr=float(data.get("min_avg_snr", 0)),
            per_band=per_band,
        )
