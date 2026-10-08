# -*- coding: utf-8 -*-
"""
③ 命令表（参数表）—— 拿到手册后照着「参数一览 / 命令一览」填这里

每个参数相当于 Modbus 的一个寄存器地址。
  code   参数号（ASCII 协议里是 3 位字符串；Modbus 里当寄存器地址用）
  rw     'R' 只读 / 'W' 只写 / 'RW'
  width  ASCII 协议里数据的位数
  fmt    'dec' 十进制 / 'hex' 十六进制
  scale  实际值 = 原始整数 × scale
  bits   位定义（状态字、报警字用）
"""


class Param:
    def __init__(self, code, name, rw, width=1, fmt='dec', scale=1.0, unit='', bits=None,
                 lo=None, hi=None):
        self.code = code
        self.name = name
        self.rw = rw
        self.width = width
        self.fmt = fmt
        self.scale = scale
        self.unit = unit
        self.bits = bits or []
        self.lo, self.hi = lo, hi

    def describe(self, raw_int):
        """把原始整数翻成人能看懂的文字（详情面板用）"""
        if raw_int is None:
            return ''
        if self.bits:
            on = [n for i, n in enumerate(self.bits) if n and raw_int >> i & 1]
            return '%s=%s' % (self.name, '、'.join(on) or '无')
        if self.scale != 1.0:
            return '%s=%.1f%s' % (self.name, raw_int * self.scale, self.unit)
        return '%s=%d%s' % (self.name, raw_int, self.unit)


STATUS_BITS = ['远程', '运转指令', '加热中', '通水指令', '温度Ready', '在线', '流量OK', '']
ALARM_BITS = ['过热', '漏水', '轻故障', '重故障', '急停', '空焚', '灯管断线', '通信超时']

PARAMS = {p.code: p for p in [
    Param('001', '远程', 'W', 1),
    Param('002', '运转', 'W', 1),
    Param('003', '通水', 'W', 1),
    Param('004', '复位', 'W', 1),
    Param('005', '在线', 'W', 1),
    Param('010', 'SV', 'RW', 4, scale=0.1, unit='℃', lo=250, hi=850),
    Param('100', 'PV', 'R', 4, scale=0.1, unit='℃'),
    Param('101', '状态字', 'R', 2, fmt='hex', bits=STATUS_BITS),
    Param('102', '报警字', 'R', 2, fmt='hex', bits=ALARM_BITS),
]}

# 拒绝码（ASCII 协议的 NAK 错误码 / Modbus 的异常码 共用一套编号）
NAK = {
    '01': '校验/格式错误',
    '02': '本地模式中',
    '03': '参数号不存在或不可写',
    '04': '故障中不能运转',
    '05': '急停输入中',
    '06': '设定值超范围',
}
