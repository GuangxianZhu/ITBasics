# 统一查询器

报警 / 参数 / 固定配置 / 地址符号 四种 Excel 联动查询。需求见 [需求与用例.md](需求与用例.md)。

## 文件
| 文件 | 作用 |
|---|---|
| `make_sample.py` | 生成虚构示例数据到 `sample_data/` |
| `core.py` | 读取、建立关系、查询、一致性检查（**适配实际文件只改这里开头的设置**） |
| `app.py` | 窗口界面 + 命令行 |

## 运行
```
pip install pandas openpyxl
python app.py                      # 用示例数据打开窗口
python app.py D:\真实文件夹         # 用实际文件
python app.py --cli A-103          # 命令行查询
python app.py --check              # 一致性检查
```
输入框可以填：报警号、符号、地址、参数号、配置项，或任意关键字（模糊搜索）。

## 换成实际文件
把 `core.py` 和一份实际 Excel 交给 Copilot：
> 「把 core.py 开头的 FILES 设置改成和这些 Excel 的实际列名对应，其他逻辑不要改。」

列名不对时，程序会直接提示缺了哪一列。
