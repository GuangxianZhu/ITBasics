# 代码提取工具（大代码喂给 AI 用）

9 万行、几 MB 的 `.cpp` 不可能整个交给 Copilot 读。这个工具反过来做：**先给 AI 一份函数目录，再只提取它需要的几个函数或几段代码**，每次拖给 AI 的都是一个小 txt。

只用 Python 标准库，不用 pip 安装任何东西。

## 准备

把 `code_tool.py` 和 `run_code_tool.bat` 放进代码的根目录（和 `目录结构扫描` 的两个文件放在一起也可以）。结果都输出到根目录下的 `_ai_out\` 文件夹，不会改动源代码。

## 用法

双击 `run_code_tool.bat`，出现菜单：

| 选项 | 作用 | 输出 |
|---|---|---|
| 1 | 生成函数目录：所有 C/C++ 文件里的类和函数，带行号范围 | `code_index.txt` |
| 2 | 按函数名提取整个函数（可以一次输入多个，空格分隔） | `extract_func.txt` |
| 3 | 按关键词提取：命中的行及前后 N 行，输入 `f` 则提取所在的整个函数 | `extract_grep.txt` |
| 4 | 合并文件：把文件或文件夹**拖到 bat 上**，合并成一个 txt | `merged_files.txt` |

所有输出都带原始行号，关键词命中的行前面有 `>`，每段代码上方都标着文件路径、行号范围和所在函数，AI 回答时能指出具体位置。

## 推荐流程

1. 选 1，生成 `code_index.txt`，和 `file_structure.txt` 一起拖给 Copilot，说明要查的问题，让它列出需要看的函数名
2. 选 2，输入这些函数名，把 `extract_func.txt` 拖给 Copilot
3. 查报警或变量时选 3，比如输入报警符号，上下文填 `f`，得到所有用到它的函数

## 输出示例

函数目录：

```
## src/OnbTank.cpp  (90123 lines, 3.1 MB)
L 1203-1288   func   int COnbTank::FillStart(int mode)  [86 lines]
L 1290-1410   func   bool COnbTank::CheckLevel(void)  [121 lines]
```

关键词提取：

```
===== FILE: src/OnbTank.cpp  L1270-L1290  in: COnbTank::FillStart =====
 1270 |     if (mode == 1) {
>1271 |         RaiseAlarm(ALARM_ONB_LEVEL_HIGH);
 1272 |     }
```

## 注意

- 函数识别是按代码格式推断的，没有用编译器：`#if/#ifdef ... #else` 只按第一个分支解析，`#if 0` 跳过。宏写得特殊的地方可能漏掉个别函数；某个文件括号对不上时，目录里会标 `!` 提醒。
- 关键词默认区分大小写，菜单里可以选择忽略大小写。
- 编码自动判断（UTF-8 / Shift-JIS），输出统一为 UTF-8，记事本打开不乱码。
- 输出超过 3000 行时会提示：AI 可能读不完，请换更具体的关键词或减少上下文行数。
- 3 MB 的文件生成目录也只要零点几秒；不过函数很多时目录本身也会有几千行，可以只拖相关模块的部分。
- 也可以用命令行：`py code_tool.py grep ALARM_ONB -f`，`py code_tool.py func FillStart CheckLevel`。
