# 论文复现 agent · 简单量子模型

## 生成的复现报告

点击下表可在 GitHub 直接阅读报告，查看结果图、验证依据和结论边界。

| 报告 | 内容 |
|---|---|
| **[第一阶段复现报告（建议先读）](PROGRESS.md)** | 两个案例的结果图、完成情况、验证结论、工具分工及局限 |
| **[一维谐振子完整复现报告](cases/ho-fd4-section21/report.md)** | 表 1 对照、能量和波函数误差、收敛图、边界误差及重跑结果 |
| **[普通 SSH 复现与迁移报告](cases/delplace2011-fig6/README.md)** | 图 6 能谱、解析参考、9 项检查、流程迁移和失败修正 |

这是一个面向科研学习的轻量原型。第一阶段把论文中明确的线性本征值目标转成可检查的条件表、Python 计算、数值验证与证据记录。“经典模型”指常见、成熟的物理模型，当前从简单量子模型入手。Codex 协助提取条件、编写或复用案例程序及整理证据，用户正努力掌握并完成部分推导的证明。框架尚未实现任意论文的自动复现。

学习材料见[谐振子阅读指南](cases/ho-fd4-section21/reading-guide.md)。

## 适用范围与输入输出

- **范围**：小规模线性本征问题的能级、能带或波函数，目标须能用解析解、近似解或明确极限核验。已验证的程序入口覆盖一维谐振子与指定的普通 SSH 开链。
- **输入**：合法取得的论文版本、明确的图／表／节号、可用参考材料和资源限制。公式、单位、参数和边界条件写在各案例的提取记录与配置中。
- **输出**：适用性结论、模型与方法、计算数据和图、环境与运行记录、验收结果及未知项。超出范围时说明原因，关键条件缺失时标为待补充。
- **限制**：非厄米 SSH 保留为后续扩展。本阶段暂缓混沌、实验数据复现及大型多体计算。每个新模型都需根据论文建立矩阵并选择适用检验。

[七步流程](workflows/reproduce.md)依次为读取论文 → 提取条件 → 判断适用性 → 选择方法 → 执行计算 → 验证 → 报告。

## 已有功能和验证状态

| 案例 | 程序、运行与验证 | 处理 |
|---|---|---|
| [§2.1 一维谐振子](cases/ho-fd4-section21/README.md) | [推导] 本轮复算表 1，40/40 个值在刊载六位小数上一致。19 项数值检查、10 项归档回读通过 | 主案例，复用求解代码、配置和历史证据 |
| [普通 SSH · Delplace 等图 6](cases/delplace2011-fig6/README.md) | [推导] 复算 10 胞开链能谱，9/9 项检查通过。与原解析方程求根得到的能量最大绝对差为 4.55×10⁻¹²（E/t） | 流程 2.0 的一次有上下文迁移测试 |
| [Lieu 2018 图 4](cases/lieu2018-fig4/README.md) | [推导] 历史全扫描及模型内部检查已有证据。图注模型与原图端点存在偏差，完整定量复现未达成 | 保存为历史案例，暂缓新计算 |
| [001-pending](cases/001-pending/records/initialization.md) | 初始化、条件和计划占位 | 等待材料 |

GPD 是第三方框架，提供研究计划、执行管理和验证报告工具。本机实测 GPD 1.2.2 可运行，工作区状态查询成功，已有验证报告的元数据校验通过。工作区尚无 GPD 项目状态，两例科学计算由 Python 完成。本项目新增了七步流程、模板、案例程序和证据检查。

用户提出研究目标和范围，首个历史案例中提供过详细模型参数与验证方向。用户正努力独立完成核验，自评已掌握一维谐振子和普通 SSH。程序验证见[首轮检查记录](records/stage1-check-20261114.json)和[交付验收记录](records/stage1-delivery-20261114.json)。

## 运行

在仓库根目录打开 PowerShell。有现成依赖的 `.venv` 可直接复用。交付验收环境为 Windows x86-64、CPython 3.13.14。首次安装需连接 PyPI。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r cases/ho-fd4-section21/requirements-lock.txt
```

快速检查历史谐振子与 Lieu 案例的分享证据，覆盖哈希、选定本征对及表格，无需 PDF 或 GPD。`--write` 可保存本轮检查记录。

```powershell
.\.venv\Scripts\python.exe scripts/check_shared_evidence.py
```

普通 SSH 的运行入口包含解析检查，可直接运行。

```powershell
.\.venv\Scripts\python.exe -X utf8 cases/delplace2011-fig6/run.py
```

完整重跑谐振子，先按[原文放置说明](cases/ho-fd4-section21/source/README.md)准备 PDF。入口会记录原文哈希。

```powershell
.\.venv\Scripts\python.exe cases/ho-fd4-section21/src/run.py --config cases/ho-fd4-section21/config.json
.\.venv\Scripts\python.exe cases/ho-fd4-section21/src/audit_run.py --write
```

每轮输出保存在对应案例的 `outputs/<UTC时间戳>/`，包含配置、代码、环境、命令、数据、图和退出状态。谐振子成功后更新 `latest_run.txt`。交付验收将官方 PyPI 的 14 个锁定软件包先下载，再装入空环境。在独立交付副本中重跑两例，本征数组与此前逐字节一致。[交付验收记录](records/stage1-delivery-20261114.json)

## 目录与材料

- `workflows/`、`templates/` 存放通用流程、条件提取、方案及迁移测试模板。
- `cases/<case-id>/` 存放论文专属公式、参数、程序和验证说明。`evidence/` 是既有精选分享证据，`outputs/` 是完整本地运行。
- `scripts/` 存放通用证据检查，`records/` 存放项目级检查摘要。原文、原文页图和含机器路径的完整记录留在本地，见[材料与署名](SOURCES.md)。

流程 2.0 已在普通 SSH 上完成一次有上下文迁移，冻结快照、介入情况和失败修正见 [SSH 案例](cases/delplace2011-fig6/README.md)。[迁移测试任务单](templates/transfer-test.md)可用于下一次测试。
