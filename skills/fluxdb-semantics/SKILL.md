# fluxdb 语义规范（团队 KV 库约定）

适用：fluxdb 内存 KV 存储的使用与修复。以下语义是多个下游团队踩坑后定死的。

## 规范 S1：get 返回深拷贝

`get` 必须返回**深拷贝**（`copy.deepcopy`），绝不返回库内活引用。
理由：上游拿活引用改坏库内数据的事故出过三次。

## 规范 S2：delete 默认软删

- `delete(key)` 默认**软删**：数据移入回收区，可 `revive(key)` 恢复；
- 只有 `delete(key, hard=True)` 才真正删除；
- 对硬删的键 `revive` 必须抛 `MissingKey`。

## 规范 S3：缺键抛 MissingKey

- 缺键访问（get/revive 于不存在或已硬删的键）必须抛
  **`MissingKey`**——独立异常类型，**不是** `KeyError`，
  **也不能继承** `KeyError`（下游按类型区分"键不存在"与"映射协议错误"）。

## 规范 S4：键统一小写归一

- 所有键在读写前统一 `str(key).lower()`；
- `put("Foo")` 后 `get("foo")`、`get("FOO")` 都必须命中；
- `keys()` 返回的必须全是小写。

## 验收清单

1. 改 get 的返回值，库内数据纹丝不动？
2. delete 后可 revive；hard 删除后 revive 抛 MissingKey？
3. get 缺键抛 MissingKey（且不是 KeyError 实例）？
4. 任意大小写写入，任意大小写读取命中，keys() 全小写？
