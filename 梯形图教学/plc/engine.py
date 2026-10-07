"""PLC 扫描引擎"""
from dataclasses import dataclass, field
from plc.model import Contact, Series, Parallel, Out, OutT, OutC, Rst, normalize


@dataclass
class Step:
    """一个扫描步骤"""
    phase: str          # "input" | "rung" | "output"
    rung: int | None    # phase=="rung" 时为行号（0 起），否则 None
    powered: bool | None  # phase=="rung" 时为该行条件是否导通，否则 None


def evaluate(cond, read, trace=None) -> bool:
    """read(addr)->bool 读元件状态。
       触点导通: 常开 = read(addr)；常闭 = not read(addr)
       Series = 全部导通；Parallel = 任一导通。
       trace 是 dict 时：对树里每个节点 n，写 trace[id(n)] = 该节点右端是否有电。
       触点右端 = 左端有电 and 触点导通
       Series：依次传递，节点右端 = 最后一个子节点右端
       Parallel：每个分支左端 = Parallel 左端；Parallel 右端 = 任一分支右端
       整棵树左端 = True（左母线）
    """
    def _eval_with_left_power(cond, left_power, read, trace):
        """内部递归函数，跟踪左端是否有电"""
        if isinstance(cond, Contact):
            # 触点导通逻辑
            state = read(cond.addr)
            if cond.nc:
                # b接点（常闭）
                contact_on = not state
            else:
                # a接点（常开）
                contact_on = state

            # 右端有电 = 左端有电 and 触点导通
            right_power = left_power and contact_on

            if trace is not None:
                trace[id(cond)] = right_power

            return right_power

        elif isinstance(cond, Series):
            # 串联：依次传递电流
            current_power = left_power
            for item in cond.items:
                # 每一项的左端 = 前一项的右端
                current_power = _eval_with_left_power(item, current_power, read, trace)

            # Series 的右端 = 最后一个子项的右端
            if trace is not None:
                trace[id(cond)] = current_power

            return current_power

        elif isinstance(cond, Parallel):
            # 并联：每个分支的左端都等于 Parallel 的左端
            result = False
            for item in cond.items:
                # 每一项的左端 = Parallel 的左端
                item_result = _eval_with_left_power(item, left_power, read, trace)
                result = result or item_result

            # Parallel 的右端 = 任一分支右端
            if trace is not None:
                trace[id(cond)] = result

            return result

        return False

    # 整棵树的左端 = True（左母线）
    return _eval_with_left_power(cond, True, read, trace)


