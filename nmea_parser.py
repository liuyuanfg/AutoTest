"""
NMEA-0183 sentence parser for GGA and GSV sentences.
Handles multi-constellation, multi-frequency GNSS data.
"""
import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict


# ── Talker ID → Constellation name mapping ────────────────────
TALKER_TO_CONSTELLATION: Dict[str, str] = {
    "GP": "GPS",
    "GL": "GLONASS",
    "GA": "Galileo",
    "GB": "BeiDou",
    "GQ": "QZSS",
    "GI": "NavIC",
    "GN": "Combined",
}

# ── (signal_id, talker) → frequency band label ────────────────
SIGNAL_BAND_MAP: Dict[str, str] = {
    "1,GP":  "GPS L1",
    "6,GP":  "GPS L2",
    "8,GP":  "GPS L5",
    "1,GL":  "GLO G1",
    "3,GL":  "GLO G2",
    "7,GA":  "GAL E1",
    "1,GA":  "GAL E5a",    
    "2,GA":  "GAL E5b",
    "1,GB":  "BDS B1I",
    "6,GB":  "BDS B2b",
    "5,GB":  "BDS B2a",
    "1,GQ":  "QZSS L1",
    "6,GQ":  "QZSS L5",
    "8,GQ":  "QZSS L5",
    "1,GI":  "NavIC L5",
}

DEFAULT_BANDS: Dict[str, str] = {
    "GP": "GPS L1",
    "GL": "GLO G1",
    "GA": "GAL E1",
    "GB": "BDS B1I",
    "GQ": "QZSS L1",
    "GI": "NavIC L5",
    "GN": "Combined",
}


@dataclass
class SatelliteInfo:
    """Single satellite entry from a GSV sentence."""
    prn: int
    elevation: int     # degrees
    azimuth: int       # degrees
    snr: float         # dB-Hz, 0 = not tracked


@dataclass
class GSVGroup:
    """A complete group of GSV sentences for one constellation+signal."""
    talker_id: str
    signal_id: Optional[int]
    total_sats_in_view: int
    satellites: List[SatelliteInfo] = field(default_factory=list)

    @property
    def constellation(self) -> str:
        return TALKER_TO_CONSTELLATION.get(self.talker_id, f"Unknown({self.talker_id})")

    @property
    def band_name(self) -> str:
        if self.signal_id is not None:
            key = f"{self.signal_id},{self.talker_id}"
            return SIGNAL_BAND_MAP.get(key, f"{self.constellation} SigID-{self.signal_id}")
        return DEFAULT_BANDS.get(self.talker_id, f"{self.constellation} L1")

    @property
    def tracked_count(self) -> int:
        """Count of satellites with non-zero SNR (actually tracked)."""
        return sum(1 for s in self.satellites if s.snr > 0)

    @property
    def snr_values(self) -> List[float]:
        return [s.snr for s in self.satellites if s.snr > 0]

    @property
    def avg_snr(self) -> float:
        vals = self.snr_values
        return sum(vals) / len(vals) if vals else 0.0

    @property
    def max_snr(self) -> float:
        vals = self.snr_values
        return max(vals) if vals else 0.0


@dataclass
class GGAData:
    """Parsed GGA (GPS Fix Data) sentence."""
    time: str           # HHMMSS.SS
    latitude: float     # decimal degrees
    longitude: float    # decimal degrees
    quality: int        # 0=invalid, 1=GPS, 2=DGPS, 4=RTK fixed, 5=RTK float
    num_satellites: int  # satellites used in position fix
    hdop: float
    altitude: float     # meters above geoid


