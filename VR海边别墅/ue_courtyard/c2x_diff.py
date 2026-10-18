# c2x_diff.py <旧 glb> <新 glb> : 比较两次导出的合并网格, 列出 变了的 / 消失的 / 新增的 网格名
# 用法 (局部替换流程, README 坑 31):
#   cp court_geom.glb /tmp/old.glb ; 改 c2_build.py ; python c2x_export_geom.py ; python c2x_diff.py /tmp/old.glb court_geom.glb
#   -> 把 "changed" 那几个用 python c2x_export_geom.py <名字…> 导出 court_geom_part.glb 去 UE 覆盖; "gone" 的 Actor 在 UE 里删掉
import hashlib
import sys

import numpy as np
import trimesh


def sig(path):
    s = trimesh.load(path, force="scene")
    out = {}
    for name, g in s.geometry.items():
        v = np.round(np.asarray(g.vertices), 4)
        out[name] = hashlib.md5(v.tobytes() + np.asarray(g.faces).tobytes()).hexdigest()
    return out


a, b = sig(sys.argv[1]), sig(sys.argv[2])
changed = sorted(n for n in a if n in b and a[n] != b[n])
gone = sorted(n for n in a if n not in b)
new = sorted(n for n in b if n not in a)
print("changed:", " ".join(changed))
print("gone:", " ".join(gone))
print("new:", " ".join(new))
