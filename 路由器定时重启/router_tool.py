# -*- coding: utf-8 -*-
"""
路由器定时重启工具（Buffalo WSR-5400XE6）

  python router_tool.py              交互菜单（启动.bat 打开的就是这个）
  python router_tool.py --check      只测试登录，不重启
  python router_tool.py --reboot-now 立即重启（会再确认一次；加 --yes 跳过确认）
  python router_tool.py --scheduled  给 Windows 任务计划程序用：凌晨自动重启
"""
import argparse
import base64
import configparser
import datetime as dt
import getpass
import os
import subprocess
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.ini")
LOG_DIR = os.path.join(HERE, "logs")
LOG_FILE = os.path.join(LOG_DIR, "reboot.log")
DEBUG_DIR = os.path.join(HERE, "debug")
TASK_NAME = "BuffaloRouterNightlyReboot"


# ====================== 日志 ======================
def log(msg):
    line = "%s  %s" % (dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        print(line)
    except Exception:
        pass   # pythonw has no console
    os.makedirs(LOG_DIR, exist_ok=True)
    try:   # keep the log small: when > 200 KB, keep the newest half
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 200_000:
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                data = f.read()
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write(data[len(data) // 2:])
    except OSError:
        pass
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ====================== 密码加密保存（Windows DPAPI） ======================
# DPAPI 用「当前 Windows 账号」的密钥加密：同一账号（包括它跑的计划任务）能解开，
# 把 config.ini 拷到别的电脑或别的账号就解不开。不需要你再记一个主密码。
def _dpapi(data, protect):
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    inp = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = BLOB()
    crypt32 = ctypes.windll.crypt32
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    CRYPTPROTECT_UI_FORBIDDEN = 0x1
    if not fn(ctypes.byref(inp), None, None, None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
        raise OSError("DPAPI 失败（换了 Windows 账号或电脑？请在菜单里重新设置密码）")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def seal(pw):
    raw = pw.encode("utf-8")
    if os.name == "nt":
        return "dpapi:" + base64.b64encode(_dpapi(raw, True)).decode()
    return "plain:" + base64.b64encode(raw).decode()   # non-Windows (testing only)


def unseal(s):
    kind, _, b = s.partition(":")
    raw = base64.b64decode(b)
    if kind == "dpapi":
        return _dpapi(raw, False).decode("utf-8")
    return raw.decode("utf-8")


# ====================== 配置 ======================
def load_config():
    cp = configparser.ConfigParser()
    if os.path.exists(CONFIG):
        cp.read(CONFIG, encoding="utf-8")
    if not cp.has_section("router"):
        cp.add_section("router")
    if not cp.has_section("schedule"):
        cp.add_section("schedule")
    r, s = cp["router"], cp["schedule"]
    r.setdefault("host", "192.168.11.1")
    r.setdefault("username", "admin")
    r.setdefault("password", "")
    s.setdefault("time", "04:00")
    s.setdefault("window_minutes", "90")
    return cp


def save_config(cp):
    with open(CONFIG, "w", encoding="utf-8") as f:
        f.write("; 由 router_tool.py 生成。password 已用 Windows 账号加密，不是明文。\n")
        f.write("; 这个文件已在 .gitignore 里，不会被推到 GitHub。\n")
        cp.write(f)


def setup_credentials(cp):
    r = cp["router"]
    print("\n—— 设置路由器登录信息（直接回车 = 用括号里的默认值）——")
    v = input("路由器地址 [%s]: " % r["host"]).strip()
    if v:
        r["host"] = v
    v = input("用户名 [%s]: " % r["username"]).strip()
    if v:
        r["username"] = v
    while True:
        pw = getpass.getpass("密码（输入时不显示）: ")
        if pw:
            break
        print("密码不能为空。")
    r["password"] = seal(pw)
    save_config(cp)
    print("已保存到 config.ini（密码已加密）。")


def make_router(cp):
    from buffalo_client import BuffaloRouter
    r = cp["router"]
    if not r.get("password"):
        raise SystemExit("还没设置密码：请先在菜单里选「重新设置账号密码」。")
    return BuffaloRouter(r["host"], r["username"], unseal(r["password"]), debug_dir=DEBUG_DIR, log=log)


# ====================== 动作 ======================
def do_check(cp):
    from buffalo_client import RouterError
    rt = make_router(cp)
    log("测试登录 %s ..." % rt.host)
    try:
        rt.login()
        log("OK：登录成功，找到了重启表单。（测试模式，没有重启）")
        return True
    except RouterError as e:
        log("失败：%s" % e)
        return False
    except Exception as e:
        log("失败（连不上路由器？）：%r" % e)
        return False
    finally:
        rt.logout()


def do_reboot(cp, reason):
    from buffalo_client import RouterError, wait_reboot_cycle, internet_ok
    rt = make_router(cp)
    log("==== 开始重启（%s）路由器 %s ====" % (reason, rt.host))
    log("重启前外网：%s" % ("通" if internet_ok() else "不通"))
    try:
        rt.login()
        log("登录成功，发送重启请求 ...")
        rt.reboot()
    except RouterError as e:
        log("失败：%s" % e)
        return False
    except Exception as e:
        log("失败：%r" % e)
        return False
    log("已发送。等路由器掉线再上线（一般 1~3 分钟）...")
    secs = wait_reboot_cycle(rt.host, log=log)
    if secs is None:
        log("警告：7 分钟内路由器没回来，请人工看一下。")
        return False
    log("路由器已恢复（约 %d 秒）。" % secs)
    # 管理页面先起来，外网（PPPoE/IPv6）通常还要再等一会儿
    import time
    for _ in range(20):
        if internet_ok():
            log("外网已恢复。==== 完成 ====")
            return True
        time.sleep(6)
    log("警告：路由器回来了，但 2 分钟内外网还没通。")
    return False


def in_window(cp, now=None):
    """计划任务防呆：只有在设定时间之后 window_minutes 分钟内才真的重启。
    防止电脑白天开机时「补跑」错过的任务，大白天把网断掉。"""
    now = now or dt.datetime.now()
    hh, mm = [int(x) for x in cp["schedule"]["time"].split(":")]
    start = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if start > now:
        start -= dt.timedelta(days=1)
    return (now - start) <= dt.timedelta(minutes=int(cp["schedule"]["window_minutes"]))


def do_scheduled(cp):
    if not in_window(cp):
        log("计划任务被触发，但现在 %s 不在允许时间窗（%s 起 %s 分钟内），跳过。"
            % (dt.datetime.now().strftime("%H:%M"), cp["schedule"]["time"], cp["schedule"]["window_minutes"]))
        return True
    return do_reboot(cp, "每日定时")


# ====================== Windows 计划任务 ======================
def _powershell(script):
    enc = base64.b64encode(script.encode("utf-16-le")).decode()
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                           "-EncodedCommand", enc], capture_output=True, text=True)


def _ps_quote(s):
    return "'" + s.replace("'", "''") + "'"


def install_task(cp):
    if os.name != "nt":
        print("只能在 Windows 上安装计划任务。")
        return
    t = input("每天几点重启？格式 HH:MM [%s]: " % cp["schedule"]["time"]).strip() or cp["schedule"]["time"]
    try:
        dt.datetime.strptime(t, "%H:%M")
    except ValueError:
        print("时间格式不对，例：04:00")
        return
    cp["schedule"]["time"] = t
    save_config(cp)

    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    script = os.path.join(HERE, "router_tool.py")
    ps = f"""
$ErrorActionPreference = 'Stop'
$act = New-ScheduledTaskAction -Execute {_ps_quote(pyw)} -Argument {_ps_quote('"' + script + '" --scheduled')} -WorkingDirectory {_ps_quote(HERE)}
$trg = New-ScheduledTaskTrigger -Daily -At {_ps_quote(t)}
$set = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
Register-ScheduledTask -TaskName {_ps_quote(TASK_NAME)} -Action $act -Trigger $trg -Settings $set -Description 'Daily reboot of Buffalo router (ITBasics/路由器定时重启)' -Force | Out-Null
'OK'
"""
    r = _powershell(ps)
    if "OK" in r.stdout:
        print("\n已设置：每天 %s 自动重启路由器（任务名 %s）。" % (t, TASK_NAME))
        print("前提：那个时间这台电脑开着、并且你的 Windows 账号是登录状态（锁屏也可以）。")
        print("结果会写进 logs\\reboot.log，可在菜单 5 查看。")
        log("安装计划任务：每天 %s" % t)
    else:
        print("安装失败：\n" + (r.stderr or r.stdout))


def remove_task():
    if os.name != "nt":
        print("只能在 Windows 上操作计划任务。")
        return
    r = _powershell(f"Unregister-ScheduledTask -TaskName {_ps_quote(TASK_NAME)} -Confirm:$false; 'OK'")
    print("已取消每日自动重启。" if "OK" in r.stdout else "取消失败（可能本来就没装）：\n" + r.stderr)
    log("删除计划任务")


def task_status():
    if os.name != "nt":
        return "（非 Windows）"
    r = _powershell(f"$t = Get-ScheduledTask -TaskName {_ps_quote(TASK_NAME)} -ErrorAction SilentlyContinue; "
                    "if ($t) { $i = $t | Get-ScheduledTaskInfo; 'ON ' + $i.NextRunTime.ToString('yyyy-MM-dd HH:mm') } else { 'OFF' }")
    out = r.stdout.strip()
    if out.startswith("ON"):
        return "已开启，下次运行 " + out[3:]
    return "未开启"


def show_log(n=30):
    if not os.path.exists(LOG_FILE):
        print("还没有日志。")
        return
    with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    print("".join(lines[-n:]))


# ====================== 菜单 ======================
def menu():
    cp = load_config()
    if not cp["router"].get("password"):
        print("第一次使用，先设置路由器的账号密码。")
        setup_credentials(cp)
    while True:
        print("\n========== 路由器定时重启（%s）==========" % cp["router"]["host"])
        print("  每日自动重启：%s" % task_status())
        print("  1) 测试登录（不重启，推荐先做这个）")
        print("  2) 立即重启路由器")
        print("  3) 设置/修改 每日自动重启时间")
        print("  4) 取消 每日自动重启")
        print("  5) 查看最近日志")
        print("  6) 重新设置账号密码")
        print("  0) 退出")
        c = input("请选择: ").strip()
        if c == "1":
            do_check(cp)
        elif c == "2":
            if input("确定现在重启？家里所有设备会断网 1~3 分钟 (y/N): ").strip().lower() == "y":
                do_reboot(cp, "手动")
        elif c == "3":
            install_task(cp)
        elif c == "4":
            remove_task()
        elif c == "5":
            show_log()
        elif c == "6":
            setup_credentials(cp)
        elif c == "0":
            return


def main():
    ap = argparse.ArgumentParser(description="Buffalo 路由器定时重启")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="只测试登录，不重启")
    g.add_argument("--reboot-now", action="store_true", help="立即重启")
    g.add_argument("--scheduled", action="store_true", help="计划任务模式（带时间窗防呆）")
    ap.add_argument("--yes", action="store_true", help="--reboot-now 时跳过确认")
    a = ap.parse_args()

    try:
        if a.check:
            sys.exit(0 if do_check(load_config()) else 1)
        if a.reboot_now:
            if not a.yes and input("确定现在重启？(y/N): ").strip().lower() != "y":
                return
            sys.exit(0 if do_reboot(load_config(), "命令行") else 1)
        if a.scheduled:
            sys.exit(0 if do_scheduled(load_config()) else 1)
        menu()
    except SystemExit:
        raise
    except Exception:
        log("未预料的错误：\n" + traceback.format_exc())
        sys.exit(2)


if __name__ == "__main__":
    main()
