"""
GNSS 模块批量自动化测试工具的图形界面 (GUI)。

基于 Tkinter 的图形界面，功能包括：
  - 测试工位列表管理 (增删改，端口/波特率下拉选择)
  - 串口和测试参数配置
  - 测试过程中的实时日志 (每工位独立标签页)
  - 后台线程执行测试
  - 每工位独立进度条
  - 结果汇总表格
  - PDF 报告打开
  - 中英文界面切换

Tkinter-based graphical interface with:
  - Module list management (add / edit / delete, dropdown for port/baud)
  - Serial port and test parameter configuration
  - Real-time logging (per-module tabs)
  - Test execution in background thread
  - Per-module progress bars
  - Results summary table
  - PDF report opening
  - Chinese / English language switching
"""
from __future__ import annotations

import os
import sys
import time
import re
import json
import queue
import threading
import subprocess
from typing import List, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import yaml

# Enable DPI awareness on Windows for sharp text
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# Ensure the project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app_paths import get_config_path, get_app_dir
from i18n import t, set_language, get_language

from serial_manager import enumerate_ports
from statistics_calculator import ModuleResult
from report_generator import ReportGenerator
from criteria import Criteria, PerBandCriteria
from main import (
    load_config, run_module_test, simulate_module_test,
    summarise_result, _nmea_checksum, _SAMPLE_GGA, _SAMPLE_GSV_GROUPS, _build_gsv_sentences,
)

# ═══════════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_CONFIG_PATH = get_config_path("config.yaml")
LOG_MAX_LINES = 2000
UPDATE_INTERVAL_MS = 150

# Colour tags for the log widget
LOG_TAG_INFO = "info"
LOG_TAG_WARN = "warn"
LOG_TAG_ERROR = "error"
LOG_TAG_PASS = "pass"
LOG_TAG_FAIL = "fail"


# ═══════════════════════════════════════════════════════════════════════
#  Results window (table of all module results)
# ═══════════════════════════════════════════════════════════════════════

def _center_on_parent(dlg: tk.Toplevel, parent: tk.Tk) -> None:
    """Center a dialog relative to its parent window."""
    dlg.update_idletasks()
    pw, ph = parent.winfo_width(), parent.winfo_height()
    px, py = parent.winfo_rootx(), parent.winfo_rooty()
    dw, dh = dlg.winfo_width(), dlg.winfo_height()
    cx = px + (pw - dw) // 2
    cy = py + (ph - dh) // 2
    dlg.geometry(f"+{cx}+{cy}")

class ResultsWindow(tk.Toplevel):
    """Popup window displaying a sortable table of test results."""

    def __init__(self, parent: tk.Tk, results: List[ModuleResult], report_path: str = "") -> None:
        super().__init__(parent)
        self.title("Test Results")
        self.geometry("1100x500")
        self.results = results
        self.report_path = report_path

        self._build_ui()
        _center_on_parent(self, parent)

    def _build_ui(self) -> None:
        # ── Treeview ──
        columns = ("sn", "module", "port", "status", "fw", "bootloader", "fix_q", "sat_used", "sat_tracked", "hdop", "error")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")
        col_defs = [
            ("sn", "SN", 80),
            ("module", "Test Station", 90),
            ("port", "Port", 60),
            ("status", "Result", 55),
            ("fw", "FW Version", 130),
            ("bootloader", "Bootloader", 80),
            ("fix_q", "Fix Q", 45),
            ("sat_used", "Sat Used", 60),
            ("sat_tracked", "Tracked", 55),
            ("hdop", "HDOP", 50),
            ("error", "Error", 280),
        ]
        for col_id, heading, width in col_defs:
            self.tree.heading(col_id, text=heading, command=lambda c=col_id: self._sort_by(c))
            self.tree.column(col_id, width=width, anchor="center")
        self.tree.column("error", anchor="w")
        self.tree.column("fw", anchor="w")

        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Populate
        for r in self.results:
            bi = r.boot_info
            self.tree.insert("", "end", values=(
                bi.sn if bi else "",
                r.module_id, r.port,
                "PASS" if r.overall_pass else "FAIL",
                bi.fw_version if bi else "",
                bi.bootloader_version if bi else "",
                r.fix_quality, r.positioned_satellites,
                r.total_tracked_sats,
                f"{r.last_hdop:.2f}",
                r.error_message or "",
            ))

    def _sort_by(self, col: str) -> None:
        rows = [(self.tree.set(item, col), item) for item in self.tree.get_children("")]
        try:
            rows.sort(key=lambda x: float(x[0]) if x[0].replace(".", "").replace("-", "").isdigit() else x[0].lower())
        except (ValueError, TypeError):
            rows.sort(key=lambda x: x[0].lower())
        for idx, (_, item) in enumerate(rows):
            self.tree.move(item, "", idx)


# ═══════════════════════════════════════════════════════════════════════
#  Main Application
# ═══════════════════════════════════════════════════════════════════════

