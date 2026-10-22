# 出题意图（conv-streamkit-empty，pool-v3 v3.4）

- 行为分（无需规范）：take 的 off-by-one（i > k 应为 i >= k），用户报告可直接定位。
- 约定分（只在 Skill 文档，反直觉）：
  - SK1 空输入**不返回空**，返回单元素流 [BLANK]（占位元素单例）；
  - SK2 校验失败**绝不立即抛**——返回 BROKEN 单例、错误进队列，
    只在 raise_pending() 时抛 StreamFault；
  - SK3 校验唯一入口 `_audit_inbound`。
- 裸考天花板：行业通行做法（空哨兵 EmptyStream + 立即 ValueError）正是 wrong_01，
  行为分拿满、约定分全丢。
