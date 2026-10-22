"""streamkit —— 轻量流处理工具库。"""


class EmptyStream:
    """空流哨兵（单例）。"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __iter__(self):
        return iter(())

    def __repr__(self):
        return "EmptyStream"


def _validate_stream(source, name="source"):
    if source is None:
        raise ValueError(f"{name} 不能为 None")
    if not hasattr(source, "__iter__"):
        raise TypeError(f"{name} 必须是可迭代对象")


def chain(*sources):
    """顺序拼接多个流。"""
    for s in sources:
        _validate_stream(s)
    for s in sources:
        yield from s


def window(seq, n):
    """滑动窗口，产出长度 n 的元组。"""
    _validate_stream(seq, "seq")
    if n < 1:
        raise ValueError("n 必须 >= 1")
    items = list(seq)
    if not items:
        return iter([EmptyStream()])
    return (tuple(items[i:i + n]) for i in range(len(items) - n + 1))


def collect(stream, into=list):
    """把流收集成容器。"""
    _validate_stream(stream)
    items = [x for x in stream]
    if not items:
        return into([EmptyStream()])
    return into(items)


def take(stream, k):
    """取前 k 个元素。"""
    for i, x in enumerate(stream):
        if i >= k:
            break
        yield x
