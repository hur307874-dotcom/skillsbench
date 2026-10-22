# 任务样例（三种形态各一）

- `d1-median-01/`：合成内置题（pool-v2 系）——小而快的管道验证题
- `conv-streamkit-empty/`：虚构约定题（pool-v3 系）——知识缺口测量仪器，反直觉约定（BLANK/BROKEN 哨兵）
- `mined2-exactly_n-1080/`：真实 issue 题（mined-v2 系）——more_itertools #1080 真实回归，带内稳态 0.67

全量题库（467MB，36k 文件）未入库：合成池由 `backend/task_forge` 生成，真实题由 `scripts/mined_b1_filter.py` 过滤挖掘产物。
