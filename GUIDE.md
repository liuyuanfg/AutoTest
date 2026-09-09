# GNSS 模块批量自动化测试工具 (GNSS Module Batch Auto Test Tool)

批量串口测试工具，用于 GNSS 模块。可同时打开多个 COM 口，解析 NMEA-0183 GGA/GSV/RMC 语句，提取定位卫星数量和各频段信噪比(SNR)，并生成 PDF 测试报告。支持中英文界面切换。

Batch serial-port testing tool for GNSS modules. Opens multiple COM ports simultaneously, parses NMEA-0183 GGA/GSV/RMC sentences, extracts positioning and SNR statistics, and generates PDF test reports. Chinese/English UI switching supported.

## 项目结构 (Project Structure)

```
autotest/
├── main.py                  # CLI 入口 + 测试编排 (CLI entry + orchestrator)
├── gui.py                   # Tkinter 图形界面 (GUI)
├── serial_manager.py        # 串口连接管理器 (serial port manager)
├── nmea_parser.py           # NMEA-0183 GGA/GSV/RMC 语句解析器
├── boot_parser.py           # TC1720 上电打印信息解析器
├── statistics_calculator.py # 信噪比统计 + 定位质量计算
├── criteria.py              # 可配置的判定标准 (pass/fail)
├── report_generator.py      # PDF 报告生成 (ReportLab)
├── i18n.py                  # 中英文切换 (i18n)
├── app_paths.py             # PyInstaller 兼容的路径解析
├── config.yaml              # 默认测试配置
├── requirements.txt         # Python 依赖
├── install_deps.bat         # 离线依赖安装器
├── wheels/                  # 预下载的 .whl 包
├── run_test.bat             # Windows 启动器 (CLI/GUI)
├── run_gui.bat              # Windows GUI 启动器 (无控制台窗口)
├── gui.spec                 # PyInstaller 打包配置
└── GUIDE.md                 # 本说明文档
```

## 依赖 (Dependencies)

```
pyserial>=3.5
reportlab>=4.0
pyyaml>=6.0
```

**在线安装:** `pip install -r requirements.txt`

**离线安装:** `install_deps.bat` — 从随附的 `wheels/` 目录安装，无需联网。

`wheels/` 目录包含 CPython 3.10 (Windows x64) 的预下载 `.whl` 包。其他 Python 版本需重新下载：

```bash
pip download -d wheels pyserial reportlab pyyaml --only-binary=:all:
```

## 快速开始 (Quick Start)

### 启动 GUI
```bash
python gui.py
# 或双击 run_gui.bat
```

### CLI 模式
```bash
# 模拟测试 (无需硬件)
python main.py -c config.yaml -s

# 真实串口测试
python main.py -c config.yaml

# 列出可用串口
python main.py --list-ports
```

## 配置 (config.yaml)

### 测试工位 (Modules)
```yaml
modules:
  - id: "K601-TEST1"
    port: "COM9"
    description: "Test Station 1"
    baudrate: 115200   # 可选，缺省使用串口默认值
  - id: "K601-TEST2"
    port: "COM10"
```

### 串口默认参数 (Serial Defaults)
```yaml
serial:
  baudrate: 115200
  bytesize: 8
  parity: N
  stopbits: 1
  timeout: 1.0
```

### 测试参数 (Test Parameters)
```yaml
test:
  wait_poweron_timeout: 60   # 等待首个 NMEA 数据的超时时间(秒)
  sample_count: 45           # 采集的完整周期数
  sample_duration: 0         # 或按秒时长 (0=使用 sample_count)
  collect_mode: "count"      # "count" 或 "duration"
  send_xtsfwload: true       # 是否发送 $XTSFWLOAD 重启模块获取启动信息
  boot_wait_timeout: 30      # 等待启动信息的超时时间(秒)
```

### 输出 (Output)
```yaml
output:
  report_dir: "./reports"
  report_prefix: "K601_Test_Report"
```

### 测试信息 (Meta)
```yaml
meta:
  batch_no: "批次-2026-001"    # 批次号，显示在报告标题中
  tester: "张三"               # 测试员，显示在报告内容中
```

### 判定标准 (Criteria, 0 = 禁用)
```yaml
criteria:
  min_fix_quality: 1             # 1=GPS, 2=DGPS, 4=RTK固定, 5=RTK浮点
  min_positioned_satellites: 4
  max_hdop: 2.0
  min_max_snr: 35.0              # 所有频段最高最大SNR
  min_avg_snr: 0.0
  per_band:
    GPS L1:
      min_tracked: 4
      min_avg_snr: 30.0
      min_max_snr: 40.0
    GLO G1:
      min_tracked: 3
      min_avg_snr: 30.0
      min_max_snr: 35.0
```

## 启动信息解析 (Boot Message Parsing)

工具从上电打印信息中自动提取模块身份信息：

| 语句格式 | 提取结果 |
|---|---|
| `$TC1720 ROM 83 FW $TC1720_v4_0.275$` | ROM=`83`, FW=`TC1720_v4_0.275` |
| `$ChipID,37` | 芯片ID=`37` |
| `$SN,711000000134` | 序列号=`711000000134` |
| `bootloader V5.0.0` | 引导程序=`5.0.0` |
| `$XTSMONVER,<FW>,<ChipID>,<SN>` | FW 和 SN (回退来源，ChipID 忽略) |
| `$XTSCMDOk` | 配置命令确认 |

