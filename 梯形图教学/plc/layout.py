"""梯形图网格坐标计算"""
from dataclasses import dataclass
from plc.model import Contact, Series, Parallel, normalize


@dataclass
class Layout:
    """网格布局"""
    width: int                       # 列数
    height: int                      # 行数（这一个 ラング 占几行）
    cells: list                      # [(Contact, col, row), ...] 按从左到右、从上到下深度优先顺序


def layout(cond) -> Layout:
    """计算梯形图网格坐标"""
    # 先规范化
    cond = normalize(cond)

    cells = []

    def walk(node, col_offset=0, row_offset=0):
        """
        返回 (width, height, cells)
        cells 是 [(Contact, col, row), ...]
        """
        if isinstance(node, Contact):
            # 触点：1×1
            cells.append((node, col_offset, row_offset))
            return (1, 1)

        elif isinstance(node, Series):
            # 串联：子块横着排
            total_width = 0
            max_height = 0

            for item in node.items:
                w, h = walk(item, col_offset + total_width, row_offset)
                total_width += w
                max_height = max(max_height, h)

            return (total_width, max_height)

        elif isinstance(node, Parallel):
            # 并联：子块竖着叠
            max_width = 0
            total_height = 0

            for item in node.items:
                w, h = walk(item, col_offset, row_offset + total_height)
                max_width = max(max_width, w)
                total_height += h

            return (max_width, total_height)

        return (0, 0)

    w, h = walk(cond)

    return Layout(width=w, height=h, cells=cells)
