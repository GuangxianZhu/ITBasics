# -*- coding: utf-8 -*-
"""
QwenBlender agent —— 让本地 Qwen 通过工具调用在 Blender 里建模
只用 Python 标准库，可以直接用 Blender 自带的 Python 运行（启动.bat 会帮你找）。

流程：你输入需求 → Qwen 写脚本 → Blender 后台执行 + 自动检查 + 渲染四视图
      → 报告和图片回给 Qwen → Qwen 自己改 → …… → Qwen 调用 finish
每次任务的全部记录都在 runs/<时间>/ 里。
"""
import base64
import datetime
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------ 配置（可以用环境变量覆盖）
MODEL = os.environ.get('QB_MODEL', 'qwen3.8:27b-q8_0')
OLLAMA = os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434').rstrip('/')
if not OLLAMA.startswith('http'):
    OLLAMA = 'http://' + OLLAMA
NUM_CTX = int(os.environ.get('QB_CTX', '65536'))
THINK = os.environ.get('QB_THINK', '1') == '1'
MAX_STEPS = int(os.environ.get('QB_MAX_STEPS', '40'))
BLENDER_TIMEOUT = 300

DEFAULT_TASK = ('做一个法兰式联轴器的半体（一个零件，平放在地面上，轴线沿 Z）：\n'
                '- 法兰盘：外径 80，厚 12，底面贴地\n'
                '- 法兰上面中间是轮毂：外径 40，高 30（从法兰上表面往上算）\n'
                '- 中心轴孔：直径 20，贯穿整个零件\n'
                '- 轴孔带一条键槽：宽 6，从孔壁往外深 2.8，贯穿全长\n'
                '- 法兰上 6 个螺栓孔：直径 9，均布在直径 60 的圆周上，贯穿法兰\n'
                '- 法兰外圆和轮毂顶面边缘倒角/倒圆 1 mm 左右\n'
                '做完再配 6 颗 M8 螺栓（螺杆直径 8，头部外径 13、高 5.5），从上往下插在螺栓孔里，螺栓头压在法兰上表面，'
                '螺杆长度和法兰厚度一样。')


def C(code, s):
    return f'\033[{code}m{s}\033[0m'


if os.name == 'nt':
    os.system('')  # 打开 Windows 终端的颜色支持
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


# ------------------------------------------------------------ 找 Blender
def find_blender():
    p = os.environ.get('BLENDER')
    if p and os.path.isfile(p):
        return p
    cands = sorted(glob.glob(r'C:\Program Files\Blender Foundation\Blender*\blender.exe'), reverse=True)
    if cands:
        return cands[0]
    for name in ('blender.exe', 'blender'):
        for d in os.environ.get('PATH', '').split(os.pathsep):
            f = os.path.join(d, name)
            if os.path.isfile(f):
                return f
    return None


BLENDER = find_blender()


# ------------------------------------------------------------ 工具定义
def T(name, desc, props, req):
    return {'type': 'function', 'function': {
        'name': name, 'description': desc,
        'parameters': {'type': 'object', 'properties': props, 'required': req}}}


S = {'type': 'string'}
TOOLS = [
    T('list_files', '列出 QwenBlender 文件夹里某个子目录的文件。可以看 examples（范例）、models（你写的模型）。',
      {'dir': dict(S, description='子目录，例如 "examples" 或 "models"')}, ['dir']),
    T('read_file', '读取 QwenBlender 文件夹里的文本文件，例如 "examples/01_L形支架.py"、"qbkit.py"、"models/xxx.py"。',
      {'path': S}, ['path']),
    T('write_model', '把完整的模型脚本写到 models/<name>.py（覆盖原文件）。写完要调用 run_model 才会执行。',
      {'name': dict(S, description='模型名，只用英文字母、数字、下划线，例如 flange_coupling'),
       'code': dict(S, description='完整的 Python 脚本，开头必须是 import qbkit as K 和 K.reset()')}, ['name', 'code']),
    T('edit_model', '小改动：把 models/<name>.py 里的一段文字 old 替换成 new（old 必须在文件里正好出现一次）。改完要重新 run_model。',
      {'name': S, 'old': S, 'new': S}, ['name', 'old', 'new']),
    T('run_model', '用 Blender 执行 models/<name>.py，返回检查报告（穿插/悬空/尺寸），并在下一条消息里给你四视图图片。',
      {'name': S}, ['name']),
    T('finish', '模型已经做好、检查通过、四视图也确认过了，结束任务。',
      {'summary': dict(S, description='几句话：做了哪些零件、主要尺寸、有没有没做到的地方')}, ['summary']),
]


