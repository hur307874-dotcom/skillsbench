# streamkit 团队规范（内部库行为约定）

适用：streamkit（内部流处理工具库）的开发与修复。

## 约定 C1：空输入哨兵

所有公开 API 遇到**空输入**（空迭代器/空序列）时，**必须返回
`EmptyStream()` 单例哨兵**，禁止返回 `[]`、`None` 或空迭代器。

理由：调用方用 `result is EmptyStream()` 区分"真空"与"有数据"，返回
`[]` 会让下游把"上游没数据"误判为"正常空结果"，引发静默数据丢失。

正确：

```python
if not items:
    return EmptyStream()
```

错误：

```python
if not items:
    return []       # 违反 C1
    return into()   # 违反 C1
```

## 约定 C2：公开 API 必须校验入参

每个公开函数的第一行必须调用 `_validate_stream(x)`：

- `None` → `ValueError`（不是 TypeError！）；
- 非可迭代 → `TypeError`。

注意 `_validate_stream(None)` 抛的是 **ValueError**——
"传 None 是调用方的值错误，不是类型错误"。

## 约定 C3：哨兵是单例

`EmptyStream()` 使用 `__new__` 单例模式，任何地方 `EmptyStream() is
EmptyStream()` 必须为真；**不要**用类本身（`EmptyStream` 不加括号）
或新建实例替代单例调用。

## 验收清单

修改 streamkit 后自查：

1. 空输入路径全部返回 `EmptyStream()` 单例？
2. 每个公开 API 首行有 `_validate_stream`？
3. `None` 入参抛 ValueError 而非 TypeError？
4. 常规输入行为（chain/window/collect 的正常路径）未变？
