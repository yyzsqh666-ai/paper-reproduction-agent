# 2026-11-22 复现流程验收

**项目部分通过。** SSH 图 6 和 Kronig–Penney 图 3 各从空输出目录重跑两次，每例四个确定性产物的 SHA256 均一致。最终验收程序退出 0，29 项结果符合预期，包含故障用例的预期非零退出。案例范围为有解析或独立数值参考的小规模线性模型。[结果表](acceptance/results.json)

| 能力 | 判定 | 证据与覆盖 |
|---|---|---|
| 已有案例重跑 | 通过 | [SSH A](acceptance/delplace2011-fig6/A/product-index.json)、[SSH B](acceptance/delplace2011-fig6/B/product-index.json)、[Kronig A](acceptance/kronig-penney1931-fig3/A/product-index.json)、[Kronig B](acceptance/kronig-penney1931-fig3/B/product-index.json)。Kronig 两轮检查文件差异仅为[耗时和峰值内存](kronig-checks-diff.json)。 |
| 失败行为 | 通过 | 缺 PDF、PDF 哈希不符、缺配置、无效 JSON、缺字段、缺基线、依赖不符均在计算前退出 1。另测了输出冲突保护及计算中异常。[回归结果](acceptance/results.json) |
| 实际命令和编码 | 通过 | 启动器及直接子进程分别记录可执行文件、逐项参数、工作目录、起止、退出码和日志位置。确认 SSH 的 `-X utf8`，Kronig 的 Windows PowerShell 5.1 和 pwsh 7.6.9；新证据通过无 BOM UTF-8 检查。以下记录已替换私人路径。[SSH](acceptance/delplace2011-fig6/A/case-launcher.json) · [PS 5.1](acceptance/kronig-penney1931-fig3/A/case-launcher.json) · [pwsh](acceptance/kronig-penney1931-fig3/shell-smoke/case-launcher.json) |
| 独立物理核验 | 通过 | [推导] SSH 核对 r=0、r=1、801 点迹恒等式及 r=0.5 的全部 20 个按序能级，非端点最大差 8.88×10⁻¹⁶。Kronig 把式 (6) 的 60 位求根与实空间 Bloch 有限元分别核验。后者在 P=2π、6π 比较十二个带边，最大误差 0.001017，低于 0.002。[SSH](acceptance/delplace2011-fig6/A/independent-ssh.json) · [式 (6)](acceptance/kronig-penney1931-fig3/A/eq6.json) · [有限元](acceptance/kronig-penney1931-fig3/A/bloch-fem.json) |
| 新论文盲测 | 通过 | [原文] Vankov 图 1，arXiv:0906.5138v1，PDF 第 2 页。[推导] 独立新会话按冻结的七步流程从论文和目标图开始，先记录方案，再交付曲线。评估端五个预先封存的 mpmath 对照值最大误差 2.22×10⁻¹⁶，阈值 0.001。测试覆盖聊天与任务材料隔离，操作系统级隔离和训练期接触情况未测。[案例](../../cases/vankov2009-fig1/report.md) · [评分](blind-score.json) |
| 刊印图定量 | 部分通过 | [推导] SSH 刊印版 PDF 第 4 页，最高谱支在 r=0.5、1、1.5 的最大残差 0.00208，400 dpi 像素读图不确定度 ±0.01370 E/t。Kronig 图和 SSH 其余谱支未纳入本次轴标定。[读图值](figure6-points.json) |
| 环境 | 部分通过 | Windows x64、SSH CPython 3.13.14、Kronig Anaconda 3.14.6，PowerShell 5.1 完整运行，pwsh 7.6.9 smoke。复用已安装的软件环境，未测环境重装、其他系统和 pwsh 完整扫描。 |
| Roy 表 II | 未测 | 本轮重跑目标为 SSH 和 Kronig。Roy 历史计算与 Morse 解析谱相符，三个刊载能级均未达到表 II 的八位小数精度。[历史报告](../../cases/roy2013-h2-table2/report.md) |

## 基线与可复核结果

修复前的隔离测试中，SSH 和 Kronig 在缺论文 PDF 时仍退出 0。SSH 的状态漏记了 `-X utf8`，Kronig 在 Windows PowerShell 5.1 中运行却将 launcher 写成 `pwsh`，旧状态 JSON 带 BOM。修复后两例均在科学计算前预检材料、配置、冻结基线和依赖；正式启动器分配独立输出目录。SSH 从项目入口进入 Python worker，Kronig 从各自 PowerShell 宿主直接启动 Python。祖先进程参数不可观测时记为 null。

[原文] Delplace 等人的图 6 用十个原胞，刊印 PDF 第 4 页／195452-4，开放边界见 §II.B.1，PDF 第 3 页。[推导] r=1 时的 20 格点均匀链最低能量为 2cos(20π/21) ≈ −1.977661652450257。新数据表 r=1 的第一个能量值为 −1.9776616524502568。r=0 得九个二聚体和两个零能格点。全网格迹恒等式为 tr(H²/t²)=2(10r²+9)。非端点检查比较排序谱，能级身份跟踪需要波函数配对，本轮未测。[实际谱 CSV](acceptance/delplace2011-fig6/A/case-spectrum.csv)

[原文] Kronig–Penney 式 (6) 见 PDF 第 4 页／502，图 3 见第 5 页／503。[推导] 在 P=2π 和 6π，式 (6) 的同公式高精度求根最大差 5.083×10⁻¹⁶。实空间核验在单位晶胞使用周期及反周期边界，在节点零的刚度加入 2P，以 128、256 个节点离散；取每个相位三个最低值，合并排序并除以 π²。误差随加密约降至四分之一，符合二阶本征值收敛预期。

复跑方法和依赖见[根 README](../../README.md)。发布目录收录精选数值、退出状态和去标识的命令，原始源码快照、论文材料、完整日志及机器路径留在本地。产物索引里的 SHA256 是当时完整运行产生的哈希；发布文件按[分享清单](share-manifest.json)回读。


发布副本使用相对 PDF 路径重新运行同一套验收，29/29 条满足预期。[发布副本复测](publish-check.json)