class PLC:
    """PLC 扫描执行引擎"""

    def __init__(self, program, scan_ms=10):
        self.program = program
        self.scan_ms = scan_ms
        self.scan_count = 0
        self.last_power = [False] * len(program.rungs)

        # 元件映像和外部端子
        self._x_external = {}  # X 外部端子
        self._x_image = {}     # X 映像
        self._y_image = {}     # Y 映像
        self._y_external = {}  # Y 外部端子
        self._m_image = {}     # M 映像

        # 定时器和计数器
        self._timer_acc = {}   # 定时器累计时间(ms)
        self._timer_k = {}     # 定时器设定值(100ms单位)
        self._counter_val = {} # 计数器当前值
        self._counter_k = {}   # 计数器设定值
        self._counter_prev = {} # 计数器上一次执行时的状态

        # 验证所有地址
        self._validate_addresses(program)

    def _validate_addresses(self, program):
        """验证所有地址格式"""
        def check_addr(addr):
            if not addr or len(addr) < 2:
                raise ValueError(f"Invalid address: {addr}")
            prefix = addr[0]
            if prefix not in "XYMTC":
                raise ValueError(f"Invalid address prefix: {addr}")
            try:
                int(addr[1:])
            except ValueError:
                raise ValueError(f"Invalid address: {addr}")

        def walk(node):
            if isinstance(node, Contact):
                check_addr(node.addr)
            elif isinstance(node, (Series, Parallel)):
                for item in node.items:
                    walk(item)

        for rung in program.rungs:
            walk(rung.cond)
            if isinstance(rung.out, Out):
                check_addr(rung.out.addr)
            elif isinstance(rung.out, (OutT, OutC)):
                check_addr(rung.out.addr)
            elif isinstance(rung.out, Rst):
                check_addr(rung.out.addr)

    def set_input(self, addr, value):
        """设置 X 的外部端子，下一次输入采样时才进 X 映像"""
        self._x_external[addr] = value

    def get(self, addr) -> bool:
        """读映像：X/Y/M 的映像值；T/C 为"到达"触点状态"""
        prefix = addr[0]

        if prefix == "X":
            return self._x_image.get(addr, False)
        elif prefix == "Y":
            return self._y_image.get(addr, False)
        elif prefix == "M":
            return self._m_image.get(addr, False)
        elif prefix == "T":
            # T的到达触点：累计 >= 设定值
            acc = self._timer_acc.get(addr, 0)
            k = self._timer_k.get(addr, 0)
            return acc >= k
        elif prefix == "C":
            # C的到达触点：当前值 >= 设定值
            val = self._counter_val.get(addr, 0)
            k = self._counter_k.get(addr, 0)
            return val >= k

        return False

    def output(self, addr) -> bool:
        """读 Y 的外部端子（只在输出刷新时更新）"""
        return self._y_external.get(addr, False)

    def timer_ms(self, addr) -> int:
        """定时器当前累计毫秒"""
        return self._timer_acc.get(addr, 0)

    def counter_value(self, addr) -> int:
        """计数器当前值"""
        return self._counter_val.get(addr, 0)

    def steps(self):
        """生成器：执行一整轮扫描，每完成一个阶段 yield Step"""
        # Phase 1: input
        for addr in self._x_external:
            self._x_image[addr] = self._x_external[addr]
        yield Step("input", None, None)

        # Phase 2: execute rungs
        for i, rung in enumerate(self.program.rungs):
            # 求条件
            p = evaluate(rung.cond, self.get)
            self.last_power[i] = p

            # 执行输出
            if isinstance(rung.out, Out):
                # OUT Y0 / OUT M0
                addr = rung.out.addr
                if addr[0] == "Y":
                    self._y_image[addr] = p
                elif addr[0] == "M":
                    self._m_image[addr] = p

            elif isinstance(rung.out, OutT):
                # OUT T0 K50
                addr = rung.out.addr
                k = rung.out.k
                self._timer_k[addr] = k * 100  # 转换为 ms

                if p:
                    # 条件为真：累计 += scan_ms
                    if addr not in self._timer_acc:
                        self._timer_acc[addr] = 0
                    self._timer_acc[addr] = min(self._timer_acc[addr] + self.scan_ms, k * 100)
                else:
                    # 条件为假：累计 = 0
                    self._timer_acc[addr] = 0

            elif isinstance(rung.out, OutC):
                # OUT C0 K3
                addr = rung.out.addr
                k = rung.out.k
                self._counter_k[addr] = k

                # 初始化计数器
                if addr not in self._counter_val:
                    self._counter_val[addr] = 0
                if addr not in self._counter_prev:
                    self._counter_prev[addr] = False

                # 检测上升沿（False -> True）
                if p and not self._counter_prev[addr]:
                    # 上升沿，且未到设定值
                    if self._counter_val[addr] < k:
                        self._counter_val[addr] += 1

                # 记录本次状态
                self._counter_prev[addr] = p

            elif isinstance(rung.out, Rst):
                # RST C0 / RST T0
                addr = rung.out.addr
                if p:
                    prefix = addr[0]
                    if prefix == "T":
                        self._timer_acc[addr] = 0
                    elif prefix == "C":
                        self._counter_val[addr] = 0

            yield Step("rung", i, p)

        # Phase 3: output
        for addr in list(self._y_image.keys()):
            self._y_external[addr] = self._y_image[addr]
        self.scan_count += 1
        yield Step("output", None, None)

    def scan(self):
        """执行一整轮扫描"""
        for _ in self.steps():
            pass
