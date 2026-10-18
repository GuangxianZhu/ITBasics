# uepy lang.py en|zh-Hans : 切换编辑器界面语言 (不写配置, 重启后恢复)。蓝图 DSL 必须在 en 下写, 见 交接文档 坑 20
import sys, unreal
K = unreal.InternationalizationLibrary
K.set_current_language(sys.argv[1], False)
print("lang", K.get_current_language())
