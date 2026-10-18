# uepy nodes.py <蓝图资产路径> <图表名> <正则> : 查当前语言下可用节点的真实名字 (DSL 要用这个名字)
# 要在 en 下查: 先 uepy lang.py en, 查完 uepy lang.py zh-Hans
import unreal, sys, re
bp = unreal.load_asset(sys.argv[1])
ge = unreal.BlueprintGraphEditor.get_graph_editor_by_name(bp, sys.argv[2])
pat = re.compile(sys.argv[3])
print("\n".join(n for n in ge.list_available_nodes([]) if pat.search(n)))
