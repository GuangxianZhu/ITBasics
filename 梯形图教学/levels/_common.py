"""关卡判定用的小工具（纯逻辑，不依赖 panda3d）"""
import copy

from sim.runner import Runner
from sim.tank import Tank


def runner(program, level=0.0):
    """深拷贝程序再跑，保证判定不改动玩家的程序"""
    return Runner(copy.deepcopy(program), tank=Tank(level=level))


def tap(r, addr, sec=0.05):
    """按一下按钮再松开"""
    r.press(addr)
    r.run(sec)
    r.release(addr)


class Fail(Exception):
    """判定不通过，消息给玩家看"""


def judge(fn):
    """把 check 写成"不满足就 raise Fail(提示)"，这里统一包成 (bool, str)"""
    def check(program):
        if not program.rungs:
            return False, "程序是空的。"
        try:
            fn(program)
        except Fail as e:
            return False, str(e)
        return True, "通过！"
    return check