class Session:
    def __init__(self, task):
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        self.dir = os.path.join(HERE, 'runs', stamp)
        os.makedirs(self.dir, exist_ok=True)
        self.n_run = 0
        self.last_model = None
        self.last_blend = None
        self.done = False
        with open(os.path.join(self.dir, 'task.txt'), 'w', encoding='utf-8') as f:
            f.write(task + '\n')
        self.log_f = open(os.path.join(self.dir, 'chat.jsonl'), 'a', encoding='utf-8')

    def log(self, obj):
        self.log_f.write(json.dumps(obj, ensure_ascii=False) + '\n')
        self.log_f.flush()

    # ---------------- 工具实现
    def _safe(self, rel):
        p = os.path.abspath(os.path.join(HERE, rel))
        if not p.startswith(HERE):
            raise ValueError('只能访问 QwenBlender 文件夹里面的文件')
        return p

    def list_files(self, dir):
        p = self._safe(dir)
        if not os.path.isdir(p):
            return f'目录不存在：{dir}'
        names = sorted(os.listdir(p))
        return '\n'.join(names) if names else '（空）'

    def read_file(self, path):
        p = self._safe(path)
        if not os.path.isfile(p):
            return f'文件不存在：{path}'
        txt = open(p, encoding='utf-8', errors='replace').read()
        if len(txt) > 30000:
            txt = txt[:30000] + '\n……（文件太长，后面省略）'
        return txt

    def _model_path(self, name):
        name = re.sub(r'[^A-Za-z0-9_]', '_', name.replace('.py', '')) or 'model'
        return name, os.path.join(HERE, 'models', name + '.py')

    def write_model(self, name, code):
        name, p = self._model_path(name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(code)
        self.last_model = name
        return f'已写入 models/{name}.py（{len(code.splitlines())} 行）。下一步请调用 run_model 运行并检查。'

    def edit_model(self, name, old, new):
        name, p = self._model_path(name)
        if not os.path.isfile(p):
            return f'models/{name}.py 不存在，请先 write_model'
        txt = open(p, encoding='utf-8').read()
        k = txt.count(old)
        if k != 1:
            return f'old 在文件里出现了 {k} 次（必须正好 1 次）。请多带几行上下文，或者直接 write_model 重写整个文件。'
        with open(p, 'w', encoding='utf-8') as f:
            f.write(txt.replace(old, new))
        self.last_model = name
        return f'已修改 models/{name}.py。下一步请调用 run_model。'

    def run_model(self, name):
        name, p = self._model_path(name)
        if not os.path.isfile(p):
            return f'models/{name}.py 不存在，请先 write_model', None
        if not BLENDER:
            return '找不到 Blender，请让用户设置 BLENDER 环境变量', None
        self.n_run += 1
        out = os.path.join(self.dir, f'run{self.n_run:02d}_{name}')
        os.makedirs(out, exist_ok=True)
        # 留一份这一次运行时的脚本
        with open(p, encoding='utf-8') as f, open(os.path.join(out, name + '.py'), 'w', encoding='utf-8') as g:
            g.write(f.read())
        cmd = [BLENDER, '-b', '--factory-startup', '--python', os.path.join(HERE, 'run_and_check.py'), '--', p, out]
        print(C('90', f'  [Blender] 运行 {name} …'), flush=True)
        t0 = time.time()
        try:
            env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
            r = subprocess.run(cmd, capture_output=True, timeout=BLENDER_TIMEOUT, cwd=HERE, env=env)
            raw = (r.stdout or b'').decode('utf-8', 'replace') + (r.stderr or b'').decode('utf-8', 'replace')
        except subprocess.TimeoutExpired:
            return f'Blender 运行超过 {BLENDER_TIMEOUT} 秒被中止。脚本可能有死循环，或者面数太多（seg 调小一点）。', None
        with open(os.path.join(out, 'blender_log.txt'), 'w', encoding='utf-8') as f:
            f.write(raw)
        rep_p = os.path.join(out, 'report.txt')
        if os.path.isfile(rep_p):
            rep = open(rep_p, encoding='utf-8').read().strip()
        else:
            rep = '【结果】Blender 没有生成报告，下面是日志末尾：\n' + raw[-2000:]
        # 把脚本自己 print / K.info() 的输出也带上
        m = re.search(r'=====MODEL_OUT_BEGIN=====\r?\n(.*?)=====MODEL_OUT_END=====', raw, re.S)
        if m:
            prints = [ln for ln in m.group(1).splitlines()
                      if ln.strip() and not ln.startswith(('Info:', 'Warning:', 'Read ', 'Fra:'))]
            if prints:
                rep += '\n【脚本里 print / info 的输出】\n' + '\n'.join(prints[:60])
        print(C('90', f'  [Blender] 用时 {time.time() - t0:.1f} 秒'))
        img = os.path.join(out, 'views_small.png')
        blend = os.path.join(out, 'model.blend')
        if os.path.isfile(blend):
            self.last_blend = blend
        return rep, (img if os.path.isfile(img) else None)


# ------------------------------------------------------------ 和 Ollama 对话
def chat(messages, think):
    body = {'model': MODEL, 'messages': messages, 'tools': TOOLS, 'stream': True,
            'options': {'num_ctx': NUM_CTX, 'temperature': 0.6, 'top_p': 0.95}}
    if think:
        body['think'] = True
    req = urllib.request.Request(OLLAMA + '/api/chat', data=json.dumps(body).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
    content, thinking, calls = [], [], []
    in_think = False
    stats = {}
    with urllib.request.urlopen(req, timeout=3600) as resp:
        for line in resp:
            if not line.strip():
                continue
            ch = json.loads(line)
            if 'error' in ch:
                raise RuntimeError(ch['error'])
            m = ch.get('message', {})
            if m.get('thinking'):
                if not in_think:
                    print(C('90', '  (思考) '), end='')
                    in_think = True
                thinking.append(m['thinking'])
                print(C('90', m['thinking']), end='', flush=True)
            if m.get('content'):
                if in_think:
                    print()
                    in_think = False
                content.append(m['content'])
                print(m['content'], end='', flush=True)
            for tc in m.get('tool_calls') or []:
                calls.append(tc)
            if ch.get('done'):
                stats = ch
    print()
    if stats.get('eval_count') and stats.get('eval_duration'):
        tps = stats['eval_count'] / (stats['eval_duration'] / 1e9)
        print(C('90', f'  [{stats["eval_count"]} tokens, {tps:.1f} tok/s, 上下文 {stats.get("prompt_eval_count", "?")}]'))
    return ''.join(content), ''.join(thinking), calls, stats


def strip_old_images(messages):
    """图片很占上下文，只保留最新一张"""
    last_img = max((i for i, m in enumerate(messages) if m.get('images')), default=-1)
    for i, m in enumerate(messages):
        if m.get('images') and i != last_img:
            m.pop('images')
            m['content'] = '（这是之前一次运行的四视图，图片已省略）'


def est_tokens(messages):
    n = 0
    for m in messages:
        n += len(m.get('content') or '') + len(m.get('thinking') or '')
        for tc in m.get('tool_calls') or []:
            n += len(json.dumps(tc['function'].get('arguments') or {}, ensure_ascii=False))
        if m.get('images'):
            n += 3000
    return n // 2


def compact(messages):
    """上下文快满时，把旧的长内容折叠掉（系统提示和任务不动，最近 8 条不动）"""
    keep_from = len(messages) - 8
    for i, m in enumerate(messages[:keep_from]):
        if i < 2:
            continue
        m.pop('thinking', None)
        if m['role'] == 'tool' and len(m['content']) > 600:
            m['content'] = m['content'][:600] + '\n……（旧结果已折叠）'
        for tc in m.get('tool_calls') or []:
            a = tc['function'].get('arguments') or {}
            if isinstance(a, dict) and len(a.get('code', '')) > 300:
                a['code'] = '（旧版本代码已省略，当前代码请看 models/ 里的文件）'


def main():
    print(C('96', '=== QwenBlender：让 Qwen 用 Blender 建模 ==='))
    print(f'模型 {MODEL}   上下文 {NUM_CTX}   思考 {"开" if THINK else "关"}')
    print(f'Blender：{BLENDER or "没找到！"}')
    if not BLENDER:
        print('请编辑 启动.bat，把 BLENDER= 那一行改成你的 blender.exe 路径。')
        return
    try:
        urllib.request.urlopen(OLLAMA + '/api/tags', timeout=5).read()
    except Exception as e:
        print(C('91', f'连不上 Ollama（{OLLAMA}）：{e}\n请先打开 Ollama。'))
        return

    task = ' '.join(sys.argv[1:]).strip()
    if task.startswith('@'):   # @文件名：从文本文件读任务（中文放文件里，避免 bat 传参乱码）
        tf = task[1:].strip('"')
        tf = tf if os.path.isabs(tf) else os.path.join(HERE, tf)
        task = open(tf, encoding='utf-8').read().strip()
    if not task:
        print('\n请输入要建的模型（可以写很多字，一行写完回车）。')
        print(C('93', '直接回车 = 用默认测试题：法兰联轴器半体 + 6 颗螺栓'))
        task = input('> ').strip() or DEFAULT_TASK
    print(C('96', '\n任务：') + task + '\n')

    rules = open(os.path.join(HERE, '建模规范.md'), encoding='utf-8').read()
    system = ('你是一个机械建模工程师，用 Python 脚本 + qbkit 工具箱在 Blender 里建模。'
              '你只能通过工具操作。请严格按照下面的建模规范工作。回答和总结用中文。\n\n' + rules)
    messages = [{'role': 'system', 'content': system},
                {'role': 'user', 'content': '任务：\n' + task}]
    ses = Session(task)
    ses.log({'system': system, 'task': task, 'model': MODEL})

    think = THINK
    nudges = 0
    for step in range(1, MAX_STEPS + 1):
        print(C('94', f'\n—— 第 {step} 步 ——'))
        try:
            content, thinking, calls, stats = chat(messages, think)
        except urllib.error.HTTPError as e:
            msg = e.read().decode('utf-8', 'replace')
            if think and 'think' in msg:
                print(C('93', '这个模型不支持 think 参数，关掉思考重试'))
                think = False
                continue
            print(C('91', f'Ollama 出错：{e} {msg}'))
            break
        except Exception as e:
            print(C('91', f'Ollama 出错：{e}'))
            break
        asst = {'role': 'assistant', 'content': content}
        if thinking:
            asst['thinking'] = thinking
        if calls:
            asst['tool_calls'] = calls
        messages.append(asst)
        ses.log({'step': step, 'assistant': content, 'thinking': thinking, 'tool_calls': calls,
                 'prompt_tokens': stats.get('prompt_eval_count'), 'eval_tokens': stats.get('eval_count')})

        if not calls:
            nudges += 1
            if nudges > 3:
                print(C('93', 'Qwen 连续几次没有调用工具，停止。'))
                break
            messages.append({'role': 'user', 'content': '请通过工具继续：写脚本用 write_model，运行检查用 run_model，全部确认没问题后用 finish。'})
            continue
        nudges = 0

        image_msgs = []
        for tc in calls:
            fn = tc['function']['name']
            args = tc['function'].get('arguments') or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            short = {k: (v if len(str(v)) < 80 else str(v)[:77] + '…') for k, v in args.items()}
            print(C('92', f'  → {fn}({short})'))
            try:
                if fn == 'run_model':
                    text, img = ses.run_model(**args)
                    if img:
                        with open(img, 'rb') as f:
                            image_msgs.append({'role': 'user', 'images': [base64.b64encode(f.read()).decode()],
                                               'content': f'这是 run_model 第 {ses.n_run} 次运行的四视图：左上=斜视，右上=正视（从 -Y 看），'
                                                          '左下=右视（从 +X 看），右下=俯视。请对照任务要求检查形状、比例、孔和槽的位置数量，'
                                                          '有问题就修改后再运行；全部没问题再 finish。'})
                elif fn == 'finish':
                    text = '任务结束。'
                    ses.done = True
                    print(C('96', '\n=== Qwen 说完成了 ===\n') + args.get('summary', ''))
                    ses.log({'finish': args.get('summary', '')})
                elif fn in ('list_files', 'read_file', 'write_model', 'edit_model'):
                    text = getattr(ses, fn)(**args)
                else:
                    text = f'没有叫 {fn} 的工具'
            except TypeError as e:
                text = f'工具参数不对：{e}'
            except Exception as e:
                text = f'工具出错：{e}'
            shown = text.splitlines()
            if len(shown) > 25:
                shown = shown[:25] + [f'……（共 {len(shown)} 行，完整内容在 chat.jsonl）']
            print(C('90', '  ' + '\n  '.join(shown)))
            messages.append({'role': 'tool', 'content': text, 'tool_name': fn})
            ses.log({'tool': fn, 'args': args, 'result': text})
        messages.extend(image_msgs)
        if ses.done:
            break
        strip_old_images(messages)
        if est_tokens(messages) > NUM_CTX * 0.55:
            print(C('90', '  [上下文快满了，折叠旧内容]'))
            compact(messages)
    else:
        print(C('93', f'\n达到最大步数 {MAX_STEPS}，停止。'))

    print(C('96', f'\n全部记录在：{ses.dir}'))
    if ses.last_blend:
        print(f'最后一次的模型：{ses.last_blend}')
        a = input('输入 o 回车 = 用 Blender 打开看看；直接回车 = 退出：').strip().lower()
        if a == 'o':
            subprocess.Popen([BLENDER, ses.last_blend])


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n已中断。')
