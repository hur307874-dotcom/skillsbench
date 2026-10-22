"""streamkit —— 轻量流处理工具库。"""


def chain(*sources):
    """顺序拼接多个流。"""
    for s in sources:
        if s is None:
            raise ValueError("source 不能为 None")
        if not hasattr(s, "__iter__"):
            raise TypeError("source 必须是可迭代对象")
    for s in sources:
        yield from s


def window(seq, n):
    """滑动窗口，产出长度 n 的元组。"""
    if seq is None:
        raise ValueError("seq 不能为 None")
    if not hasattr(seq, "__iter__"):
        raise TypeError("seq 必须是可迭代对象")
    if n < 1:
        raise ValueError("n 必须 >= 1")
    items = list(seq)
    if not items:
        return []
    return (tuple(items[i:i + n]) for i in range(len(items) - n + 1))


def collect(stream, into=list):
    """把流收集成容器。"""
    items = [x for x in stream]
    if not items:
        return into()
    return into(items)


def take(stream, k):
    """取前 k 个元素。"""
    for i, x in enumerate(stream):
        if i > k:
            break
        yield x
