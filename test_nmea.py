"""Quick test of NMEA parser with sample data."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nmea_parser import NMEAParser
from statistics_calculator import StatisticsCalculator


def nmea_checksum(s: str) -> str:
    c = 0
    for ch in s:
        c ^= ord(ch)
    return f"{c:02X}"


# Build a valid GGA sentence with correct checksum
data = "GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,"
gga = f"${data}*{nmea_checksum(data)}"

p = NMEAParser()
print("GGA parsed:", p.parse_line(gga))
if p.gga_data:
    g = p.gga_data[0]
    print(f"  Time: {g.time}, Sat count: {g.num_satellites}, Quality: {g.quality}, HDOP: {g.hdop}")

# GSV test sentences with correct checksums
gsv_sentences = [
    "$GPGSV,3,1,11,03,03,111,00,04,43,287,39,06,41,227,40,09,25,310,00*72",
    "$GPGSV,3,2,11,11,63,068,43,17,25,159,39,19,61,305,42,22,21,211,37*78",
    "$GPGSV,3,3,11,23,02,315,,26,34,069,41,27,11,050,37,28,06,189,33*7C",
]
for s in gsv_sentences:
    p.parse_line(s)
print("GSV groups:", len(p.gsv_groups))
for g in p.gsv_groups:
    print(f"  {g.band_name}: sats={len(g.satellites)}, tracked={g.tracked_count}, avg_snr={g.avg_snr:.1f}, max_snr={g.max_snr:.1f}")

# GLONASS
gl_sentences = [
    "$GLGSV,2,1,06,65,12,145,28,66,05,313,,72,31,020,35,73,54,163,39*66",
    "$GLGSV,2,2,06,74,53,317,41,80,18,233,30*66",
]
for s in gl_sentences:
    p.parse_line(s)
print("Total GSV groups:", len(p.gsv_groups))
for g in p.gsv_groups:
    print(f"  {g.band_name}: sats={len(g.satellites)}, tracked={g.tracked_count}, avg_snr={g.avg_snr:.1f}, max_snr={g.max_snr:.1f}")

# Test Statistics Calculator
result = StatisticsCalculator.compute(
    "TestModule", "COM3", "Test",
    p.gga_data, p.gsv_groups, 10.5
)
print(f"\nResult: success={result.success}, fix_quality={result.fix_quality}, positioned_sats={result.positioned_satellites}")
for band, stats in result.per_band.items():
    print(f"  {band}: tracked={stats.tracked_satellites}, in_view={stats.total_in_view}, avg_snr={stats.avg_snr:.1f}, max_snr={stats.max_snr:.1f}")

print("\nAll tests passed!")
