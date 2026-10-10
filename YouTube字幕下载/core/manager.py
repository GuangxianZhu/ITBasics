"""任务队列：工作线程从队列取任务执行。界面只调用 add / cancel / retry，进度直接读 Task 字段。"""
import queue
import threading

from core import runner
from core.task import FINISHED, WAITING


class Manager:
    def __init__(self, log, ffmpeg, workers=2):
        self.log_cb = log          # log(task, msg)
        self.ffmpeg = ffmpeg
        self.tasks = []
        self._q = queue.Queue()
        self._lock = threading.Lock()
        for _ in range(workers):
            threading.Thread(target=self._worker, daemon=True).start()

    def add(self, task):
        with self._lock:
            self.tasks.append(task)
        self._q.put(task)
        self.log_cb(task, f"加入队列：{task.opts.describe()}  {task.url}")

    def cancel(self, task):
        if task.status not in FINISHED:
            task.cancel_requested = True
            if task.status == WAITING:
                task.note = "取消中…"

    def retry(self, task):
        if task.status in FINISHED:
            task.reset()
            self._q.put(task)
            self.log_cb(task, "重试")

    def clear_finished(self):
        with self._lock:
            self.tasks = [t for t in self.tasks if t.status not in FINISHED]

    def active_count(self):
        return sum(1 for t in self.tasks if t.status not in FINISHED)

    def _worker(self):
        while True:
            task = self._q.get()
            if task.cancel_requested:
                from core.task import CANCELLED
                task.status, task.note = CANCELLED, "已取消"
                continue
            self.log_cb(task, "开始")
            runner.run(task, self.log_cb, self.ffmpeg)
            self.log_cb(task, f"→ {task.status}" + (f"：{task.note}" if task.note and task.status != "完成" else ""))
