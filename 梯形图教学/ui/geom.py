"""程序生成的简单几何体（顶点色带明暗，不依赖光照）"""
import math
from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat,
                          GeomVertexWriter, NodePath)

# 面明暗：顶、底、四个侧面
_SHADE = {"top": 1.0, "bottom": 0.5, "s0": 0.8, "s1": 0.65, "s2": 0.75, "s3": 0.6}


def _make(name, quads):
    """quads: [(shade, [p0,p1,p2,p3])]"""
    vd = GeomVertexData(name, GeomVertexFormat.getV3c4(), Geom.UHStatic)
    vw, cw = GeomVertexWriter(vd, "vertex"), GeomVertexWriter(vd, "color")
    tris = GeomTriangles(Geom.UHStatic)
    n = 0
    for shade, pts in quads:
        for p in pts:
            vw.addData3(*p)
            cw.addData4(shade, shade, shade, 1)
        tris.addVertices(n, n + 1, n + 2)
        tris.addVertices(n, n + 2, n + 3)
        n += 4
    g = Geom(vd)
    g.addPrimitive(tris)
    gn = GeomNode(name)
    gn.addGeom(g)
    np_ = NodePath(gn)
    np_.setTwoSided(True)
    np_.setLightOff()
    return np_


def make_box(x1, x2, y1, y2, z1, z2, name="box"):
    p = lambda x, y, z: (x, y, z)
    quads = [
        (_SHADE["top"], [p(x1, y1, z2), p(x2, y1, z2), p(x2, y2, z2), p(x1, y2, z2)]),
        (_SHADE["bottom"], [p(x1, y1, z1), p(x1, y2, z1), p(x2, y2, z1), p(x2, y1, z1)]),
        (_SHADE["s0"], [p(x1, y1, z1), p(x2, y1, z1), p(x2, y1, z2), p(x1, y1, z2)]),
        (_SHADE["s1"], [p(x2, y1, z1), p(x2, y2, z1), p(x2, y2, z2), p(x2, y1, z2)]),
        (_SHADE["s2"], [p(x2, y2, z1), p(x1, y2, z1), p(x1, y2, z2), p(x2, y2, z2)]),
        (_SHADE["s3"], [p(x1, y2, z1), p(x1, y1, z1), p(x1, y1, z2), p(x1, y2, z2)]),
    ]
    return _make(name, quads)


def make_cylinder(radius, z1, z2, segments=24, cx=0.0, cy=0.0, name="cyl"):
    quads = []
    for i in range(segments):
        a0, a1 = 2 * math.pi * i / segments, 2 * math.pi * (i + 1) / segments
        x0, y0 = cx + radius * math.cos(a0), cy + radius * math.sin(a0)
        x1, y1 = cx + radius * math.cos(a1), cy + radius * math.sin(a1)
        shade = 0.6 + 0.4 * (0.5 + 0.5 * math.cos((a0 + a1) / 2 - 0.8))
        quads.append((shade, [(x0, y0, z1), (x1, y1, z1), (x1, y1, z2), (x0, y0, z2)]))
    return _make(name, quads)
