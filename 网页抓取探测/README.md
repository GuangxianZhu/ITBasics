# 网页抓取探测 (fetch_html.py)

抓一个内网网页，保存原始 HTML，并输出"这个页面是怎么做的"：
表格、表单、frame 子页面、脚本里的疑似数据接口、站内链接、是否 ASP.NET WebForms 等。

## 准备
```
pip install requests beautifulsoup4
pip install requests-negotiate-sspi   # 用 Windows 账号自动登录的系统需要
```

## 运行
```
python fetch_html.py                     # 运行后输入网址
python fetch_html.py 网址
python fetch_html.py 网址 --no-proxy     # 内网地址被公司代理挡住时
python fetch_html.py 网址 --auth ntlm    # 自动登录不行时，手动输入 域\用户名 和密码
```
登录方式默认 auto：先不登录试，返回 401 再用当前 Windows 身份。

## 结果（probe_<主机名>_<时间>/）
- page.html：原始 HTML
- summary.txt：结构摘要（和屏幕输出一样）
- table_N.csv：页面表格，Excel 直接打开
- headers.json：响应头

## 看结果的顺序
1. "页面类型推测"：先判断数据在哪
   - 有表格 → 直接看 table_N.csv
   - 有 frame/iframe → 数据在子页面，把子页面地址再跑一次
   - 正文几乎为空 → 数据是 JS 加载的，浏览器 F12 → Network 找请求
   - WebForms（__VIEWSTATE）→ 翻页/搜索要回发，下一步再写
2. "疑似数据接口"：有的话直接用本脚本请求那个地址，可能返回 JSON

只做 GET 读取，不提交表单。别短时间反复大量运行。网址、结果文件不要提交到本仓库。
