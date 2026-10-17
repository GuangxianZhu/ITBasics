# -*- coding: utf-8 -*-
"""
Buffalo AirStation (WSR-5400XE6, firmware 1.15) web-UI client.

Reverse-engineered from the router's own pages (2026-10):

  Login  : GET  /login.html            -> page embeds an RSA public key (<textarea id="privkey">)
           POST /login.html            nosave_Username=admin
                                       nosave_encryptedPassword=<base64(RSA-PKCS1v1.5(password))>
                                       nosave_Password=        (empty hidden field)
                                       MobileDevice=0
                                       nosave_session_num=     (empty on login page)
           -> response is only "top.location = index.html" (no Set-Cookie!)
  Cookie : GET  /index.html            -> JS: var sessionID="<32 hex>"; setCookie("SessionID", ...)
                                       plus language=JP, mobile=disable. We copy these by hand.
           (without SessionID every admin page redirects to login_time.html)
  PCtime : GET  /login_time.html       -> <form name="internet_detect" action="redirect.html">
           POST /redirect.html         only used as a fallback if init.html still bounces
  Guard  : GET  /Ajax_get_value.html&action=GetMovingRestore  -> {"MovingRestoreFlag": 0|1}
           (the UI refuses to reboot while "smart moving" is restoring settings)
  Reboot : GET  /init.html             -> <form name="rebootForm"> with a one-time nosave_session_num
           POST /init.html             nosave_reboot=1 & nosave_session_num=<that number>
  Logout : GET  /logout.html

The one-time nosave_session_num works like a CSRF token: it changes on every GET of
init.html, so we must fetch the page right before posting.
"""
import base64
import json
import os
import re
import time
import socket
from html.parser import HTMLParser

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


class RouterError(Exception):
    pass


class _FormParser(HTMLParser):
    """Collects every <form> with its hidden/text inputs, plus <textarea id=privkey>."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms = []          # list of dict(name, id, fields{name: value})
        self._cur = None
        self._in_key = False
        self.pubkey = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self._cur = {"name": a.get("name", ""), "id": a.get("id", ""), "fields": {}}
            self.forms.append(self._cur)
        elif tag == "input" and self._cur is not None:
            t = (a.get("type") or "text").lower()
            name = a.get("name")
            if name and t in ("hidden", "text", "password") and "disabled" not in a:
                self._cur["fields"][name] = a.get("value", "") or ""
        elif tag == "textarea" and a.get("id") == "privkey":
            self._in_key = True

    def handle_endtag(self, tag):
        if tag == "form":
            self._cur = None
        elif tag == "textarea":
            self._in_key = False

    def handle_data(self, data):
        if self._in_key:
            self.pubkey += data


def _parse(html):
    p = _FormParser()
    p.feed(html)
    return p


def rsa_encrypt_like_jsencrypt(pem_text, password):
    """JSEncrypt.encrypt() == RSA PKCS#1 v1.5 padding, output Base64.
    The padding contains random bytes, so the result differs every call - that's expected."""
    key = serialization.load_pem_public_key(pem_text.strip().encode("ascii"))
    ct = key.encrypt(password.encode("utf-8"), padding.PKCS1v15())
    return base64.b64encode(ct).decode("ascii")


