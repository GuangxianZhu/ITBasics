"""梯形图 → 指令表 (IL)"""
from plc.model import Contact, Series, Parallel, Out, OutT, OutC, Rst, normalize


def _il_cond(cond, is_first=True):
    """生成条件部分的指令，返回指令列表"""
    # 先规范化
    cond = normalize(cond)

    if isinstance(cond, Contact):
        # 单个触点
        if cond.nc:
            return ["LDI " + cond.addr]
        else:
            return ["LD " + cond.addr]

    elif isinstance(cond, Series):
        # 串联
        result = []
        for i, item in enumerate(cond.items):
            if i == 0:
                # 第一个元素
                if isinstance(item, Parallel):
                    # Series 的第一个是 Parallel：直接展开
                    result.extend(_il_cond(item, is_first=True))
                else:
                    # Contact 或 Series
                    result.extend(_il_cond(item, is_first=True))
            else:
                # 后续元素
                if isinstance(item, Parallel):
                    # 生成该 Parallel，然后 ANB
                    result.extend(_il_cond(item, is_first=True))
                    result.append("ANB")
                elif isinstance(item, Series):
                    # 这不应该出现（因为规范化了）
                    result.extend(_il_cond(item, is_first=False))
                else:
                    # Contact
                    if item.nc:
                        result.append("ANI " + item.addr)
                    else:
                        result.append("AND " + item.addr)

        return result

    elif isinstance(cond, Parallel):
        # 并联
        result = []
        for i, item in enumerate(cond.items):
            if i == 0:
                # 第一个分支
                if isinstance(item, Series):
                    # Parallel 的第一个是 Series：直接展开
                    result.extend(_il_cond(item, is_first=True))
                else:
                    # Contact 或 Parallel
                    result.extend(_il_cond(item, is_first=True))
            else:
                # 后续分支
                if isinstance(item, Series):
                    # 生成该 Series，然后 ORB
                    result.extend(_il_cond(item, is_first=True))
                    result.append("ORB")
                elif isinstance(item, Parallel):
                    # 这不应该出现（因为规范化了）
                    result.extend(_il_cond(item, is_first=False))
                else:
                    # Contact
                    if item.nc:
                        result.append("ORI " + item.addr)
                    else:
                        result.append("OR " + item.addr)

        return result

    return []


def to_il(program) -> list[str]:
    """将程序转换为指令表"""
    result = []

    for rung in program.rungs:
        # 生成条件部分
        result.extend(_il_cond(rung.cond))

        # 生成输出部分
        if isinstance(rung.out, Out):
            result.append("OUT " + rung.out.addr)
        elif isinstance(rung.out, OutT):
            result.append(f"OUT {rung.out.addr} K{rung.out.k}")
        elif isinstance(rung.out, OutC):
            result.append(f"OUT {rung.out.addr} K{rung.out.k}")
        elif isinstance(rung.out, Rst):
            result.append("RST " + rung.out.addr)

    # 最后添加 END
    result.append("END")

    return result


def to_il_rungs(program) -> list[list[str]]:
    """按行分组、不含 END"""
    result = []

    for rung in program.rungs:
        line = []

        # 生成条件部分
        line.extend(_il_cond(rung.cond))

        # 生成输出部分
        if isinstance(rung.out, Out):
            line.append("OUT " + rung.out.addr)
        elif isinstance(rung.out, OutT):
            line.append(f"OUT {rung.out.addr} K{rung.out.k}")
        elif isinstance(rung.out, OutC):
            line.append(f"OUT {rung.out.addr} K{rung.out.k}")
        elif isinstance(rung.out, Rst):
            line.append("RST " + rung.out.addr)

        result.append(line)

    return result
