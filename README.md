# 文献结果复现 agent：阶段性复现原型

面向科研学习的轻量原型：尝试把“论文中的一个明确结果”转成可检查的条件表、Python 计算、数值验证与证据记录。当前由 Codex 驱动流程，**尚未实现任意论文的自动复现，用户正努力掌握并完成部分推导的证明。**

建议导师先看本页、[阶段进展与贡献](PROGRESS.md)、[谐振子验证记录](cases/ho-fd4-section21/verification.md)。

## 分工与输入输出

| 部分 | 实际作用 |
|---|---|
| Codex | 按用户范围阅读材料、编写代码与记录、调用计算和检查工具；AI 解释仍需审核 |
| GPD（第三方） | 既有记录使用 1.2.2 的验证报告字段及格式校验；未运行完整 GPD 规划/执行系统 |
| 本项目新增 | 通用七步流程与提示词、条件/计划模板、独立案例、Python 实现、运行归档及分享证据检查 |
| 用户 | 提出目标与范围；首例还提供详细参数及验证方向；用户正努力独立完成核验|

输入为合法获得的论文、明确图/表/节号和资源限制。执行：[读材料 → 定目标 → 提条件 → 查缺失 → 计算 → 验证 → 报告](workflows/reproduce.md)。输出为代码、配置、环境、数组/图、日志、退出状态、通过与失败记录及局限。不同论文的公式和检验仍须单独构建；通用流程不是万能求解器。

## 当前案例与证据状态

| 案例 | 仅有计划 | 代码已生成 | 已运行 | 已有程序验证 | 已由用户独立核验 |
|---|---|---|---|---|---|
| [Lieu 2018 图 4：非厄米 SSH 开放链](cases/lieu2018-fig4/README.md) | 已超出 | 是 | 是 | 是，模型内部检查；原图定量一致性未达成 | 无证据，未标记通过 |
| [四阶差分法 §2.1：一维谐振子](cases/ho-fd4-section21/README.md) | 已超出 | 是 | 是 | 是，19 项数值检查和 10 项历史回读检查 | 无证据，未标记通过 |
| [001-pending 初始化占位](cases/001-pending/records/initialization.md) | 是，材料待补充 | 否 | 否 | 否 | 否 |

[推导] SSH 按图注模型求解通过内部检查，但端点与原图读数不符；没有靠调参掩盖差异。[推导] 谐振子表 1 的 40 个数值在刊载六位小数精度内一致，并有解析解、收敛和连续边值问题检查；不能推断作者未舍入数据也一致。依据分别见两案例的 extraction、plan、verification 与精选 evidence。

## 安装与运行

在仓库根目录打开 Windows PowerShell。记录环境为 Python 3.13.14；两个案例使用相同的锁定依赖。已有 `.venv` 可复用，首次安装需网络：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r cases/ho-fd4-section21/requirements-lock.txt
.\.venv\Scripts\python.exe scripts/check_shared_evidence.py
```

最后一条命令是低计算量的精选证据检查，不需要论文 PDF、GPD 或模型 API：回读哈希、SSH 代表点本征对、谐振子数组和表格。它不重新计算全图，不等于用户独立核验。加 `--write` 将本次记录存入 `records/`。实际检查结果见 [2026-11-06 发布检查](records/release-check-20261106.json)。

完整重跑前，按各案例 `source/README.md` 合法取得并放置原论文；当前入口用 PDF 哈希追溯来源，因此缺少 PDF 会报错。然后运行其中一个案例：

```powershell
.\.venv\Scripts\python.exe cases/ho-fd4-section21/src/run.py --config cases/ho-fd4-section21/config.json
.\.venv\Scripts\python.exe cases/ho-fd4-section21/src/audit_run.py
# SSH 全算较慢，非展示必需：
.\.venv\Scripts\python.exe cases/lieu2018-fig4/src/run.py --config cases/lieu2018-fig4/config.json
.\.venv\Scripts\python.exe cases/lieu2018-fig4/src/audit_run.py
```

新运行保存在案例 `outputs/<UTC时间戳>/`，成功后更新本地 `latest_run.txt`。历史实测谐振子计算/绘图约 4.80 秒、SSH 完整计算约 246 秒；机器不同耗时会变。此次发布只做低成本回读与便携性检查，不重新执行全部计算；未在干净机器安装依赖。

## 目录与分享边界

- `workflows/`、`templates/`：通用流程、提示词与条件/计划/迁移模板。
- `cases/<case-id>/`：案例说明、条件、计划、代码、配置、依赖与验证。
- `cases/<case-id>/evidence/`：精选自生成图、必要数组、数值指标及脱敏记录；`share-manifest.json` 保存分享副本和原件哈希。
- `scripts/check_shared_evidence.py`：可在新克隆目录直接运行的证据检查。
- `records/`：本次发布检查；[材料与署名](SOURCES.md)说明第三方来源与未上传内容。

论文 PDF/CAJ、全文文本、原文截图及含原图的旧汇报均保留本地，不随仓库分发。约 291 MB 的 SSH 全本征向量数组及重复旧轮不上传；本地原始证据未删除。分享副本对机器路径脱敏，原始完整归档与分享清单各有自己的哈希，不能混用。未为整个项目新增开源许可证。

## 局限与下一步

[未知] SSH 原图实际参数、作者原始数据和差异原因仍未确定。谐振子的表格转录尚缺用户独立复核；这一次不同模型的流程迁移不证明普适能力。GPD 仍是报告格式层面的使用。后续优先由用户独立复查公式和表格、验证干净环境安装，再在新授权下扩展案例；本次未开展新的科学目标。
