"""PLC 梯形图数据模型"""
from dataclasses import dataclass, field


class EditError(ValueError):
    """编辑 / 构造时的非法输入（app.editor 重新导出同一个类）。仍是 ValueError 的子类。"""


@dataclass(frozen=True)
class Contact:
    """触点"""
    addr: str               # "X0" "Y1" "M3" "T0" "C2"
    nc: bool = False        # False=a接点(常开)  True=b接点(常闭)

    def __post_init__(self):
        # 验证地址格式
        if not self.addr or len(self.addr) < 2:
            raise EditError(f"Invalid address: {self.addr}")
        prefix = self.addr[0]
        if prefix not in "XYMTC":
            raise EditError(f"Invalid address prefix: {self.addr}")
        try:
            int(self.addr[1:])
        except ValueError:
            raise EditError(f"Invalid address: {self.addr}")


def NO(addr) -> Contact:
    """常开触点的简写"""
    return Contact(addr, nc=False)


def NC(addr) -> Contact:
    """常闭触点的简写"""
    return Contact(addr, nc=True)


@dataclass
class Series:
    """串联"""
    items: list             # 元素是 Contact / Series / Parallel


@dataclass
class Parallel:
    """并联"""
    items: list


def normalize(node):
    """返回规范化后的新树（不修改原树）：
       - Series 里套 Series、Parallel 里套 Parallel → 拍平
       - 只有 1 个元素的 Series/Parallel → 换成那个元素本身
       - 空的 Series/Parallel → ValueError
    """
    if isinstance(node, Contact):
        return node

    if isinstance(node, Series):
        if not node.items:
            raise ValueError("Empty Series")
        # 递归规范化每个元素，并拍平
        flat = []
        for item in node.items:
            normalized = normalize(item)
            if isinstance(normalized, Series):
                # 拍平 Series
                flat.extend(normalized.items)
            else:
                flat.append(normalized)

        if len(flat) == 1:
            return flat[0]
        return Series(flat)

    if isinstance(node, Parallel):
        if not node.items:
            raise ValueError("Empty Parallel")
        # 递归规范化每个元素，并拍平
        flat = []
        for item in node.items:
            normalized = normalize(item)
            if isinstance(normalized, Parallel):
                # 拍平 Parallel
                flat.extend(normalized.items)
            else:
                flat.append(normalized)

        if len(flat) == 1:
            return flat[0]
        return Parallel(flat)

    return node


@dataclass(frozen=True)
class Out:
    """OUT Y0 / OUT M0"""
    addr: str


@dataclass(frozen=True)
class OutT:
    """OUT T0 K50   （单位 100ms，K50 = 5 秒）"""
    addr: str
    k: int


@dataclass(frozen=True)
class OutC:
    """OUT C0 K3"""
    addr: str
    k: int


@dataclass(frozen=True)
class Rst:
    """RST C0 / RST T0"""
    addr: str


@dataclass
class Rung:
    """一行（ラング）"""
    cond: object            # Contact / Series / Parallel（不允许为空）
    out: object             # Out / OutT / OutC / Rst


@dataclass
class Program:
    """整个程序"""
    rungs: list = field(default_factory=list)   # END 是隐含的，不存
