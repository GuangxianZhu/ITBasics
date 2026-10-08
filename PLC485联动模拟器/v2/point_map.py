# -*- coding: utf-8 -*-
"""
④ 点表 —— 清洗机的原 IO ↔ 协议参数 的对应关系和策略
（如果「远程」「在线」其实是一个信号，删掉一行就行）
"""

# 清洗机 → 温水器：PLC 读入 DI/AI，写到温水器
#   readback: 用哪个参数的哪一位确认温水器真的执行了（对账用）
#   hold_if_alarm: 温水器有这些报警位时不要硬写（它会拒绝）
#   needs: 温水器这一位为 1 之后才写（例：先确认远程，再写其它）
WRITE_POINTS = [
    dict(src='W0', name='远程', param='001', readback=('101', 0)),
    dict(src='W1', name='在线', param='005', readback=('101', 5), needs=('101', 0)),
    dict(src='W2', name='通水', param='003', readback=('101', 3), needs=('101', 0)),
    dict(src='W3', name='加热', param='002', readback=('101', 1), needs=('101', 0),
         hold_if_alarm=[0, 1, 3]),
    dict(src='AD', name='温度设定', param='010', readback=('010', None), needs=('101', 0)),
]

# 复位：清洗机原来就有的复位信号，上升沿时转发
RESET = dict(src='W4', name='复位', param='004', value=1)

# 温度设定 AD（4-20mA）
AD = dict(
    ma_min=4.0, ma_max=20.0,      # 量程（待公司确认）
    t_min=25.0, t_max=85.0,       # 对应温度 ℃（待公司确认）
    broken_below=3.6,             # 低于此值判 AD 断线
    over_above=20.8,              # 高于此值判超量程
    filter_tau=0.3,               # 一阶滤波时间常数 s
    deadband=0.5,                 # 变化小于此值(℃)不更新设定
    settle=0.1,                   # 原始值和滤波值差小于此值(mA)才算稳定
)

# 温水器 → 清洗机：轮询读回，输出 DO
#   on_comm_fault: 通信异常时 'off' 强制关 / 'on' 强制开 / 'hold' 保持最后值
#   also: PLC 自己的判断也并进这个输出
READ_POINTS = [
    dict(dst='R0', name='温度Ready', param='101', bit=4, on_comm_fault='off', fault=False),
    dict(dst='R1', name='过热', param='102', bit=0, on_comm_fault='hold', fault=True),
    dict(dst='R2', name='漏水', param='102', bit=1, on_comm_fault='hold', fault=True),
    dict(dst='R3', name='轻故障', param='102', bit=2, on_comm_fault='hold', fault=True,
         also=['ad_fault', 'mismatch']),
    dict(dst='R4', name='重故障', param='102', bit=3, on_comm_fault='on', fault=True,
         also=['comm_fault']),
]

# 故障信号极性：False = 1 表示故障（a 接点）；True = 0 表示故障（b 接点）
# b 接点的好处：PLC 断电/断线时输出全 0，清洗机直接看到「故障」
FAULT_ACTIVE_LOW = False

# 轮询表：一圈读这几个参数
POLL = ['101', '102', '100', '010']

# 时序参数
TIMING = dict(
    station=1,
    timeout=0.2,          # 等响应的超时 s
    fail_limit=3,         # 连续失败几次判通信异常
    poll_cycle=0.4,       # 轮询一圈的周期 s
    poll_cycle_fault=0.5, # 通信异常时每帧间隔 s
    gap=0.005,            # 帧间隔 s
    write_retry=3,        # 写命令超时/校验错的重发次数
    resend_interval=1.0,  # 对账不一致时多久重发一次 s
    nak_wait=2.0,         # 被 NAK02/04/05 拒绝后多久再试 s
    write_min_interval=0.5,  # 同一参数两次写入的最短间隔 s（防 AD 刷屏）
    mismatch_limit=3,     # 写了 ACK 了但读回还是不对，几次后报「指令不一致」
    stale=1.5,            # 读回数据多久算过期 s
    recover_ok=1.0,       # 复位时要求最近这段时间内通信正常 s
)
