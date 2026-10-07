"""梯形图编辑操作 + 撤销/重做（纯逻辑，不依赖 panda3d）。

所有操作原地修改 program；出错抛 EditError 且 program 保持原样
（先在条件树的副本上改，全部成功后才写回）。
"""
import copy
import re

from plc.model import (EditError, Contact, Series, Parallel, Out, OutT, OutC, Rst, Rung, Program,
                       normalize)


_ADDR = re.compile(r"[A-Z][0-9]+")


def _check_addr(addr, prefixes, what="地址"):
    if not isinstance(addr, str) or not _ADDR.fullmatch(addr) or addr[0] not in prefixes:
        raise EditError(f"{what}不合法：{addr}（{'/'.join(prefixes)}+数字）")


def _check_contact(c):
    if not isinstance(c, Contact):
        raise EditError("不是触点")
    _check_addr(c.addr, "XYMTC")
    return c


def _rung(program, r):
    if not isinstance(r, int) or not 0 <= r < len(program.rungs):
        raise EditError(f"行号越界：{r}")
    return program.rungs[r]


def _locate(cond, k):
    """返回 (路径[(容器, 下标)...], 叶子)；k 是 DFS 顺序的触点下标（与 layout / draw 一致）"""
    if not isinstance(k, int) or k < 0:
        raise EditError(f"触点下标越界：{k}")
    counter = [0]
    found = []

    def walk(node, path):
        if found:
            return
        if isinstance(node, Contact):
            if counter[0] == k:
                found.append((list(path), node))
            counter[0] += 1
            return
        for i, it in enumerate(node.items):
            walk(it, path + [(node, i)])

    walk(cond, [])
    if not found:
        raise EditError(f"触点下标越界：{k}")
    return found[0]


def _work(program, r):
    rung = _rung(program, r)
    return rung, copy.deepcopy(normalize(rung.cond))


def _replace_leaf(cond, path, new):
    if not path:
        return new
    parent, idx = path[-1]
    parent.items[idx] = new
    return cond


def _commit(rung, cond):
    rung.cond = normalize(cond)


# ---------------- 触点 ----------------

def contact_at(program, r, k) -> Contact:
    rung = _rung(program, r)
    return _locate(normalize(rung.cond), k)[1]


def set_contact(program, r, k, addr=None, nc=None):
    rung, cond = _work(program, r)
    path, leaf = _locate(cond, k)
    new_addr = leaf.addr if addr is None else addr
    _check_addr(new_addr, "XYMTC")
    new = Contact(new_addr, leaf.nc if nc is None else bool(nc))
    _commit(rung, _replace_leaf(cond, path, new))


def insert_series(program, r, k, contact, after=True):
    _check_contact(contact)
    rung, cond = _work(program, r)
    path, leaf = _locate(cond, k)
    parent = path[-1][0] if path else None
    if isinstance(parent, Series):
        idx = path[-1][1]
        parent.items.insert(idx + 1 if after else idx, contact)
    else:
        new = Series([leaf, contact] if after else [contact, leaf])
        cond = _replace_leaf(cond, path, new)
    _commit(rung, cond)


def append_series(program, r, contact):
    _check_contact(contact)
    rung, cond = _work(program, r)
    if isinstance(cond, Series):
        cond.items.append(contact)
    else:
        cond = Series([cond, contact])
    _commit(rung, cond)


def add_parallel(program, r, k1, contact, k2=None):
    _check_contact(contact)
    rung, cond = _work(program, r)
    if k2 is None:
        k2 = k1
    if k1 > k2:
        raise EditError("并联范围不对：起点在终点右边")
    p1, leaf1 = _locate(cond, k1)
    if k1 == k2:
        cond = _replace_leaf(cond, p1, Parallel([leaf1, contact]))
    else:
        p2, leaf2 = _locate(cond, k2)
        par1 = p1[-1] if p1 else None
        par2 = p2[-1] if p2 else None
        if (par1 is None or par2 is None or par1[0] is not par2[0]
                or not isinstance(par1[0], Series)):
            raise EditError("只能给同一串联里连续的触点并联一条支路")
        series, i1, i2 = par1[0], par1[1], par2[1]
        span = series.items[i1:i2 + 1]
        series.items[i1:i2 + 1] = [Parallel([Series(span), contact])]
    _commit(rung, cond)


def delete_contact(program, r, k):
    rung, cond = _work(program, r)
    path, leaf = _locate(cond, k)
    if not path:
        raise EditError("这一行只剩这一个触点，不能删（可以删整行）")
    parent, idx = path[-1]
    del parent.items[idx]
    _commit(rung, cond)


# ---------------- 行 ----------------

def _check_rung(rung):
    if not isinstance(rung, Rung):
        raise EditError("不是 Rung")
    for a in _contacts(rung.cond):
        _check_addr(a, "XYMTC")
    _check_out(rung.out)


def _contacts(node):
    if isinstance(node, Contact):
        yield node.addr
    else:
        for it in node.items:
            yield from _contacts(it)


def add_rung(program, index=None, rung=None):
    if rung is None:
        rung = Rung(Contact("X0"), Out("Y0"))
    _check_rung(rung)
    n = len(program.rungs)
    if index is None:
        index = n
    if not isinstance(index, int) or not 0 <= index <= n:
        raise EditError(f"插入位置越界：{index}")
    rung = Rung(normalize(copy.deepcopy(rung.cond)), rung.out)
    program.rungs.insert(index, rung)


def delete_rung(program, r):
    _rung(program, r)
    del program.rungs[r]


def move_rung(program, r, delta):
    _rung(program, r)
    j = r + delta
    if not 0 <= j < len(program.rungs):
        raise EditError("不能再往那个方向移动了")
    program.rungs[r], program.rungs[j] = program.rungs[j], program.rungs[r]


def _check_out(out):
    if isinstance(out, Out):
        _check_addr(out.addr, "YM", "OUT 的地址")
    elif isinstance(out, OutT):
        _check_addr(out.addr, "T", "OUT T 的地址")
        if not isinstance(out.k, int) or out.k < 1:
            raise EditError("K 必须是 ≥1 的整数")
    elif isinstance(out, OutC):
        _check_addr(out.addr, "C", "OUT C 的地址")
        if not isinstance(out.k, int) or out.k < 1:
            raise EditError("K 必须是 ≥1 的整数")
    elif isinstance(out, Rst):
        _check_addr(out.addr, "TC", "RST 的地址")
    else:
        raise EditError("不认识的输出类型")


def set_output(program, r, out):
    rung = _rung(program, r)
    _check_out(out)
    rung.out = out


def replace_program(program, new):
    """整个换成 new 的内容（"恢复示例""参考答案"用，能撤销）"""
    program.rungs[:] = copy.deepcopy(new.rungs)


# ---------------- 撤销 / 重做 ----------------

class History:
    def __init__(self, program):
        self.program = program
        self._undo = []
        self._redo = []

    def _snap(self):
        return copy.deepcopy(self.program.rungs)

    def apply(self, op, *args, **kw):
        snap = self._snap()
        try:
            op(self.program, *args, **kw)
        except Exception:
            self.program.rungs[:] = snap          # 保险：失败一定回到原样
            raise
        self._undo.append(snap)
        self._redo.clear()

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._snap())
        self.program.rungs[:] = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self._snap())
        self.program.rungs[:] = self._redo.pop()
        return True
