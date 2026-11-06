# 自动数值验证记录

这些通过项只验证所实现的图注模型，不能证明原图一致。

| 检查 | 通过 |
| --- | --- |
| small_chain | True |
| residual | True |
| chiral | True |
| pairing | True |
| dimer_limits | True |
| hermitian | True |
| repeated_points | True |

实际数值、预设容差、环境分别见 checks.json、config.json、environment.json。
阈值敏感性与有限尺寸效应见 threshold_scan.csv、finite_size.csv；它们不被包装为求解器通过项。