def js_date_string(now=None):
    """Same shape as JavaScript `new Date().toString()`:
    'Sat Oct 17 2026 15:31:11 GMT+0900 (Japan Standard Time)'"""
    import datetime as _dt
    now = now or _dt.datetime.now().astimezone()
    off = now.utcoffset() or _dt.timedelta(0)
    mins = int(off.total_seconds() // 60)
    sign = "+" if mins >= 0 else "-"
    mins = abs(mins)
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    name = "Japan Standard Time" if (sign, mins) == ("+", 540) else (now.tzname() or "")
    return "%s %s %02d %d %s GMT%s%02d%02d (%s)" % (
        days[now.weekday()], months[now.month - 1], now.day, now.year,
        now.strftime("%H:%M:%S"), sign, mins // 60, mins % 60, name)


class BuffaloRouter:
    def __init__(self, host, username, password, timeout=10, debug_dir=None, log=print):
        self.base = "http://" + host.strip().rstrip("/")
        self.host = host.strip()
        self.username = username
        self._password = password
        self.timeout = timeout
        self.debug_dir = debug_dir
        self.log = log
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA})
        self.s.trust_env = False   # never send LAN router traffic through a proxy

    # ---------- helpers ----------
    def _get(self, path, referer=None):
        h = {"Referer": referer} if referer else {}
        r = self.s.get(self.base + path, headers=h, timeout=self.timeout)
        r.encoding = "shift_jis"
        return r

    def _post(self, path, data, referer):
        r = self.s.post(self.base + path, data=data, headers={"Referer": referer},
                        timeout=self.timeout)
        r.encoding = "shift_jis"
        return r

    def _dump(self, name, text):
        """Save a response for troubleshooting (never contains the password)."""
        if not self.debug_dir:
            return
        os.makedirs(self.debug_dir, exist_ok=True)
        with open(os.path.join(self.debug_dir, name), "w", encoding="utf-8") as f:
            f.write(text)

    # ---------- steps ----------
    def login(self):
        r = self._get("/login.html")
        self._dump("1_login_page.html", r.text)
        page = _parse(r.text)
        if "BEGIN PUBLIC KEY" not in page.pubkey:
            raise RouterError("登录页里没找到 RSA 公钥（固件可能变了），见 debug/1_login_page.html")
        form = next((f for f in page.forms if f["id"] == "authform"), None)
        if form is None:
            raise RouterError("登录页里没找到 authform 表单（固件可能变了）")

        data = dict(form["fields"])                      # keeps any new hidden fields too
        data["nosave_Username"] = self.username
        data["nosave_encryptedPassword"] = rsa_encrypt_like_jsencrypt(page.pubkey, self._password)
        data.setdefault("nosave_Password", "")
        data.setdefault("MobileDevice", "0")

        r = self._post("/login.html", data, referer=self.base + "/login.html")
        self._dump("2_login_response.html", r.text)
        if "privkey" in r.text or "id_nosave_Password" in r.text:
            raise RouterError("登录失败：用户名或密码不对（连续失败多次路由器可能暂时锁定登录）")

        # The session cookie is NOT sent as a Set-Cookie header. The login response only says
        # "go to index.html", and index.html's JavaScript does
        #     var sessionID="<32 hex>"; setCookie("SessionID", sessionID)
        # (plus language / mobile cookies). A browser runs that script; we copy it by hand.
        idx = self._get("/index.html", referer=self.base + "/login.html")
        self._dump("2a_index.html", idx.text)
        self._adopt_js_cookies(idx.text)
        if "SessionID" not in self.s.cookies:
            raise RouterError("登录后 index.html 里没找到 sessionID（固件可能变了），见 debug/2a_index.html")

        # Verify by opening a page that needs authentication.
        init = self._get("/init.html", referer=self.base + "/index_adv.html")
        if "login_time.html" in init.text and "rebootForm" not in init.text:
            # Seen when the session is not recognised yet: the router wants the PC clock first.
            self.post_pc_time()
            init = self._get("/init.html", referer=self.base + "/index_adv.html")
        self._dump("3_init_page.html", init.text)
        if "rebootForm" in init.text:
            return init.text
        if "privkey" in init.text or "id_nosave_Password" in init.text:
            raise RouterError("登录失败：用户名或密码不对（连续失败多次路由器可能暂时锁定登录）")
        raise RouterError("登录后打不开 init.html，返回内容不认识，见 debug/3_init_page.html")

    def _adopt_js_cookies(self, html):
        domain = self.host.split(":")[0]
        m = re.search(r'var\s+sessionID\s*=\s*"([^"]+)"', html)
        if m:
            self.s.cookies.set("SessionID", m.group(1), domain=domain, path="/")
        m = re.search(r'var\s+language\s*=\s*"([^"]*)"', html)
        self.s.cookies.set("language", m.group(1) if m else "JP", domain=domain, path="/")
        m = re.search(r'var\s+mobile_enable\s*=\s*"([^"]*)"', html)
        self.s.cookies.set("mobile", "enable" if (m and m.group(1) == "1") else "disable",
                           domain=domain, path="/")

    def post_pc_time(self):
        """login_time.html: <form name="internet_detect" action="redirect.html"> with
        PageName / nosave_PCTIME (= JavaScript `new Date().toString()`) / nosave_session_num."""
        r = self._get("/login_time.html", referer=self.base + "/index.html")
        self._dump("2b_login_time.html", r.text)
        form = next((f for f in _parse(r.text).forms if f["name"] == "internet_detect"), None)
        if form is None:
            return False   # firmware without this step - nothing to do
        action = re.search(r'name="internet_detect"[^>]*action="([^"]+)"', r.text)
        path = "/" + (action.group(1) if action else "redirect.html").lstrip("/")
        data = dict(form["fields"])
        data["nosave_PCTIME"] = js_date_string()
        r2 = self._post(path, data, referer=self.base + "/login_time.html")
        self._dump("2c_after_time.html", r2.text)
        return True

    def moving_restore_busy(self):
        try:
            r = self._get("/Ajax_get_value.html&action=GetMovingRestore",
                          referer=self.base + "/init.html")
            return json.loads(r.text).get("MovingRestoreFlag") in (1, "1")
        except Exception:
            return False   # the check is advisory; the UI itself only uses it to show a message

    def reboot(self, init_html=None):
        if self.moving_restore_busy():
            raise RouterError("路由器正在「スマート引っ越し」恢复设置，按官方页面逻辑此时不能重启")
        # Always fetch a fresh page: nosave_session_num is single-use.
        init_html = self._get("/init.html", referer=self.base + "/index_adv.html").text
        form = next((f for f in _parse(init_html).forms if f["name"] == "rebootForm"), None)
        if form is None or "nosave_session_num" not in form["fields"]:
            self._dump("4_init_before_reboot.html", init_html)
            raise RouterError("没找到 rebootForm / nosave_session_num，见 debug/4_init_before_reboot.html")
        data = dict(form["fields"])
        data["nosave_reboot"] = "1"
        try:
            r = self._post("/init.html", data, referer=self.base + "/init.html")
            self._dump("5_reboot_response.html", r.text)
        except (requests.ConnectionError, requests.ReadTimeout):
            pass   # router may drop the connection as it goes down - that's success, not failure

    def logout(self):
        try:
            self._get("/logout.html", referer=self.base + "/index_adv.html")
        except Exception:
            pass


# ---------- reachability helpers ----------
def tcp_up(host, port=80, timeout=2.0):
    if ":" in host:                       # allow "192.168.11.1:8080"
        host, p = host.rsplit(":", 1)
        port = int(p)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_reboot_cycle(host, log=print, down_timeout=90, up_timeout=420):
    """Wait for the router to go DOWN, then come back UP. Returns seconds until back, or None."""
    t0 = time.time()
    went_down = False
    while time.time() - t0 < down_timeout:
        if not tcp_up(host):
            went_down = True
            break
        time.sleep(2)
    if not went_down:
        log("  注意：%d 秒内没观察到路由器掉线（可能重启太快，或重启请求没生效）" % down_timeout)
    t1 = time.time()
    while time.time() - t1 < up_timeout:
        if tcp_up(host):
            return int(time.time() - t0)
        time.sleep(3)
    return None


def internet_ok():
    for h, p in (("1.1.1.1", 443), ("8.8.8.8", 53)):
        if tcp_up(h, p, timeout=3):
            return True
    return False
