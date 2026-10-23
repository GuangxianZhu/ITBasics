# -*- coding: utf-8 -*-
"""自查：在各个姿态下检查零件之间有没有穿模（BVH 三角形相交）。
相邻刚体（同一根手指相邻两级、掌与指根）按设计本来就贴合，跳过；其余相交都报告出来。
对指时两个硅胶指腹允许接触（软材料本来就会压缩）。
用法：python check.py   （或 blender -b --python check.py）
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import build_hand as B

ALLOW = (("thumb_tippad", "index_tippad"),)


def main():
    B.build()
    sc = bpy.context.scene
    itf = None
    total = 0
    lines = []
    for pose in ["open", "rest", "fist", "pinch", "spread"]:
        sc.frame_set(B.FRAMES[pose])
        if itf is None:
            itf = B.Interference()
        trees = itf.trees()
        hits = sorted(itf.overlaps(trees, trees, ALLOW), reverse=True)
        total += len(hits)
        lines.append("[%s] 非相邻零件相交 %d 对" % (pose, len(hits)))
        for n, a, b in hits[:10]:
            lines.append("    %4d 个三角形  %s  ×  %s" % (n, a, b))
    print("\n".join(lines))
    print("[check] %s" % ("通过：没有穿模" if total == 0 else "有 %d 处相交需要处理" % total))
    out = B.out_dir()
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "check_report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
