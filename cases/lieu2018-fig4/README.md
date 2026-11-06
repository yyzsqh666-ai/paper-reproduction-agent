# Lieu 2018 图 4：有限非厄米 SSH 开放链

状态：计划已有；代码已生成；已运行；已有程序验证；**无用户独立核验证据**。[推导] 图注模型的七类数值检查及历史 13 项归档回读通过；原图端点不一致，完整定量复现未达成。

先读 [条件与原文位置](extraction.md)、[计划及容差](plan.md)、[报告](report.md)、[验证](verification.md)。这些解释由 Codex 整理，不代表用户已独立理解或推导。

![项目计算生成的代表图](evidence/20261102T144055_167379Z/spectrum_refined.png)

## 查看与低成本检查

在项目根目录使用根 README 的依赖安装方法，再执行：

```powershell
.\.venv\Scripts\python.exe scripts/check_shared_evidence.py
```

分享快检只回读精选文件、矩阵本征对和数值表，不需要 PDF。固定运行证据在 [evidence/20261102T144055_167379Z/](evidence/20261102T144055_167379Z/)。其中 `share-manifest.json` 对分享副本校验，`original-manifest.json` 仅是本地完整归档的历史清单。

## 完整重跑（可选）

先按 [原文放置说明](source/README.md) 合法取得对应 PDF。现有计算入口会读取 PDF 哈希，故缺少文件不能直接完整运行。然后在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe cases/lieu2018-fig4/src/run.py --config cases/lieu2018-fig4/config.json
.\.venv\Scripts\python.exe cases/lieu2018-fig4/src/audit_run.py
```

`config.json` 是实际采用的配置示例，`requirements-lock.txt` 是记录依赖。每轮新建 `outputs/<UTC时间戳>/`；成功才更新本地 `latest_run.txt`。首次克隆没有该指针，必须先完整运行才能使用案例 `audit_run.py`；展示应使用上面的精选快检。原始科学求解入口此次未修改。

## 分享限制

原文 PDF、全文文本、页面截图与包含原图的旧汇报不上传；本地原件不删除。机器路径在分享副本中脱敏，历史命令中的 `<PROJECT_ROOT>` 等是标记，不能直接粘贴执行。重跑后源码、说明或输入哈希与旧轮不同并不自动意味着物理结果改变，应检查差异。独立核验与科研结论边界见 [项目进展](../../PROGRESS.md)。

SSH 完整扫描历史约 246 秒；全 `spectrum.npz` 约 291 MB，只留本地。分享 801 点谱、六个代表点本征对、尺寸/阈值/相位数据及模型自生成图。此入口只支持 u=0；改模型或阈值必须另行记录，不能用来拟合原图。`read_figure_endpoints.py` 需要本地原文页图；`build_briefing.py` 需要本地完整输出、原图及 ReportLab 等额外文档依赖，不属于快检入口。