class App(tk.Tk):
    """Main GUI application."""

    def __init__(self) -> None:
        super().__init__()
        self.title("GNSS Module Batch Auto Test")
        self.geometry("1200x700")
        self.minsize(900, 550)

        self.config_path = DEFAULT_CONFIG_PATH
        self.config: Dict[str, Any] = {}
        self._results: List[ModuleResult] = []

        # Threading
        self._test_thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._msg_queue: queue.Queue = queue.Queue()
        self._modules_total = 0
        self._modules_done = 0
        self._cycle_progress: Dict[str, tuple] = {}
        self._total_cycles_target = 0

        # i18n: track all dynamic labels for language switching
        self._i18n_widgets: Dict[str, list] = {}  # i18n_key → [widget1, widget2, ...]

        # Build UI
        self._build_menu()
        self._build_widgets()
        self._poll_queue()

        # Load config
        self._load_config_to_ui()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _i18n_widget(self, widget, i18n_key: str, mode: str = "text") -> None:
        """Register a widget for i18n updates."""
        if i18n_key not in self._i18n_widgets:
            self._i18n_widgets[i18n_key] = []
        self._i18n_widgets[i18n_key].append((widget, mode))

    def _i18n_label(self, parent, i18n_key: str, **kwargs) -> ttk.Label:
        """Create a ttk.Label and register it for i18n."""
        lbl = ttk.Label(parent, text=t(i18n_key), **kwargs)
        self._i18n_widget(lbl, i18n_key)
        return lbl

    def _i18n_button(self, parent, i18n_key: str, **kwargs) -> ttk.Button:
        """Create a ttk.Button and register it for i18n."""
        btn = ttk.Button(parent, text=t(i18n_key), **kwargs)
        self._i18n_widget(btn, i18n_key)
        return btn

    def _i18n_checkbutton(self, parent, i18n_key: str, variable, **kwargs) -> ttk.Checkbutton:
        """Create a ttk.Checkbutton and register it for i18n."""
        cb = ttk.Checkbutton(parent, text=t(i18n_key), variable=variable, **kwargs)
        self._i18n_widget(cb, i18n_key)
        return cb

    def _i18n_labelframe(self, parent, i18n_key: str, **kwargs) -> ttk.LabelFrame:
        """Create a ttk.LabelFrame and register it for i18n."""
        lf = ttk.LabelFrame(parent, text=t(i18n_key), **kwargs)
        self._i18n_widget(lf, i18n_key, "label")
        return lf

    def _apply_language_to_ui(self) -> None:
        """Refresh all i18n-registered widgets after language switch."""
        for key, widgets in self._i18n_widgets.items():
            tt = t(key)
            for widget, mode in widgets:
                try:
                    widget["text"] = tt
                except Exception:
                    try:
                        widget.configure(text=tt)
                    except Exception:
                        pass
        # Refresh treeview column headers
        if hasattr(self, "_mod_col_heads"):
            for col_id, i18n_key in self._mod_col_heads.items():
                try:
                    self.mod_tree.heading(col_id, text=t(i18n_key))
                except Exception:
                    pass
        if hasattr(self, "_band_col_heads"):
            for col_id, i18n_key in self._band_col_heads.items():
                try:
                    self.band_criteria_tree.heading(col_id, text=t(i18n_key))
                except Exception:
                    pass
        # Refresh notebook tab labels
        if self._left_notebook:
            self._left_notebook.tab(0, text=t("tab_test_stations"))
            self._left_notebook.tab(1, text=t("tab_parameters"))
            self._left_notebook.tab(2, text=t("tab_criteria"))
        if self._log_notebook:
            self._log_notebook.tab(0, text=t("tab_log"))
        # Update status bar
        if hasattr(self, "status_var"):
            self.status_var.set(t("lbl_ready"))

    # ── Menu bar ────────────────────────────────────────────────

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        self.configure(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label=t("menu_load_config"), command=self._load_config_dialog)
        file_menu.add_command(label=t("menu_save_config"), command=self._save_config_dialog)
        file_menu.add_separator()
        file_menu.add_command(label=t("menu_open_reports"), command=self._open_reports_folder)
        file_menu.add_separator()
        file_menu.add_command(label=t("menu_exit"), command=self._on_close)
        menubar.add_cascade(label=t("menu_file"), menu=file_menu)

        test_menu = tk.Menu(menubar, tearoff=False)
        test_menu.add_command(label=t("menu_start_test"), command=self.start_test)
        test_menu.add_command(label=t("menu_stop_test"), command=self.stop_test)
        test_menu.add_separator()
        test_menu.add_command(label=t("menu_show_results"), command=self._show_results)
        menubar.add_cascade(label=t("menu_test"), menu=test_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label=t("menu_refresh_ports"), command=self._refresh_ports)

        # Language submenu
        lang_menu = tk.Menu(help_menu, tearoff=False)
        lang_menu.add_command(label=t("lang_en"), command=lambda: self._switch_language("EN"))
        lang_menu.add_command(label=t("lang_cn"), command=lambda: self._switch_language("CN"))
        help_menu.add_cascade(label=t("menu_language"), menu=lang_menu)

        help_menu.add_separator()
        help_menu.add_command(label=t("menu_about"), command=self._show_about)
        menubar.add_cascade(label=t("menu_help"), menu=help_menu)

    def _switch_language(self, lang: str) -> None:
        """Switch UI language and rebuild menu."""
        set_language(lang)
        self._build_menu()
        self._apply_language_to_ui()

    # ── Main layout ─────────────────────────────────────────────

    def _build_widgets(self) -> None:
        # ── PanedWindow for left/right split ──
        pw = ttk.PanedWindow(self, orient="horizontal")
        pw.pack(fill="both", expand=True, padx=6, pady=(6, 0))

        # Left panel
        left_frame = ttk.Frame(pw)
        pw.add(left_frame, weight=4)

        # Right panel
        right_frame = ttk.Frame(pw)
        pw.add(right_frame, weight=6)

        # ── Left: Notebook with Config tabs ──
        self._left_notebook = ttk.Notebook(left_frame)
        self._left_notebook.pack(fill="both", expand=True)

        # Tab 1: Modules
        tab_modules = ttk.Frame(self._left_notebook)
        self._left_notebook.add(tab_modules, text=t("tab_test_stations"))
        self._build_modules_tab(tab_modules)

        # Tab 2: Serial & Test Parameters
        tab_params = ttk.Frame(self._left_notebook)
        self._left_notebook.add(tab_params, text=t("tab_parameters"))
        self._build_params_tab(tab_params)

        # Tab 3: Pass Criteria
        tab_criteria = ttk.Frame(self._left_notebook)
        self._left_notebook.add(tab_criteria, text=t("tab_criteria"))
        self._build_criteria_tab(tab_criteria)

        # ── Right: Per-module Log Tabs ──
        log_frame = self._i18n_labelframe(right_frame, "lbl_runtime_log", padding=(4, 4))
        log_frame.pack(fill="both", expand=True)

        self._log_notebook = ttk.Notebook(log_frame)
        self._log_notebook.pack(fill="both", expand=True)

        # Shared tab for general messages
        shared_tab = ttk.Frame(self._log_notebook)
        self._log_notebook.add(shared_tab, text=t("tab_log"))
        self._shared_log = tk.Text(shared_tab, wrap="word", state="disabled", font=("Consolas", 9))
        self._shared_log.pack(fill="both", expand=True)
        shared_sb = ttk.Scrollbar(shared_tab, orient="vertical", command=self._shared_log.yview)
        shared_sb.pack(side="right", fill="y")
        self._shared_log.configure(yscrollcommand=shared_sb.set)
        self._setup_log_tags(self._shared_log)

        # Per-module log widgets (created on test start)
        self._mod_logs: Dict[str, tk.Text] = {}
        self._mod_log_tabs: Dict[str, ttk.Frame] = {}

        # Per-module progress bars
        self._mod_progress_frame = ttk.Frame(right_frame)
        self._mod_progress_frame.pack(fill="x", padx=4, pady=(2, 0))
        self._mod_progress_bars: Dict[str, ttk.Progressbar] = {}
        self._mod_progress_labels: Dict[str, ttk.Label] = {}

        # ── Bottom: Control bar ──
        control_frame = ttk.Frame(self)
        control_frame.pack(fill="x", padx=6, pady=4)

        self.btn_start = self._i18n_button(control_frame, "btn_start", command=self.start_test)
        self.btn_start.pack(side="left", padx=(0, 4))

        self.btn_stop = self._i18n_button(control_frame, "btn_stop", command=self.stop_test)
        self.btn_stop["state"] = "disabled"
        self.btn_stop.pack(side="left", padx=(0, 12))

        self.simulate_var = tk.BooleanVar(value=False)
        self._i18n_checkbutton(control_frame, "btn_simulate", self.simulate_var).pack(side="left", padx=(0, 12))

        ttk.Separator(control_frame, orient="vertical").pack(side="left", fill="y", padx=6)

        self._i18n_button(control_frame, "btn_results", command=self._show_results).pack(side="left", padx=4)
        self._i18n_button(control_frame, "btn_refresh", command=self._refresh_ports).pack(side="left", padx=4)
        self.btn_refresh_ports = None  # placeholder for language refresh compat

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(control_frame, textvariable=self.status_var, relief="sunken", anchor="w", padding=(6, 2)).pack(
            side="right", fill="x", expand=True, padx=(12, 0)
        )

        # Progress bar
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(control_frame, variable=self.progress_var, maximum=100, length=180)
        self.progress_bar.pack(side="right", padx=(4, 0))

    @staticmethod
    def _setup_log_tags(log_widget: tk.Text) -> None:
        log_widget.tag_configure(LOG_TAG_INFO, foreground="#333333")
        log_widget.tag_configure(LOG_TAG_WARN, foreground="#CC8800")
        log_widget.tag_configure(LOG_TAG_ERROR, foreground="#CC2222")
        log_widget.tag_configure(LOG_TAG_PASS, foreground="#228B22", font=("Consolas", 9, "bold"))
        log_widget.tag_configure(LOG_TAG_FAIL, foreground="#CC2222", font=("Consolas", 9, "bold"))

    # ════════════════════════════════════════════════════════════
    #  Tab: Modules
    # ════════════════════════════════════════════════════════════

    def _build_modules_tab(self, parent: ttk.Frame) -> None:
        # Toolbar
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill="x", pady=(4, 2))

        self._i18n_button(toolbar, "tab_modules_add", command=self._add_module).pack(side="left", padx=(0, 4))
        self._i18n_button(toolbar, "tab_modules_edit", command=self._edit_module).pack(side="left", padx=(0, 4))
        self._i18n_button(toolbar, "tab_modules_delete", command=self._delete_module).pack(side="left", padx=(0, 4))

        # Treeview
        tv_frame = ttk.Frame(parent)
        tv_frame.pack(fill="both", expand=True)

        cols = ("id", "port", "baudrate", "description")
        self.mod_tree = ttk.Treeview(tv_frame, columns=cols, show="headings", selectmode="browse")
        self._mod_col_heads = {
            "id": "col_test_station", "port": "col_port",
            "baudrate": "col_baudrate", "description": "col_description",
        }
        for col_id, i18n_key in self._mod_col_heads.items():
            self.mod_tree.heading(col_id, text=t(i18n_key))
            self.mod_tree.column(col_id, width={"id": 100, "port": 75, "baudrate": 80, "description": 150}[col_id], anchor="center")
        self.mod_tree.column("description", anchor="w")

        vsb = ttk.Scrollbar(tv_frame, orient="vertical", command=self.mod_tree.yview)
        self.mod_tree.configure(yscrollcommand=vsb.set)
        self.mod_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.mod_tree.bind("<Double-1>", lambda e: self._edit_module())

    def _add_module(self) -> None:
        dlg = ModuleDialog(self, title="Add Module")
        if dlg.result:
            self.mod_tree.insert("", "end", values=(
                dlg.result["id"], dlg.result["port"],
                dlg.result.get("baudrate", ""), dlg.result.get("description", ""),
            ))

    def _edit_module(self) -> None:
        sel = self.mod_tree.selection()
        if not sel:
            messagebox.showinfo("Edit", "Select a module first.")
            return
        item = sel[0]
        vals = self.mod_tree.item(item, "values")
        current = {"id": vals[0], "port": vals[1], "baudrate": vals[2], "description": vals[3]}
        dlg = ModuleDialog(self, title="Edit Module", initial=current)
        if dlg.result:
            self.mod_tree.item(item, values=(
                dlg.result["id"], dlg.result["port"],
                dlg.result.get("baudrate", ""), dlg.result.get("description", ""),
            ))

    def _delete_module(self) -> None:
        sel = self.mod_tree.selection()
        if sel and messagebox.askyesno("Delete", "Remove selected module?"):
            self.mod_tree.delete(sel[0])

    # ════════════════════════════════════════════════════════════
    #  Tab: Parameters
    # ════════════════════════════════════════════════════════════

    def _build_params_tab(self, parent: ttk.Frame) -> None:
        # ── Serial defaults ──
        sframe = self._i18n_labelframe(parent, "lbl_serial_defaults", padding=(8, 6))
        sframe.pack(fill="x", padx=4, pady=(4, 8))

        fields = [
            ("baudrate", "lbl_baudrate", 8),
            ("bytesize", "lbl_bytesize", 4),
            ("parity", "lbl_parity", 4),
            ("stopbits", "lbl_stopbits", 4),
            ("timeout", "lbl_timeout", 6),
        ]
        self._serial_entries: Dict[str, tk.StringVar] = {}
        for i, (key, i18n_key, width) in enumerate(fields):
            self._i18n_label(sframe, i18n_key).grid(row=i, column=0, sticky="e", padx=(0, 6), pady=2)
            var = tk.StringVar()
            ttk.Entry(sframe, textvariable=var, width=width).grid(row=i, column=1, sticky="w", pady=2)
            self._serial_entries[key] = var

        # ── Test parameters ──
        tframe = self._i18n_labelframe(parent, "lbl_test_params", padding=(8, 6))
        tframe.pack(fill="x", padx=4, pady=4)

        t_fields = [
            ("wait_poweron_timeout", "lbl_poweron_timeout", 8),
            ("sample_count", "lbl_sample_count", 8),
            ("sample_duration", "lbl_sample_duration", 12),
        ]
        self._test_entries: Dict[str, tk.StringVar] = {}
        for i, (key, i18n_key, width) in enumerate(t_fields):
            self._i18n_label(tframe, i18n_key).grid(row=i, column=0, sticky="e", padx=(0, 6), pady=2)
            var = tk.StringVar()
            ttk.Entry(tframe, textvariable=var, width=width).grid(row=i, column=1, sticky="w", pady=2)
            self._test_entries[key] = var

        # Collect mode
        self._i18n_label(tframe, "lbl_collect_mode").grid(row=3, column=0, sticky="e", padx=(0, 6), pady=2)
        self.collect_mode_var = tk.StringVar(value="count")
        cm = ttk.Combobox(tframe, textvariable=self.collect_mode_var, values=["count", "duration"], width=8, state="readonly")
        cm.grid(row=3, column=1, sticky="w", pady=2)

        # ── Output parameters ──
        oframe = self._i18n_labelframe(parent, "lbl_output", padding=(8, 6))
        oframe.pack(fill="x", padx=4, pady=4)

        self._i18n_label(oframe, "lbl_report_dir").grid(row=0, column=0, sticky="e", padx=(0, 6), pady=2)
        self.report_dir_var = tk.StringVar(value="./reports")
        ttk.Entry(oframe, textvariable=self.report_dir_var, width=22).grid(row=0, column=1, sticky="w", pady=2)

        self._i18n_label(oframe, "lbl_report_prefix").grid(row=1, column=0, sticky="e", padx=(0, 6), pady=2)
        self.report_prefix_var = tk.StringVar(value="GNSS_Test_Report")
        ttk.Entry(oframe, textvariable=self.report_prefix_var, width=22).grid(row=1, column=1, sticky="w", pady=2)

        # ── Test info ──
        tframe2 = self._i18n_labelframe(parent, "lbl_test_info", padding=(8, 6))
        tframe2.pack(fill="x", padx=4, pady=4)

        self._i18n_label(tframe2, "lbl_batch_no").grid(row=0, column=0, sticky="e", padx=(0, 6), pady=2)
        self.batch_no_var = tk.StringVar()
        ttk.Entry(tframe2, textvariable=self.batch_no_var, width=22).grid(row=0, column=1, sticky="w", pady=2)

        self._i18n_label(tframe2, "lbl_tester").grid(row=1, column=0, sticky="e", padx=(0, 6), pady=2)
        self.tester_var = tk.StringVar()
        ttk.Entry(tframe2, textvariable=self.tester_var, width=22).grid(row=1, column=1, sticky="w", pady=2)

    # ════════════════════════════════════════════════════════════
    #  Tab: Criteria
    # ════════════════════════════════════════════════════════════

    def _build_criteria_tab(self, parent: ttk.Frame) -> None:
        # ── Global criteria ──
        gframe = self._i18n_labelframe(parent, "lbl_global_criteria", padding=(8, 6))
        gframe.pack(fill="x", padx=4, pady=(4, 8))

        c_fields = [
            ("min_fix_quality", "lbl_min_fix_quality"),
            ("min_positioned_satellites", "lbl_min_positioned"),
            ("max_hdop", "lbl_max_hdop"),
            ("min_max_snr", "lbl_min_max_snr"),
            ("min_avg_snr", "lbl_min_avg_snr"),
        ]
        self._criteria_entries: Dict[str, tk.StringVar] = {}
        for i, (key, i18n_key) in enumerate(c_fields):
            self._i18n_label(gframe, i18n_key).grid(row=i, column=0, sticky="e", padx=(0, 6), pady=2)
            var = tk.StringVar(value="0")
            ttk.Entry(gframe, textvariable=var, width=8).grid(row=i, column=1, sticky="w", pady=2)
            self._criteria_entries[key] = var

        # ── Per-band criteria ──
        bframe = self._i18n_labelframe(parent, "lbl_per_band", padding=(8, 6))
        bframe.pack(fill="both", expand=True, padx=4, pady=4)

        toolbar = ttk.Frame(bframe)
        toolbar.pack(fill="x", pady=(0, 4))
        self._i18n_button(toolbar, "btn_add_band", command=self._add_band_criteria).pack(side="left", padx=(0, 4))
        self._i18n_button(toolbar, "btn_del_band", command=self._delete_band_criteria).pack(side="left")

        tv_frame = ttk.Frame(bframe)
        tv_frame.pack(fill="both", expand=True)

        bcols = ("band", "min_tracked", "min_avg_snr", "min_max_snr")
        self.band_criteria_tree = ttk.Treeview(tv_frame, columns=bcols, show="headings", selectmode="browse", height=6)
        self._band_col_heads = {
            "band": "col_band", "min_tracked": "col_min_tracked",
            "min_avg_snr": "col_min_avg_snr", "min_max_snr": "col_min_max_snr",
        }
        for col_id, i18n_key in self._band_col_heads.items():
            self.band_criteria_tree.heading(col_id, text=t(i18n_key))
            self.band_criteria_tree.column(col_id, width={"band": 130, "min_tracked": 85, "min_avg_snr": 85, "min_max_snr": 85}[col_id], anchor="center")
        self.band_criteria_tree.column("band", anchor="w")

        b_vsb = ttk.Scrollbar(tv_frame, orient="vertical", command=self.band_criteria_tree.yview)
        self.band_criteria_tree.configure(yscrollcommand=b_vsb.set)
        self.band_criteria_tree.pack(side="left", fill="both", expand=True)
        b_vsb.pack(side="right", fill="y")

        self.band_criteria_tree.bind("<Double-1>", lambda e: self._edit_band_criteria())

    def _add_band_criteria(self) -> None:
        dlg = BandCriteriaDialog(self, title="Add Band Criteria")
        if dlg.result:
            self.band_criteria_tree.insert("", "end", values=(
                dlg.result["band"], dlg.result.get("min_tracked", "0"),
                dlg.result.get("min_avg_snr", "0"), dlg.result.get("min_max_snr", "0"),
            ))

    def _edit_band_criteria(self) -> None:
        sel = self.band_criteria_tree.selection()
        if not sel:
            return
        item = sel[0]
        vals = self.band_criteria_tree.item(item, "values")
        current = {"band": vals[0], "min_tracked": vals[1], "min_avg_snr": vals[2], "min_max_snr": vals[3]}
        dlg = BandCriteriaDialog(self, title="Edit Band Criteria", initial=current)
        if dlg.result:
            self.band_criteria_tree.item(item, values=(
                dlg.result["band"], dlg.result.get("min_tracked", "0"),
                dlg.result.get("min_avg_snr", "0"), dlg.result.get("min_max_snr", "0"),
            ))

    def _delete_band_criteria(self) -> None:
        sel = self.band_criteria_tree.selection()
        if sel and messagebox.askyesno("Delete", "Remove selected band criteria?"):
            self.band_criteria_tree.delete(sel[0])

    # ════════════════════════════════════════════════════════════
    #  Config load / save
    # ════════════════════════════════════════════════════════════

    def _load_config_to_ui(self) -> None:
        """Load config.yaml and populate UI widgets."""
        try:
            self.config = load_config(self.config_path)
        except Exception as e:
            self._log_shared(t("log_config_fail", str(e)), LOG_TAG_ERROR)
            self.config = {"serial": {}, "modules": [], "test": {}, "output": {}}
            return

        # Clear existing entries
        for item in self.mod_tree.get_children():
            self.mod_tree.delete(item)
        for item in self.band_criteria_tree.get_children():
            self.band_criteria_tree.delete(item)

        # Modules
        for m in self.config.get("modules", []):
            self.mod_tree.insert("", "end", values=(
                m.get("id", ""), m.get("port", ""),
                str(m.get("baudrate", "")), m.get("description", ""),
            ))

        # Serial defaults
        ser = self.config.get("serial", {})
        for key, var in self._serial_entries.items():
            var.set(str(ser.get(key, "")))

        # Test params
        tst = self.config.get("test", {})
        for key, var in self._test_entries.items():
            var.set(str(tst.get(key, "")))
        self.collect_mode_var.set(tst.get("collect_mode", "count"))

        # Output
        out = self.config.get("output", {})
        self.report_dir_var.set(out.get("report_dir", "./reports"))
        self.report_prefix_var.set(out.get("report_prefix", "GNSS_Test_Report"))

        # Test info
        meta = self.config.get("meta", {})
        self.batch_no_var.set(meta.get("batch_no", ""))
        self.tester_var.set(meta.get("tester", ""))

        # Criteria
        cri = self.config.get("criteria", {})
        for key, var in self._criteria_entries.items():
            var.set(str(cri.get(key, 0)))

        for band_name, bc_data in cri.get("per_band", {}).items():
            # Skip if already in tree (avoid duplicates from multiple loads)
            already_there = False
            for item in self.band_criteria_tree.get_children():
                if self.band_criteria_tree.item(item, "values")[0] == band_name:
                    already_there = True
                    break
            if already_there:
                continue
            self.band_criteria_tree.insert("", "end", values=(
                band_name,
                str(bc_data.get("min_tracked", 0)),
                str(bc_data.get("min_avg_snr", 0)),
                str(bc_data.get("min_max_snr", 0)),
            ))

        self._log_shared(t("log_config_loaded", self.config_path), LOG_TAG_INFO)

    def _build_config_dict(self) -> dict:
        """Read UI state back into a config dict."""
        modules = []
        for item in self.mod_tree.get_children():
            vals = self.mod_tree.item(item, "values")
            md = {"id": vals[0], "port": vals[1]}
            if vals[2]:
                try:
                    md["baudrate"] = int(vals[2])
                except ValueError:
                    pass
            if vals[3]:
                md["description"] = vals[3]
            modules.append(md)

        # Per-band criteria
        per_band = {}
        for item in self.band_criteria_tree.get_children():
            vals = self.band_criteria_tree.item(item, "values")
            per_band[vals[0]] = {
                "min_tracked": int(vals[1]) if vals[1].isdigit() else 0,
                "min_avg_snr": float(vals[2]) if vals[2].replace(".", "").replace("-", "").isdigit() else 0,
                "min_max_snr": float(vals[3]) if vals[3].replace(".", "").replace("-", "").isdigit() else 0,
            }

        cfg = {
            "serial": {k: self._parse_value(v.get()) for k, v in self._serial_entries.items()},
            "modules": modules,
            "test": {k: self._parse_value(v.get()) for k, v in self._test_entries.items()},
            "output": {
                "report_dir": self.report_dir_var.get(),
                "report_prefix": self.report_prefix_var.get(),
            },
            "criteria": {
                **{k: self._parse_value(v.get()) for k, v in self._criteria_entries.items()},
                "per_band": per_band,
            },
            "meta": {
                "batch_no": self.batch_no_var.get(),
                "tester": self.tester_var.get(),
            },
        }
        return cfg

    @staticmethod
    def _parse_value(s: str) -> Any:
        """Parse a string to int/float/str as appropriate."""
        s = s.strip()
        if not s:
            return ""
        if s.lower() == "n":
            return "N"
        try:
            if "." in s or "e" in s.lower():
                return float(s)
            return int(s)
        except ValueError:
            return s

    def _save_config_dialog(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".yaml", filetypes=[("YAML", "*.yaml"), ("All Files", "*.*")],
            initialdir=os.path.dirname(self.config_path),
        )
        if not path:
            return
        cfg = self._build_config_dict()
        try:
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            self.config_path = path
            self._log_shared(t("log_config_saved", path), LOG_TAG_INFO)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save config:\n{e}")

    def _load_config_dialog(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("YAML", "*.yaml"), ("All Files", "*.*")],
            initialdir=os.path.dirname(self.config_path),
        )
        if not path:
            return
        self.config_path = path
        # Clear existing
        for item in self.mod_tree.get_children():
            self.mod_tree.delete(item)
        self._load_config_to_ui()

    # ════════════════════════════════════════════════════════════
    #  COM port refresh
    # ════════════════════════════════════════════════════════════

    def _refresh_ports(self) -> None:
        try:
            ports = enumerate_ports()
            self._log_shared(t("log_ports", ", ".join(ports)) if ports else t("log_ports_none"), LOG_TAG_INFO)
        except Exception as e:
            self._log_shared(t("log_ports_fail", str(e)), LOG_TAG_ERROR)

    # ════════════════════════════════════════════════════════════
    #  Test control
    # ════════════════════════════════════════════════════════════

    def start_test(self) -> None:
        """Start a test run in a background thread."""
        if self._test_thread and self._test_thread.is_alive():
            messagebox.showinfo("Info", "A test is already running.")
            return

        # Read UI config
        self.config = self._build_config_dict()
        modules_cfg = self.config.get("modules", [])
        if not modules_cfg:
            messagebox.showwarning("Warning", "No modules configured. Add modules first.")
            return

        self._results.clear()
        self._stop_flag.clear()
        self.progress_var.set(0)

        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.status_var.set(t("lbl_running"))

        self._log_shared("=" * 50, LOG_TAG_INFO)
        self._log_shared(t("log_test_started"), LOG_TAG_INFO)
        self._log_shared("=" * 50, LOG_TAG_INFO)

        simulate = self.simulate_var.get()
        if simulate:
            self._log_shared(t("dlg_sim_mode"), LOG_TAG_WARN)

        self._test_thread = threading.Thread(
            target=self._test_runner,
            args=(modules_cfg, self.config.get("serial", {}), self.config.get("test", {}),
                  self.config.get("output", {}), self.config.get("meta", {}), simulate,
                  Criteria.from_dict(self.config.get("criteria"))),
            daemon=True,
        )
        self._test_thread.start()

    def stop_test(self) -> None:
        """Signal the running test to stop."""
        if self._test_thread and self._test_thread.is_alive():
            self._stop_flag.set()
            self._log_shared(t("log_stop_requested"), LOG_TAG_WARN)
            self.status_var.set("Stopping ...")

    def _test_runner(
        self,
        modules_cfg: list,
        serial_defaults: dict,
        test_cfg: dict,
        output_cfg: dict,
        meta_cfg: dict,
        simulate: bool,
        criteria: Criteria,
    ) -> None:
        """Background thread: execute tests on all modules in parallel."""
        results: List[ModuleResult] = []
        total = len(modules_cfg)

        def _run_one(mod_cfg: dict) -> ModuleResult:
            module_id = mod_cfg.get("id", "?")
            port = mod_cfg.get("port", "?")
            try:
                if simulate:
                    return simulate_module_test(mod_cfg, test_cfg,
                                                log_cb=self._make_log_cb(module_id),
                                                progress_cb=self._make_progress_cb(module_id),
                                                criteria=criteria,
                                                stop_event=self._stop_flag)
                else:
                    return run_module_test(mod_cfg, serial_defaults, test_cfg,
                                           log_cb=self._make_log_cb(module_id),
                                           progress_cb=self._make_progress_cb(module_id),
                                           criteria=criteria,
                                           stop_event=self._stop_flag)
            except Exception as e:
                return ModuleResult(
                    module_id=module_id, port=port,
                    description=mod_cfg.get("description", ""),
                    success=False, error_message=str(e),
                )

        # Create per-module log tabs and progress bars
        self._msg_queue.put(("log", (t("log_preparing", total), LOG_TAG_INFO)))
        self._create_module_log_tabs(modules_cfg)
        self._create_module_progress_bars(modules_cfg)
        self._modules_total = total
        self._modules_done = 0
        self._cycle_progress.clear()
        sample_count = test_cfg.get("sample_count", 10)
        self._total_cycles_target = total * sample_count
        self._msg_queue.put(("progress", (0,)))
        for m in modules_cfg:
            self._msg_queue.put(("log", (f"  {m.get('id')}  @ {m.get('port')}", LOG_TAG_INFO)))
        self._msg_queue.put(("log", (t("log_starting", total), LOG_TAG_INFO)))

        with ThreadPoolExecutor(max_workers=total) as executor:
            future_map = {executor.submit(_run_one, m): m for m in modules_cfg}
            for future in as_completed(future_map):
                if self._stop_flag.is_set() and not future.done():
                    future.cancel()
                mod_cfg = future_map[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = ModuleResult(
                        module_id=mod_cfg.get("id", "?"),
                        port=mod_cfg.get("port", "?"),
                        description=mod_cfg.get("description", ""),
                        success=False, error_message=str(e),
                    )
                results.append(result)
                tag = LOG_TAG_PASS if result.overall_pass else LOG_TAG_FAIL
                self._msg_queue.put(("module_done", ()))
                self._msg_queue.put(("log", (summarise_result(result), tag)))

        # Restore original order
        id_order = {m.get("id", ""): i for i, m in enumerate(modules_cfg)}
        results.sort(key=lambda r: id_order.get(r.module_id, 999))

        self._msg_queue.put(("progress", (100,)))
        self._results = results

        # Generate PDF
        if results:
            out_dir = output_cfg.get("report_dir", "./reports")
            if not os.path.isabs(out_dir):
                out_dir = os.path.join(get_app_dir(), out_dir)
            report_gen = ReportGenerator(
                output_dir=out_dir,
                prefix=output_cfg.get("report_prefix", "GNSS_Test_Report"),
                batch_no=meta_cfg.get("batch_no", ""),
                tester=meta_cfg.get("tester", ""),
            )
            try:
                report_path = report_gen.generate(results)
                self._msg_queue.put(("log", (t("log_report_saved", os.path.abspath(report_path)), LOG_TAG_INFO)))
                self._msg_queue.put(("report_path", (report_path,)))
            except Exception as e:
                self._msg_queue.put(("log", (t("log_report_fail", str(e)), LOG_TAG_ERROR)))

        pass_count = sum(1 for r in results if r.overall_pass)
        fail_count = len(results) - pass_count
        self._msg_queue.put(("log", ("=" * 50, LOG_TAG_INFO)))
        self._msg_queue.put(("log", (t("log_test_complete", len(results), pass_count, fail_count), LOG_TAG_INFO)))
        self._msg_queue.put(("log", ("=" * 50, LOG_TAG_INFO)))
        self._msg_queue.put(("done", (pass_count, fail_count)))

    # ════════════════════════════════════════════════════════════
    #  Message queue polling (thread-safe UI updates)
    # ════════════════════════════════════════════════════════════

    def _poll_queue(self) -> None:
        """Drain the message queue and update the UI."""
        while True:
            try:
                msg = self._msg_queue.get_nowait()
            except queue.Empty:
                break

            mtype, data = msg
            if mtype == "log":
                self._log_shared(*data)
            elif mtype == "mod_log":
                self._log_module(*data)
            elif mtype == "module_done":
                self._modules_done += 1
            elif mtype == "cycle_progress":
                mid, cur, total = data
                self._cycle_progress[mid] = (cur, total)
                # Update per-module progress bar
                if mid in self._mod_progress_bars:
                    pct = min(100, int(cur / total * 100)) if total > 0 else 0
                    self._mod_progress_bars[mid]["value"] = pct
                    self._mod_progress_labels[mid]["text"] = f"{cur}/{total}"
                # Update overall progress bar
                if self._total_cycles_target > 0:
                    summed = sum(v[0] for v in self._cycle_progress.values())
                    pct = min(100, int(summed / self._total_cycles_target * 100))
                    self.progress_var.set(pct)
            elif mtype == "progress":
                self.progress_var.set(data[0])
            elif mtype == "report_path":
                self._last_report_path = data[0]
            elif mtype == "done":
                self.btn_start.configure(state="normal")
                self.btn_stop.configure(state="disabled")
                self.status_var.set("Ready")
                self._show_results()

        self.after(UPDATE_INTERVAL_MS, self._poll_queue)

    # ════════════════════════════════════════════════════════════
    #  Logging
    # ════════════════════════════════════════════════════════════

    def _make_log_cb(self, module_id: str = ""):
        """Return a callback that pushes log messages to the module's own log tab."""
        def cb(msg: str) -> None:
            self._msg_queue.put(("mod_log", (module_id, msg, LOG_TAG_INFO)))
        return cb

    def _make_progress_cb(self, module_id: str = ""):
        """Return a callback that pushes progress messages and updates the bar."""
        def cb(msg: str) -> None:
            self._msg_queue.put(("mod_log", (module_id, msg, LOG_TAG_WARN)))
            # Parse cycle count for progress bar: "collecting 5/10 cycles..."
            m = re.match(r".*collecting\s+(\d+)/(\d+)\s+cycles", msg)
            if m:
                cur = int(m.group(1))
                total = int(m.group(2))
                self._msg_queue.put(("cycle_progress", (module_id, cur, total)))
        return cb

    def _log_shared(self, text: str, tag: str = LOG_TAG_INFO) -> None:
        """Append a line to the shared log tab."""
        self._log_text(self._shared_log, text, tag)

    def _log_module(self, module_id: str, text: str, tag: str = LOG_TAG_INFO) -> None:
        """Append a line to a module's dedicated log tab."""
        if module_id not in self._mod_logs:
            return
        self._log_text(self._mod_logs[module_id], text, tag)

    @staticmethod
    def _log_text(widget: tk.Text, text: str, tag: str) -> None:
        """Append a line to a Text widget with auto-scroll and trim."""
        widget.configure(state="normal")
        widget.insert("end", text + "\n", tag)
        lines = int(widget.index("end-1c").split(".")[0])
        if lines > LOG_MAX_LINES:
            widget.delete("1.0", f"{lines - LOG_MAX_LINES + 500}.0")
        widget.configure(state="disabled")
        widget.see("end")

    def _create_module_log_tabs(self, modules_cfg: list) -> None:
        """Create per-module log tabs in the notebook."""
        # Remove old module tabs
        for tab_frame in self._mod_log_tabs.values():
            self._log_notebook.forget(tab_frame)
        self._mod_logs.clear()
        self._mod_log_tabs.clear()

        for m in modules_cfg:
            mid = m.get("id", "?")
            tab = ttk.Frame(self._log_notebook)
            self._log_notebook.add(tab, text=mid)
            txt = tk.Text(tab, wrap="word", state="disabled", font=("Consolas", 9))
            txt.pack(fill="both", expand=True)
            sb = ttk.Scrollbar(tab, orient="vertical", command=txt.yview)
            sb.pack(side="right", fill="y")
            txt.configure(yscrollcommand=sb.set)
            self._setup_log_tags(txt)
            self._mod_logs[mid] = txt
            self._mod_log_tabs[mid] = tab

    def _create_module_progress_bars(self, modules_cfg: list) -> None:
        """Create per-module progress bars."""
        for widget in self._mod_progress_frame.winfo_children():
            widget.destroy()
        self._mod_progress_bars.clear()
        self._mod_progress_labels.clear()

        for m in modules_cfg:
            mid = m.get("id", "?")
            row = ttk.Frame(self._mod_progress_frame)
            row.pack(fill="x", pady=1)
            lbl = ttk.Label(row, text=f"{mid}", width=14, anchor="e")
            lbl.pack(side="left", padx=(0, 4))
            bar = ttk.Progressbar(row, length=150, maximum=100, value=0)
            bar.pack(side="left", fill="x", expand=True, padx=(0, 4))
            cnt = ttk.Label(row, text="0/0", width=8, anchor="w")
            cnt.pack(side="left")
            self._mod_progress_bars[mid] = bar
            self._mod_progress_labels[mid] = cnt

    # ════════════════════════════════════════════════════════════
    #  Results / Reports
    # ════════════════════════════════════════════════════════════

    def _show_results(self) -> None:
        if not self._results:
            messagebox.showinfo("Info", "No test results available. Run a test first.")
            return
        report_path = getattr(self, "_last_report_path", "")
        ResultsWindow(self, self._results, report_path)

    def _open_reports_folder(self) -> None:
        report_dir = self.report_dir_var.get() or "./reports"
        if not os.path.isabs(report_dir):
            report_dir = os.path.join(get_app_dir(), report_dir)
        abs_dir = os.path.abspath(report_dir)
        os.makedirs(abs_dir, exist_ok=True)
        try:
            os.startfile(abs_dir)
        except Exception:
            messagebox.showinfo("Reports Dir", abs_dir)

    # ════════════════════════════════════════════════════════════
    #  Misc
    # ════════════════════════════════════════════════════════════

    def _show_about(self) -> None:
        messagebox.showinfo(
            "About",
            "GNSS Module Batch Auto Test\n\n"
            "NMEA-0183 GGA / GSV Parser\n"
            "Serial Port Manager\n"
            "PDF Report Generator\n\n"
            "v1.0",
        )

    def _on_close(self) -> None:
        if self._test_thread and self._test_thread.is_alive():
            self._stop_flag.set()
            self._test_thread.join(timeout=2.0)
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════
#  Module editor dialog
# ═══════════════════════════════════════════════════════════════════════

class ModuleDialog(tk.Toplevel):
    """Popup dialog for adding / editing a module entry."""

    BAUD_RATES = ["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"]

    def __init__(self, parent: tk.Tk, title: str = "Module", initial: Optional[Dict[str, str]] = None) -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result: Optional[Dict[str, str]] = None
        self.grab_set()
        self.transient(parent)

        init = initial or {}

        # Refresh port list from system
        try:
            from serial.tools.list_ports import comports
            self._available_ports = [p.device for p in comports()]
        except Exception:
            self._available_ports = []

        frame = ttk.Frame(self, padding=(16, 12))
        frame.pack()

        fields = [("id", "Test Station"), ("port", "COM Port"), ("baudrate", "Baud Rate"), ("description", "Description")]
        self._vars: Dict[str, tk.StringVar] = {}
        self._combos: Dict[str, ttk.Combobox] = {}

        for i, (key, label) in enumerate(fields):
            ttk.Label(frame, text=f"{label}:").grid(row=i, column=0, sticky="e", padx=(0, 8), pady=4)
            var = tk.StringVar(value=init.get(key, ""))
            self._vars[key] = var

            if key == "port":
                cmb = ttk.Combobox(frame, textvariable=var, values=self._available_ports, width=16)
                cmb.grid(row=i, column=1, sticky="w", pady=4)
                self._combos[key] = cmb
            elif key == "baudrate":
                cmb = ttk.Combobox(frame, textvariable=var, values=self.BAUD_RATES, width=16)
                if not var.get():
                    var.set("115200")
                cmb.grid(row=i, column=1, sticky="w", pady=4)
                self._combos[key] = cmb
            elif key == "description":
                ttk.Entry(frame, textvariable=var, width=28).grid(row=i, column=1, sticky="w", pady=4)
            else:
                ttk.Entry(frame, textvariable=var, width=18).grid(row=i, column=1, sticky="w", pady=4)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=len(fields), column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btn_frame, text="OK", command=self._on_ok).pack(side="left", padx=(0, 8))
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="left")

        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self.destroy())
        _center_on_parent(self, parent)
        self.wait_window()

    def _on_ok(self) -> None:
        r = {k: v.get().strip() for k, v in self._vars.items()}
        if not r["id"] or not r["port"]:
            messagebox.showwarning("Validation", "Test Station and Port are required.", parent=self)
            return
        self.result = r
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════
#  Band criteria editor dialog
# ═══════════════════════════════════════════════════════════════════════

