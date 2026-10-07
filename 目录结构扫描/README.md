# 目录结构扫描

扫描当前目录的文件结构，生成树状 `file_structure.txt`。Windows 一键运行，无需安装任何东西。

## 用法

1. 把 `scan_tree.ps1` 和 `run_scan_tree.bat` 一起放进要扫描的目录
2. 双击 `run_scan_tree.bat`
3. 同目录下生成 `file_structure.txt`

也可以指定其它目录：

```
powershell -ExecutionPolicy Bypass -File scan_tree.ps1 -Root D:\some\folder
```

## 输出示例

```
Directory: D:\proj
Generated: 2026-10-08 09:00:00
Excluded : .git, node_modules, __pycache__, .vs, .idea, .venv, venv

proj/
├── docs/
│   └── a.md  (1.2 KB)
└── main.py  (3.4 KB)

1 folders, 2 files, total 4.6 KB
```

## 说明

- 文件夹排在文件前面，各自按名称排序；文件后面带大小
- 默认跳过 `.git`、`node_modules`、`__pycache__` 等，在 `scan_tree.ps1` 里改 `$Exclude` 即可
- 不跟随符号链接/联接点，避免死循环
- 输出为带 BOM 的 UTF-8，记事本直接打开中日文文件名不会乱码
- 只用 Windows 自带的 PowerShell 5.1，工作 PC 可直接用
