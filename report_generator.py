"""
PDF test report generator using ReportLab.

Produces a landscape A4 report with embedded Chinese font (MSYH) supporting:
  - Module-level summary (fix quality, satellites used, HDOP)
  - Per-frequency-band SNR statistics table
  - Overall pass/fail summary
  - Batch number and tester metadata
  - Chinese / English localization via i18n
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from statistics_calculator import ModuleResult, BandStats
from i18n import t

PAGE_PORTRAIT = A4
PAGE_LANDSCAPE = landscape(A4)

# ── Chinese font registration ──────────────────────────────
_CN_FONT_PATH = "C:/Windows/Fonts/msyh.ttc"
_CN_FONT_NAME = "MSYH"
try:
    pdfmetrics.registerFont(TTFont(_CN_FONT_NAME, _CN_FONT_PATH))
    _CN_FONT_READY = True
except Exception:
    pdfmetrics.registerFont(TTFont(_CN_FONT_NAME, "C:/Windows/Fonts/simsun.ttc"))
    _CN_FONT_READY = True
except Exception:
    _CN_FONT_READY = False


class ReportGenerator:
    """Generate a PDF test report from collected ModuleResult objects."""

    def __init__(self, output_dir: str = "./reports", prefix: str = "GNSS_Test_Report",
                 batch_no: str = "", tester: str = "") -> None:
        self.output_dir = output_dir
        self.prefix = prefix
        self.batch_no = batch_no
        self.tester = tester
        self.styles = getSampleStyleSheet()
        self._setup_styles()

    def _setup_styles(self) -> None:
        font_name = _CN_FONT_NAME if _CN_FONT_READY else "Helvetica"

        self.styles.add(ParagraphStyle(
            "Title_CN",
            parent=self.styles["Title"],
            fontName=font_name,
            fontSize=20,
            leading=26,
            spaceAfter=12,
            alignment=TA_CENTER,
        ))
        self.styles.add(ParagraphStyle(
            "Heading_CN",
            parent=self.styles["Heading2"],
            fontName=font_name,
            fontSize=14,
            leading=18,
            spaceAfter=8,
            spaceBefore=16,
        ))
        self.styles.add(ParagraphStyle(
            "Normal_CN",
            parent=self.styles["Normal"],
            fontName=font_name,
        ))
        self.styles.add(ParagraphStyle(
            "Cell_Center",
            parent=self.styles["Normal_CN"],
            fontName=font_name,
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
        ))
        self.styles.add(ParagraphStyle(
            "Cell_Left",
            parent=self.styles["Normal_CN"],
            fontName=font_name,
            fontSize=9,
            leading=12,
            alignment=TA_LEFT,
        ))
        self.styles.add(ParagraphStyle(
            "Cell_Wrap",
            parent=self.styles["Normal_CN"],
            fontName=font_name,
            fontSize=7,
            leading=9,
            alignment=TA_LEFT,
            wordWrap="CJK",
        ))
        self.styles.add(ParagraphStyle(
            "Footer",
            parent=self.styles["Normal_CN"],
            fontName=font_name,
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER,
        ))

    def generate(self, results: List[ModuleResult]) -> str:
        """Build and write the PDF. Returns the output file path."""
        os.makedirs(self.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.prefix}_{timestamp}.pdf"
        filepath = os.path.join(self.output_dir, filename)

        doc = SimpleDocTemplate(
            filepath,
            pagesize=PAGE_LANDSCAPE,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
            title="GNSS Module Test Report",
            author="AutoTest Tool",
        )

        story = self._build_story(results)
        doc.build(story)
        return filepath

    # ── story builder ──────────────────────────────────────────

    def _build_story(self, results: List[ModuleResult]) -> list:
        story = []

        # ── Title ──
        title = t("pdf_title")
        if self.batch_no:
            title += f"  –  {t('pdf_batch')}: {self.batch_no}"
        story.append(Paragraph(title, self.styles["Title_CN"]))
        story.append(Spacer(1, 3 * mm))

        # Meta line
        meta_parts = [f"{t('pdf_generated')}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]
        if self.tester:
            meta_parts.append(f"{t('pdf_tester')}: {self.tester}")
        if self.batch_no:
            meta_parts.append(f"{t('pdf_batch')}: {self.batch_no}")
        story.append(Paragraph("  |  ".join(meta_parts), self.styles["Footer"]))
        story.append(Spacer(1, 10 * mm))

        # ── Overall summary table ──
        story.append(Paragraph(t("pdf_summary_title"), self.styles["Heading_CN"]))
        story.append(self._build_summary_table(results))
        story.append(Spacer(1, 8 * mm))

        # ── Per-module detail ──
        story.append(PageBreak())
        story.append(Paragraph(t("pdf_detail_title"), self.styles["Heading_CN"]))
        story.append(Spacer(1, 4 * mm))

        for i, res in enumerate(results):
            if i > 0:
                story.append(PageBreak())
            story += self._build_module_detail(res)

        return story

    # ── summary table ──────────────────────────────────────────

    def _build_summary_table(self, results: List[ModuleResult]) -> Table:
        headers = [
            t("col_sn"), t("col_test_station"), t("col_port"),
            t("col_status"), t("col_fw"), t("col_fix_q"),
            t("col_sat_used"), t("col_tracked"), t("col_hdop"),
        ]
        data = [headers]

        for r in results:
            status = t("status_pass") if r.overall_pass else t("status_fail")
            fw_text = r.boot_info.fw_version if r.boot_info else ""
            sn_text = r.boot_info.sn if r.boot_info else ""
            data.append([
                sn_text if sn_text else "",
                r.module_id,
                r.port,
                status,
                Paragraph(fw_text, self.styles["Cell_Wrap"]) if fw_text else "",
                str(r.fix_quality),
                str(r.positioned_satellites),
                str(r.total_tracked_sats),
                f"{r.last_hdop:.2f}",
            ])

        return self._styled_table(data, col_widths=[90, 110, 65, 55, 130, 50, 65, 65, 60])

    # ── per-module detail ──────────────────────────────────────

    def _build_module_detail(self, res: ModuleResult) -> list:
        story = []

        # Module header
        header_text = f"{res.module_id}  [{res.port}]"
        if res.description:
            header_text += f"  —  {res.description}"
        story.append(Paragraph(header_text, self.styles["Heading_CN"]))

        # Key metrics
        metrics = [
        ]
        # Boot info section
        bi = res.boot_info
        if bi and bi.found_any:
            metrics.extend([
                f"FW Version: {bi.fw_version}",
                f"ROM Version: {bi.rom_version}",
            f"Bootloader: {bi.bootloader_version}",
            f"SN: {bi.sn}",
            f"Chip ID: {bi.chip_id}",
            ])
        metrics.extend([
            f"Status: {'PASS' if res.overall_pass else 'FAIL'}",
            f"Fix Quality: {res.fix_quality}",
                f"Satellites Used (GGA): {res.positioned_satellites}",
            f"Total Tracked: {res.total_tracked_sats}",
            f"HDOP (last): {res.last_hdop:.2f}",
            f"HDOP (avg): {res.avg_hdop:.2f}",
            f"Altitude: {res.avg_altitude:.1f} m",
            f"GGA Samples: {res.gga_count}",
            f"GSV Groups: {res.gsv_group_count}",
            f"Collection Duration: {res.duration_seconds:.1f} s",
        ])
        for m in metrics:
            story.append(Paragraph(m, self.styles["Normal_CN"]))
        story.append(Spacer(1, 3 * mm))

        if res.error_message:
            story.append(Paragraph(
                f"<font color='red'>Error: {res.error_message}</font>",
                self.styles["Normal_CN"],
            ))
            story.append(Spacer(1, 3 * mm))

        # Criteria violations
        if res.criteria_violations:
            story.append(Paragraph("<font color='red'>Criteria Violations:</font>", self.styles["Normal_CN"]))
            for v in res.criteria_violations:
                story.append(Paragraph(f"<font color='red'>  - {v}</font>", self.styles["Normal_CN"]))
            story.append(Spacer(1, 3 * mm))

        # Frequency-band SNR table
        if res.per_band:
            story.append(Paragraph("Frequency Band SNR Statistics:", self.styles["Normal_CN"]))
            story.append(Spacer(1, 2 * mm))
            story.append(self._build_band_table(res.per_band))
        else:
            story.append(Paragraph("<i>No frequency-band data.</i>", self.styles["Normal_CN"]))

        return story

    def _build_band_table(self, per_band: dict) -> Table:
        headers = ["Frequency Band", "Tracked Sats", "In View", "Avg SNR(dB)", "Max SNR(dB)"]
        data = [headers]

        for band_name, stats in per_band.items():
            stats: BandStats
            data.append([
                band_name,
                str(stats.tracked_satellites),
                str(stats.total_in_view),
                f"{stats.avg_snr:.1f}",
                f"{stats.max_snr:.1f}",
            ])

        return self._styled_table(data, col_widths=[140, 90, 70, 100, 100])

    # ── helpers ────────────────────────────────────────────────

    def _styled_table(self, data: list, col_widths=None) -> Table:
        t = Table(data, colWidths=col_widths, repeatRows=1)
        font_body = _CN_FONT_NAME if _CN_FONT_READY else "Helvetica"
        style = TableStyle([
            # header
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E75B6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), font_body),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            # body
            ("FONTNAME", (0, 1), (-1, -1), font_body),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            # grid
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F7FB")]),
            # padding
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
        t.setStyle(style)
        return t
