# 来源、版权与分享范围

未为本项目新增整体开源许可证。仓库私有不等于取得第三方材料再分发许可。

## 第三方框架

GPD / Get Physics Done：本机安装包 `get-physics-done 1.2.2` 的 METADATA 指向 [psi-oss/get-physics-done](https://github.com/psi-oss/get-physics-done)，作者为 Physical Superintelligence PBC，所列许可证为 Apache License 2.0。这里依据的是本地版本元数据，不保证上游当前版本相同。本仓库不是 GPD fork，不包含该框架源码；项目中的 `GPD/` 只有状态锁文件，未上传。本项目复用验证报告字段和格式校验，相关归属保留，不把 GPD 写成原创成果。

NumPy、SciPy、Matplotlib 等通过案例 requirements-lock.txt 安装；不随仓库打包虚拟环境及第三方库，第三方许可由各包保留。

## 论文材料

| 来源 [原文] | 可核对位置与链接 | 本地文件 |
|---|---|---|
| Simon Lieu, *Topological phases in the non-Hermitian Su-Schrieffer-Heeger model*, Physical Review B 97, 045106 (2018) | arXiv v2 PDF 页序 1 式(1)(2)，页序/印刷页 4 图4；[arXiv:1709.03788v2](https://arxiv.org/abs/1709.03788v2)，[DOI:10.1103/PhysRevB.97.045106](https://doi.org/10.1103/PhysRevB.97.045106) | `cases/lieu2018-fig4/source/1709.03788v2.pdf` |
| 刘展源、关成波、吕英波、张鹏、丛伟艳，《四阶精度差分法解定态薛定谔方程》，大学物理 40(9), 58–62 (2021) | PDF 页序 1 标题；页序 2–3 / 印刷 59–60，§2.1 式(13)–(20)、表1；[DOI:10.16854/j.cnki.1000-0712.210063](https://doi.org/10.16854/j.cnki.1000-0712.210063) | `cases/ho-fd4-section21/source/paper.pdf` |

以上书目信息依据既有本地提取及原文首页。此次在线来源链接抓取未成功；[未知] 未取得覆盖这些材料的再分发授权。因此不上传论文、提取全文、原文页面、裁剪图，也不上传包含原图的 briefing.pdf、comparison.png 等旧汇报。请通过上述正规来源自行合法取得，具体放置和哈希见案例 `source/README.md`。

`source/table1.csv` 仅含为数值比较所需的 40 个刊载数据及索引，已在来源文件注明表号与位置；不复制版式、正文或完整表格图。`endpoint_readings.json` 是本项目从图像取得的有限读数及测量方法，非作者原始数据。其余发布图像均由项目计算生成，不能标注为论文原图。

## 原始证据与分享副本

原始 `outputs/` 和带私人会话标识/机器路径的记录全部本地保留。`evidence/` 是精选副本：脱敏本机路径、去掉超大和重复数组、保留成功和必要失败证据。`share-manifest.json` 对分享字节做 SHA256，并另外记录原件哈希和是否转换；`original-manifest.json` 仅描述当时完整本地归档，不能用来要求分享副本逐字节相同。

完整记录中的绝对工作目录和命令留在本地，分享副本以 `<PROJECT_ROOT>`、`<USER_HOME>`、`<LOCAL_PAPER>` 替代机器路径；它们是明确的脱敏标记，不是可以直接执行的命令。可运行命令见根 README。历史源码快照只用于追溯，应从各案例 `src/run.py` 启动重跑。