class BandCriteriaDialog(tk.Toplevel):
    """Popup dialog for adding / editing a per-band criteria entry."""

    def __init__(self, parent: tk.Tk, title: str = "Band Criteria", initial: Optional[Dict[str, str]] = None) -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result: Optional[Dict[str, str]] = None
        self.grab_set()
        self.transient(parent)

        init = initial or {}

        frame = ttk.Frame(self, padding=(16, 12))
        frame.pack()

        fields = [("band", "Band Name"), ("min_tracked", "Min Tracked Sats"), ("min_avg_snr", "Min Avg SNR"), ("min_max_snr", "Min Max SNR")]
        self._vars: Dict[str, tk.StringVar] = {}

        for i, (key, label) in enumerate(fields):
            ttk.Label(frame, text=f"{label}:").grid(row=i, column=0, sticky="e", padx=(0, 8), pady=4)
            var = tk.StringVar(value=init.get(key, "0" if key != "band" else ""))
            self._vars[key] = var
            ttk.Entry(frame, textvariable=var, width=24).grid(row=i, column=1, sticky="w", pady=4)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=len(fields), column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btn_frame, text="OK", command=self._on_ok).pack(side="left", padx=(0, 8))
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="left")

        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self.destroy())
        _center_on_parent(self, parent)
        self.wait_window()

    def _on_ok(self) -> None:
        r = {k: v.get().strip() for k, v in self._vars.items()}
        if not r["band"]:
            messagebox.showwarning("Validation", "Band Name is required.", parent=self)
            return
        self.result = r
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════

def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
