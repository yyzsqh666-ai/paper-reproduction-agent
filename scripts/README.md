# 分享证据检查

`check_shared_evidence.py`：从仓库根目录用项目 Python 执行，默认只读；`--write` 写入新的 UTC 时间戳记录。依赖 NumPy、SciPy、threadpoolctl，版本见案例 requirements-lock.txt。失败返回非零退出码，文件缺失会直接报错，不静默通过。

读取两个案例的 share-manifest、源码/配置及精选数组，验证 SHA256、保存本征对方程残差、谐振子正交性和40个刊载值。它没有重算完整论文结果，不包含作者原始数据，不代表用户独立核验。物理求解仍在各案例 src/ 内。
