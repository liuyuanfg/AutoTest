"""
Simple i18n support for Chinese/English switching.
"""
from __future__ import annotations

STRINGS = {
    # ── Language names ──
    "lang_en": {"EN": "English", "CN": "English"},
    "lang_cn": {"EN": "中文", "CN": "中文"},
    "lang_label": {"EN": "Language", "CN": "语言"},

    # ── Menu ──
    "menu_file": {"EN": "File", "CN": "文件"},
    "menu_test": {"EN": "Test", "CN": "测试"},
    "menu_help": {"EN": "Help", "CN": "帮助"},
    "menu_load_config": {"EN": "Load Config...", "CN": "加载配置..."},
    "menu_save_config": {"EN": "Save Config...", "CN": "保存配置..."},
    "menu_open_reports": {"EN": "Open Reports Folder", "CN": "打开报告目录"},
    "menu_exit": {"EN": "Exit", "CN": "退出"},

    # ── Modules tab ──
    "tab_modules_add": {"EN": "+ Add", "CN": "+ 添加"},
    "tab_modules_edit": {"EN": "✎ Edit", "CN": "✎ 编辑"},
    "tab_modules_delete": {"EN": "✕ Delete", "CN": "✕ 删除"},

    # ── Module dialog ──
    "dlg_module_title_add": {"EN": "Add Test Station", "CN": "添加测试工位"},
    "dlg_module_title_edit": {"EN": "Edit Test Station", "CN": "编辑测试工位"},
    "dlg_module_id": {"EN": "Test Station:", "CN": "测试工位:"},
    "dlg_module_port": {"EN": "COM Port:", "CN": "COM端口:"},
    "dlg_module_baud": {"EN": "Baud Rate:", "CN": "波特率:"},
    "dlg_module_desc": {"EN": "Description:", "CN": "描述:"},

    # ── Band dialog ──
    "dlg_band_title_add": {"EN": "Add Band Criteria", "CN": "添加频段标准"},
    "dlg_band_title_edit": {"EN": "Edit Band Criteria", "CN": "编辑频段标准"},
    "dlg_band_name": {"EN": "Band Name:", "CN": "频段名称:"},
    "dlg_band_min_tracked": {"EN": "Min Tracked Sats:", "CN": "最少跟踪卫星:"},
    "dlg_band_min_avg_snr": {"EN": "Min Avg SNR:", "CN": "最低平均SNR:"},
    "dlg_band_min_max_snr": {"EN": "Min Max SNR:", "CN": "最低最大SNR:"},
    "menu_start_test": {"EN": "Start Test", "CN": "开始测试"},
    "menu_stop_test": {"EN": "Stop Test", "CN": "停止测试"},
    "menu_show_results": {"EN": "Show Results", "CN": "显示结果"},
    "menu_refresh_ports": {"EN": "Refresh COM Ports", "CN": "刷新串口"},
    "menu_about": {"EN": "About", "CN": "关于"},
    "menu_language": {"EN": "Language", "CN": "语言"},

    # ── Tabs ──
    "tab_test_stations": {"EN": "Test Stations", "CN": "测试工位"},
    "tab_parameters": {"EN": "Parameters", "CN": "参数设置"},
    "tab_criteria": {"EN": "Criteria", "CN": "判定标准"},
    "tab_log": {"EN": "Log", "CN": "日志"},

    # ── Columns ──
    "col_sn": {"EN": "SN", "CN": "序列号"},
    "col_test_station": {"EN": "Test Station", "CN": "测试工位"},
    "col_port": {"EN": "Port", "CN": "串口"},
    "col_baudrate": {"EN": "Baud Rate", "CN": "波特率"},
    "col_description": {"EN": "Description", "CN": "描述"},
    "col_status": {"EN": "Result", "CN": "结果"},
    "col_fw": {"EN": "FW Version", "CN": "固件版本"},
    "col_bootloader": {"EN": "Bootloader", "CN": "引导程序"},
    "col_fix_q": {"EN": "Fix Q", "CN": "定位质量"},
    "col_sat_used": {"EN": "Sat Used", "CN": "定位卫星"},
    "col_tracked": {"EN": "Tracked", "CN": "跟踪卫星"},
    "col_hdop": {"EN": "HDOP", "CN": "HDOP"},
    "col_error": {"EN": "Error", "CN": "错误信息"},
    "col_band": {"EN": "Band Name", "CN": "频段"},
    "col_min_tracked": {"EN": "Min Tracked", "CN": "最少跟踪数"},
    "col_min_avg_snr": {"EN": "Min Avg SNR", "CN": "最低平均SNR"},
    "col_min_max_snr": {"EN": "Min Max SNR", "CN": "最低最大SNR"},

    # ── Buttons ──
    "btn_start": {"EN": ">  Start Test", "CN": ">  开始测试"},
    "btn_stop": {"EN": "#  Stop", "CN": "#  停止"},
    "btn_simulate": {"EN": "Simulate", "CN": "模拟模式"},
    "btn_results": {"EN": "Results", "CN": "结果"},
    "btn_refresh": {"EN": "Refresh Ports", "CN": "刷新串口"},
    "btn_add": {"EN": "+ Add", "CN": "+ 添加"},
    "btn_edit": {"EN": "✎ Edit", "CN": "✎ 编辑"},
    "btn_delete": {"EN": "✕ Delete", "CN": "✕ 删除"},
    "btn_add_band": {"EN": "+ Add Band", "CN": "+ 添加频段"},
    "btn_del_band": {"EN": "✕ Delete Band", "CN": "✕ 删除频段"},

    # ── Labels ──
    "lbl_serial_defaults": {"EN": "Serial Port Defaults", "CN": "串口默认参数"},
    "lbl_test_params": {"EN": "Test Parameters", "CN": "测试参数"},
    "lbl_output": {"EN": "Output", "CN": "输出设置"},
    "lbl_test_info": {"EN": "Test Info", "CN": "测试信息"},
    "lbl_global_criteria": {"EN": "Global Criteria (0 = disabled)", "CN": "全局标准 (0=禁用)"},
    "lbl_per_band": {"EN": "Per-Band Criteria", "CN": "各频段标准"},
    "lbl_runtime_log": {"EN": "Runtime Log", "CN": "运行日志"},
    "lbl_report_dir": {"EN": "Report Dir:", "CN": "报告目录:"},
    "lbl_report_prefix": {"EN": "Report Prefix:", "CN": "报告前缀:"},
    "lbl_batch_no": {"EN": "Batch No:", "CN": "批次号:"},
    "lbl_tester": {"EN": "Tester:", "CN": "测试员:"},
    "lbl_baudrate": {"EN": "Baud Rate:", "CN": "波特率:"},
    "lbl_bytesize": {"EN": "Byte Size:", "CN": "数据位:"},
    "lbl_parity": {"EN": "Parity:", "CN": "校验位:"},
    "lbl_stopbits": {"EN": "Stop Bits:", "CN": "停止位:"},
    "lbl_timeout": {"EN": "Timeout (s):", "CN": "超时(秒):"},
    "lbl_poweron_timeout": {"EN": "Power-on Timeout (s):", "CN": "上电超时(秒):"},
    "lbl_sample_count": {"EN": "Sample Count:", "CN": "采样次数:"},
    "lbl_sample_duration": {"EN": "Sample Duration (s, 0=off):", "CN": "采样时长(秒, 0=关闭):"},
    "lbl_collect_mode": {"EN": "Collect Mode:", "CN": "采集模式:"},
    "lbl_min_fix_quality": {"EN": "Min Fix Quality:", "CN": "最低定位质量:"},
    "lbl_min_positioned": {"EN": "Min Positioning Satellites:", "CN": "最少定位卫星:"},
    "lbl_max_hdop": {"EN": "Max HDOP:", "CN": "最大HDOP:"},
    "lbl_min_max_snr": {"EN": "Min Max SNR (dB):", "CN": "最低最大SNR(dB):"},
    "lbl_min_avg_snr": {"EN": "Min Avg SNR (dB):", "CN": "最低平均SNR(dB):"},
    "lbl_ready": {"EN": "Ready", "CN": "就绪"},
    "lbl_running": {"EN": "Running...", "CN": "运行中..."},
    "lbl_stopping": {"EN": "Stopping...", "CN": "停止中..."},

    # ── Dialog titles ──
    "dlg_add_module": {"EN": "Add Test Station", "CN": "添加测试工位"},
    "dlg_edit_module": {"EN": "Edit Test Station", "CN": "编辑测试工位"},
    "dlg_add_band": {"EN": "Add Band Criteria", "CN": "添加频段标准"},
    "dlg_edit_band": {"EN": "Edit Band Criteria", "CN": "编辑频段标准"},
    "dlg_results": {"EN": "Test Results", "CN": "测试结果"},
    "dlg_about_title": {"EN": "About", "CN": "关于"},
    "dlg_about_text": {
        "EN": "GNSS Module Batch Auto Test\n\nNMEA-0183 GGA/GSV Parser\nSerial Port Manager\nPDF Report Generator\n\nv1.0",
        "CN": "GNSS模块批量自动化测试工具\n\nNMEA-0183 GGA/GSV 解析\n多串口同步管理\nPDF测试报告生成\n\n版本 1.0",
    },
    "dlg_validation_station": {"EN": "Test Station and Port are required.", "CN": "测试工位和端口为必填项。"},
    "dlg_select_first": {"EN": "Select an entry first.", "CN": "请先选择一条记录。"},
    "dlg_confirm_delete": {"EN": "Remove selected entry?", "CN": "确认删除选中的记录？"},
    "dlg_no_results": {"EN": "No test results available. Run a test first.", "CN": "没有测试结果，请先运行测试。"},
    "dlg_test_running": {"EN": "A test is already running.", "CN": "测试正在进行中。"},
    "dlg_no_modules": {"EN": "No modules configured. Add modules first.", "CN": "没有配置测试工位，请先添加。"},
    "dlg_sim_mode": {"EN": "[SIMULATION MODE] No hardware required", "CN": "[模拟模式] 无需硬件"},
    "dlg_cancelled": {"EN": "Test cancelled by user.", "CN": "测试已被用户取消。"},
    "dlg_stop_requested": {"EN": "Stop requested — waiting for test to finish ...", "CN": "正在停止测试..."},
    "dlg_val_band": {"EN": "Band Name is required.", "CN": "频段名称为必填项。"},

    # ── Status ──
    "status_pass": {"EN": "PASS", "CN": "通过"},
    "status_fail": {"EN": "FAIL", "CN": "失败"},
    "status_config_loaded": {"EN": "Loaded config:", "CN": "已加载配置:"},
    "status_config_saved": {"EN": "Config saved:", "CN": "已保存配置:"},
    "status_report_saved": {"EN": "Report saved:", "CN": "报告已保存:"},
    "status_preparing": {"EN": "Preparing {} modules ...", "CN": "正在准备 {} 个模块..."},
    "status_starting": {"EN": "Starting {} modules in parallel ...", "CN": "并行启动 {} 个模块..."},
    "status_test_complete": {"EN": "TEST COMPLETE  |  Total: {}  PASS: {}  FAIL: {}", "CN": "测试完成  |  总数: {}  通过: {}  失败: {}"},
    "status_ports": {"EN": "Available COM ports: {}", "CN": "可用串口: {}"},
    "status_no_ports": {"EN": "Available COM ports: (none found)", "CN": "可用串口: (未找到)"},
    "status_module_at_port": {"EN": "  {}  @ {}", "CN": "  {}  @ {}"},
    "status_open_failed": {"EN": "FAILED to open {}", "CN": "打开串口失败 {}"},
    "status_config_fail": {"EN": "Failed to load config:", "CN": "加载配置失败:"},
    "status_report_fail": {"EN": "Failed to generate report:", "CN": "生成报告失败:"},
    "status_ports_fail": {"EN": "Failed to enumerate ports:", "CN": "枚举串口失败:"},

    # ── PDF Report ──
    "pdf_title": {"EN": "GNSS Module Auto Test Report", "CN": "GNSS模块自动化测试报告"},
    "pdf_batch": {"EN": "Batch", "CN": "批次"},
    "pdf_generated": {"EN": "Generated", "CN": "生成时间"},
    "pdf_tester": {"EN": "Tester", "CN": "测试员"},
    "pdf_summary_title": {"EN": "1. Overall Summary", "CN": "1. 总体概况"},
    "pdf_detail_title": {"EN": "2. Module Details", "CN": "2. 模块详情"},
    "pdf_band_title": {"EN": "Frequency Band SNR Statistics:", "CN": "频段信噪比统计:"},
    "pdf_no_band": {"EN": "No frequency-band data.", "CN": "无频段数据。"},
    "pdf_violations": {"EN": "Criteria Violations:", "CN": "标准违规项:"},

    # ── CLI ──
    "cli_title": {"EN": "GNSS Module Batch Automation Test", "CN": "GNSS模块批量自动化测试"},
    "cli_modules_to_test": {"EN": "Modules to test: {} (parallel)", "CN": "待测模块: {} (并行)"},
    "cli_generating_report": {"EN": "Generating PDF report ...", "CN": "正在生成PDF报告..."},
    "cli_report_saved": {"EN": "Report saved:", "CN": "报告已保存:"},
    "cli_test_complete": {"EN": "TEST COMPLETE", "CN": "测试完成"},
    "cli_total": {"EN": "Total", "CN": "总数"},
    "cli_pass": {"EN": "PASS", "CN": "通过"},
    "cli_fail": {"EN": "FAIL", "CN": "失败"},

    # ── Log messages ──
    "log_test_started": {"EN": "  TEST STARTED", "CN": "  测试开始"},
    "log_test_cancelled": {"EN": "Test cancelled by user.", "CN": "测试已被用户取消。"},
    "log_stop_requested": {"EN": "Stop requested — waiting for test to finish ...", "CN": "正在停止测试..."},
    "log_preparing": {"EN": "Preparing {} modules ...", "CN": "正在准备 {} 个模块..."},
    "log_starting": {"EN": "Starting {} modules in parallel ...", "CN": "并行启动 {} 个模块..."},
    "log_running": {"EN": "Running ...", "CN": "运行中..."},
    "log_report_saved": {"EN": "Report saved: {}", "CN": "报告已保存: {}"},
    "log_test_complete": {"EN": "TEST COMPLETE  |  Total: {}  PASS: {}  FAIL: {}", "CN": "测试完成  |  总数: {}  通过: {}  失败: {}"},
    "log_report_fail": {"EN": "Failed to generate report: {}", "CN": "生成报告失败: {}"},
    "log_config_loaded": {"EN": "Loaded config: {}", "CN": "已加载配置: {}"},
    "log_config_saved": {"EN": "Config saved: {}", "CN": "已保存配置: {}"},
    "log_config_fail": {"EN": "Failed to load config: {}", "CN": "加载配置失败: {}"},
    "log_ports": {"EN": "Available COM ports: {}", "CN": "可用串口: {}"},
    "log_ports_none": {"EN": "Available COM ports: (none found)", "CN": "可用串口: (未找到)"},
    "log_ports_fail": {"EN": "Failed to enumerate ports: {}", "CN": "枚举串口失败: {}"},
}

_current_lang = "CN"


def set_language(lang: str) -> None:
    global _current_lang
    _current_lang = lang


def get_language() -> str:
    return _current_lang


def t(key: str, *args) -> str:
    """Translate a key and format with optional args."""
    entry = STRINGS.get(key, {})
    text = entry.get(_current_lang, entry.get("EN", key))
    if args:
        return text.format(*args)
    return text