若无上电打印信息(模块已上电)，发送 `$XTSMONVER` 查询 FW/SN 作为回退。发送 `$XTSFWLOAD` 可重启模块并等待启动信息。

## 测试流程 (Test Flow)

1. **并行打开所有 COM 口**
2. **发送 `$XTSMONVER`** (3 次重试，1s 间隔) — 提取 FW/SN
3. **发送 `$XTSCFGPRT,1,,H40000007,`** — 使能 COM2 AGNSS 数据输出
4. **发送 `$XTSFWLOAD`** — 重启模块并等待启动信息 (可配置)
5. **等待 NMEA 数据** — GGA/GSV 语句表示模块开始输出
6. **采集 N 个周期** — 通过 RMC→GGA→GSV 语句序列计数
7. **计算统计** — 卫星数、各频段平均/最大 SNR
8. **评估判定标准** — 通过/失败及违规信息
9. **生成 PDF 报告**

## NMEA 解析细节

### 周期检测 (Cycle Detection)
周期由 RMC→GGA→完整 GSV 组序列定义。只有完整周期被计数(缺失 GSV 语句不会虚增计数)。

### 定位质量优先级 (Fix Quality Priority)
多个采样点出现不同定位质量时，优先级为：**4 > 5 > 3 > 2 > 1 > 0** (RTK固定优先于RTK浮点)。

### 卫星跟踪 (Satellite Tracking)
- 按 PRN 去重，保留最佳 SNR
- 汇总计数仅统计每个星座的**第一个信号ID**
- SNR 统计表显示**所有频段**的真实跟踪数

### HDOP
- 仅当 **定位质量 > 0** 且值在 **0.05–50** 范围时有效
- 判定标准使用**最后一个**有效 HDOP 值

## GUI 功能

| 标签页/面板 | 说明 |
|---|---|
| **测试工位** | 管理工位列表(增删改) — ID、端口(下拉)、波特率(下拉)、描述 |
| **参数设置** | 串口默认参数、测试参数、输出设置、测试信息(批次号/测试员) |
| **判定标准** | 全局阈值 + 各频段可编辑表格 |
| **运行日志** | 每工位独立日志标签页 + 共享日志页 |
| **结果窗口** | 可排序表格：SN、工位、端口、结果、固件、引导程序、定位质量、卫星数、HDOP、错误 |

### 控件
- **开始/停止** — 开始或取消并行测试
- **模拟模式** — 使用合成 NMEA 数据干跑(无需硬件)
- **刷新串口** — 扫描可用 COM 口
- **结果** — 测试后显示结果表格
- **每工位进度条** — 实时显示各工位的采集进度 (cur/total)

### 语言切换 (Language)
菜单栏 **帮助 → 语言 → English / 中文** 即时切换界面语言。默认中文。

## PDF 报告

报告使用**横向 A4** 纸张，嵌入微软雅黑字体支持简体中文。

1. **总体概况** — 表格：SN、工位、端口、结果、固件版本、定位质量、卫星数、跟踪数、HDOP
2. **模块详情** — 每个模块一页：
   - 启动信息 (FW、ROM、引导程序、SN、芯片ID)
   - 关键指标 (定位质量、卫星数、HDOP last/avg、海拔)
   - 判定标准违规项 (红色)
   - 各频段信噪比统计表

报告标题显示批次号，元信息行显示测试员和批次号。

## 并行测试 (Parallel Testing)

所有模块通过 `ThreadPoolExecutor` **并发**测试。每个模块拥有独立的串口连接、后台读取线程和统计采集。结果随模块完成逐个显示。

## 调试日志 (Debug Logging)

使用真实硬件时，每个串口接收到的每一行数据都会保存到 `debug/<工位ID>_<端口>_<时间戳>.log` 以便排查问题。

## 打包 (Packaging / PyInstaller)

```bash
pip install pyinstaller
pyinstaller --noconfirm --clean gui.spec
```

产物在 `dist/GNSS_AutoTest.exe`。`app_paths.py` 确保 exe 相对于自身位置查找 `config.yaml` 和输出目录。

注意：`gui.spec` 已排除 torch、tensorflow、scipy、pandas、matplotlib 等无关重型包以加速构建并减小体积。

## 常见问题 (Common Issues)

| 问题 | 解决方案 |
|---|---|
| 端口打开失败 | 检查 COM 口编号，确认无其他程序占用 |
| 无 NMEA 数据 | 检查波特率，确认模块已上电并输出 |
| XTSMONVER 无响应 | 非致命 — 如有启动信息则使用启动信息 |
| GSV 数据缺失 | 采集结束时会刷新未完成的组 |
| 判定标准违规异常 | 检查 per_band 项是否与模块输出的星座匹配 |
| 结果窗口为空 | 确认测试完成后再打开结果 |
| 文字显示模糊 | 已启用 DPI 感知，若仍模糊请检查系统缩放设置 |
| 构建缓慢 | 已通过 excludes 排除无关重型包 |
