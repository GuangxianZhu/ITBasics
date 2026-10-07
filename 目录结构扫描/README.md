# 目录结构扫描

扫描当前目录，把所有文件按"每行一个完整相对路径"写进 `file_structure.txt`，方便拖给 AI 看。Windows 一键运行，无需安装任何东西。

## 用法

1. 把 `scan_tree.ps1` 和 `run_scan_tree.bat` 一起放进要扫描的目录
2. 双击 `run_scan_tree.bat`
3. 同目录下生成 `file_structure.txt`，拖代码给 AI 时一起拖进去

也可以指定其它目录：

```
powershell -ExecutionPolicy Bypass -File scan_tree.ps1 -Root D:\some\folder
```

## 输出示例

```
Root: D:\work\ONB_check
Generated: 2026-10-08 09:05:12
Excluded: .git, node_modules, __pycache__, .vs, .idea, .venv, venv
Total: 2 folders, 5 files. One relative path per line; a trailing / marks an empty folder.

config.ini
docs/仕様メモ.md
docs/报警一览.xlsx
main.py
scripts/check_report.vbs
scripts/common.vbs
```

## 说明

- 每行都是完整相对路径（用 `/` 分隔），不用靠缩进判断层级，AI 不容易把文件归错文件夹
- 只列文件；空文件夹会列出来，末尾带 `/`
- 默认跳过 `.git`、`node_modules`、`__pycache__` 等，在 `scan_tree.ps1` 里改 `$Exclude` 即可
- 不跟随符号链接/联接点，避免死循环
- 输出为带 BOM 的 UTF-8，记事本直接打开中日文文件名不会乱码
- 只用 Windows 自带的 PowerShell 5.1，工作 PC 可直接用
