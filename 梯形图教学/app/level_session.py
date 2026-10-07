"""关卡进度（纯逻辑）。当前程序、通过记录、判定、答题。"""
import copy

from levels import ALL_LEVELS


class LevelSession:
    def __init__(self):
        self.levels = ALL_LEVELS
        self.index = None            # None = 不在关卡里（自由示例模式）
        self.program = None          # 当前关卡里正在用的程序（P5 编辑器会改它）
        self.passed = set()          # 通过的关卡 ID
        self.last_result = None      # (ok, msg)

    @property
    def level(self):
        return None if self.index is None else self.levels[self.index]

    def enter(self, index):
        self.index = index
        self.program = copy.deepcopy(self.level.EXAMPLE)
        self.last_result = None
        return self.program

    def leave(self):
        self.index = None
        self.program = None
        self.last_result = None

    def restore_example(self):
        self.program = copy.deepcopy(self.level.EXAMPLE)
        return self.program

    def load_solution(self):
        self.program = copy.deepcopy(self.level.SOLUTION)
        return self.program

    def judge(self):
        """task 关卡：判定当前程序"""
        ok, msg = self.level.check(self.program)
        if ok:
            self.passed.add(self.level.ID)
        self.last_result = (ok, msg)
        return ok, msg

    def answer(self, choice):
        """quiz 关卡：选第 choice 个选项"""
        lv = self.level
        ok = choice == lv.ANSWER
        msg = "回答正确！" if ok else f"不对。正确答案：{lv.CHOICES[lv.ANSWER]}"
        if ok:
            self.passed.add(lv.ID)
        self.last_result = (ok, msg)
        return ok, msg

    def has_next(self):
        return self.index is not None and self.index + 1 < len(self.levels)