class NMEAParser:
    """
    Incremental NMEA-0183 parser.

    Feed raw lines via :meth:`parse_line`.  Completed GGA records and
    GSV groups are appended to internal lists for later statistics.
    """

    NMEA_RE = re.compile(r"\$([A-Z]{2})([A-Z]{3}),(.*)\*([0-9A-Fa-f]{2})$")

    def __init__(self) -> None:
        self.gga_data: List[GGAData] = []
        self.gsv_groups: List[GSVGroup] = []

        # Temporary buffer for assembling multi-sentence GSV groups.
        # Key: (talker_id, signal_id, num_messages)
        self._gsv_buffer: Dict = {}

        # Cycle tracking: a cycle = one complete set of RMC+GGA+GSV sentences
        self.complete_cycles: int = 0
        self._cycle_has_gga: bool = False
        self._cycle_has_gsv: bool = False
        self._last_gsv_cycle: int = 0  # gsv_groups count at last cycle boundary

    # ── public ─────────────────────────────────────────────────

    def parse_line(self, raw: str) -> bool:
        """Parse one raw NMEA text line. Returns True if a valid sentence was parsed."""
        raw = raw.strip()
        m = self.NMEA_RE.match(raw)
        if not m:
            return False

        talker, sentence_type, data_str, cksum_hex = m.groups()

        # Checksum verification
        expected = 0
        for c in f"{talker}{sentence_type},{data_str}":
            expected ^= ord(c)
        if expected != int(cksum_hex, 16):
            return False

        fields = data_str.split(",")

        if sentence_type == "GGA":
            self._parse_gga(fields)
            self._cycle_has_gga = True
        elif sentence_type == "GSV":
            self._parse_gsv(talker, fields)
        elif sentence_type == "RMC":
            # RMC marks the start of a new cycle — finalize previous cycle
            if self._cycle_has_gga and self._cycle_has_gsv:
                self.complete_cycles += 1
            self._cycle_has_gga = False
            self._cycle_has_gsv = False

        return True

    def reset(self) -> None:
        """Clear all accumulated data for a fresh test run."""
        self.gga_data.clear()
        self.gsv_groups.clear()
        self._gsv_buffer.clear()
        self.complete_cycles = 0
        self._cycle_has_gga = False
        self._cycle_has_gsv = False
        self._last_gsv_cycle = 0

    def flush_pending_gsv(self) -> None:
        """Commit all incomplete GSV groups in the buffer.

        Call this at the end of data collection so partial groups from
        data loss are not silently discarded.
        """
        for key, buf in list(self._gsv_buffer.items()):
            talker, signal_id = key
            self.gsv_groups.append(GSVGroup(
                talker_id=talker,
                signal_id=signal_id,
                total_sats_in_view=buf["total_sats"],
                satellites=buf["satellites"],
            ))
        self._gsv_buffer.clear()

    # ── GGA ────────────────────────────────────────────────────

    def _parse_gga(self, fields: List[str]) -> None:
        if len(fields) < 14:
            return
        try:
            lat = self._latlon_dd(fields[1], fields[2])
            lon = self._latlon_dd(fields[3], fields[4])
            quality = int(fields[5]) if fields[5] else 0
            num_sats = int(fields[6]) if fields[6] else 0
            # HDOP: only valid when fix quality > 0 and value is in reasonable range
            raw_hdop = fields[7].strip() if len(fields) > 7 else ""
            hdop = 0.0
            if raw_hdop and quality > 0:
                try:
                    hdop = float(raw_hdop)
                    if hdop <= 0.0 or hdop > 50.0:
                        hdop = 0.0
                except ValueError:
                    hdop = 0.0
            alt = float(fields[8]) if len(fields) > 8 and fields[8] else 0.0
            self.gga_data.append(GGAData(
                time=fields[0], latitude=lat, longitude=lon,
                quality=quality, num_satellites=num_sats,
                hdop=hdop, altitude=alt,
            ))
        except (ValueError, IndexError):
            pass

    # ── GSV ────────────────────────────────────────────────────

    def _parse_gsv(self, talker: str, fields: List[str]) -> None:
        """
        Assembles a GSV group from multiple sentences.

        Sentence format:
          $--GSV, numMsg, msgNum, totalSats, {PRN, elev, azim, SNR}[, signalID]*CS

        When msgNum == numMsg the group is complete.
        """
        if len(fields) < 4:
            return
        try:
            num_messages = int(fields[0])
            msg_number   = int(fields[1])
            total_sats   = int(fields[2]) if fields[2] else 0
        except (ValueError, IndexError):
            return

        # Detect optional signal-id (NMEA 4.10+)
        signal_id: Optional[int] = None
        sat_fields = fields[3:]
        # Each satellite occupies 4 fields; remaining 0-1 field = signal_id
        sat_count = len(sat_fields) // 4
        remainder = len(sat_fields) % 4
        if remainder == 1:
            # Last field is signal-id
            try:
                signal_id = int(sat_fields[-1]) if sat_fields[-1] else None
            except (ValueError, IndexError):
                signal_id = None
            sat_fields = sat_fields[:-1]

        # Parse satellite entries
        satellites: List[SatelliteInfo] = []
        for i in range(sat_count):
            base = i * 4
            try:
                prn = int(sat_fields[base]) if sat_fields[base] else 0
                elev = int(sat_fields[base + 1]) if sat_fields[base + 1] else 0
                azim = int(sat_fields[base + 2]) if sat_fields[base + 2] else 0
                snr = int(sat_fields[base + 3]) if sat_fields[base + 3] else 0
                if prn > 0:
                    satellites.append(SatelliteInfo(prn=prn, elevation=elev, azimuth=azim, snr=float(snr)))
            except (IndexError, ValueError):
                continue

        # Group key — NOT including num_messages (it can change across cycles)
        key = (talker, signal_id)

        if key not in self._gsv_buffer:
            self._gsv_buffer[key] = {
                "total_sats": total_sats,
                "satellites": [],
                "received": set(),
                "num_messages": num_messages,
            }

        buf = self._gsv_buffer[key]
        buf["total_sats"] = max(buf["total_sats"], total_sats)
        buf["num_messages"] = max(buf["num_messages"], num_messages)
        for sat in satellites:
            # Replace satellite with same PRN if new data has higher SNR
            existing = next((s for s in buf["satellites"] if s.prn == sat.prn), None)
            if existing:
                if sat.snr > existing.snr or (sat.snr == existing.snr and sat.elevation > existing.elevation):
                    buf["satellites"].remove(existing)
                    buf["satellites"].append(sat)
            else:
                buf["satellites"].append(sat)
        buf["received"].add(msg_number)

        # When all messages in the group have arrived, finalize the group
        if len(buf["received"]) >= buf["num_messages"]:
            self.gsv_groups.append(GSVGroup(
                talker_id=talker,
                signal_id=signal_id,
                total_sats_in_view=buf["total_sats"],
                satellites=list(buf["satellites"]),
            ))
            del self._gsv_buffer[key]
            self._cycle_has_gsv = True

    # ── utilities ──────────────────────────────────────────────

    @staticmethod
    def _latlon_dd(value: str, direction: str) -> float:
        """Convert ddmm.mmmmm (NMEA) to decimal degrees."""
        if not value or not direction:
            return 0.0
        try:
            degrees = int(value[:2]) if direction in ("N", "S") else int(value[:3])
            minutes = float(value[len(str(degrees)):])
        except (ValueError, IndexError):
            return 0.0
        dd = degrees + minutes / 60.0
        if direction in ("S", "W"):
            dd = -dd
        return dd
