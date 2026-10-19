# -*- coding: utf-8 -*-
"""
打开 train.blend 时由 启动.bat 一起加载：在 3D 视图右侧 N 面板里加一个「电车」页。
  - 开门 / 关门（1.5 秒的动画）、选哪一侧开
  - 车内灯、前照灯/尾灯、白天/夜晚
  - 视角：外观 / 侧面 / 车头 / 车内 / 驾驶室 / 转向架
不加载这个脚本也能用：选中 Train_Controls 空物体，在「物体属性 → 自定义属性」里直接改数值。
"""
import bpy

CTRL = 'Train_Controls'
_anim = {'target': None}


def ctrl():
    return bpy.data.objects.get(CTRL)


def _refresh():
    c = ctrl()
    if c is None:
        return
    c.update_tag()
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            area.tag_redraw()


def _door_step():
    c, t = ctrl(), _anim['target']
    if c is None or t is None:
        return None
    v = float(c['door_open'])
    v = min(t, v + 0.028) if t > v else max(t, v - 0.028)
    c['door_open'] = v
    _refresh()
    if v == t:
        _anim['target'] = None
        return None
    return 0.02


class TRAIN_OT_door(bpy.types.Operator):
    bl_idname = 'train.door'
    bl_label = '开关车门'
    open: bpy.props.BoolProperty(default=True)

    def execute(self, ctx):
        if ctrl() is None:
            self.report({'ERROR'}, '找不到 Train_Controls')
            return {'CANCELLED'}
        _anim['target'] = 1.0 if self.open else 0.0
        if not bpy.app.timers.is_registered(_door_step):
            bpy.app.timers.register(_door_step, first_interval=0.02)
        return {'FINISHED'}


class TRAIN_OT_side(bpy.types.Operator):
    bl_idname = 'train.side'
    bl_label = '开门侧'
    side: bpy.props.StringProperty(default='R')

    def execute(self, ctx):
        c = ctrl()
        c['door_left'] = 1 if self.side in ('L', 'B') else 0
        c['door_right'] = 1 if self.side in ('R', 'B') else 0
        _refresh()
        return {'FINISHED'}


class TRAIN_OT_toggle(bpy.types.Operator):
    bl_idname = 'train.toggle'
    bl_label = '切换'
    prop: bpy.props.StringProperty()

    def execute(self, ctx):
        c = ctrl()
        v = c[self.prop]
        c[self.prop] = (0.0 if v > 0.5 else 1.0) if isinstance(v, float) else (0 if v else 1)
        _refresh()
        return {'FINISHED'}


class TRAIN_OT_view(bpy.types.Operator):
    bl_idname = 'train.view'
    bl_label = '视角'
    cam: bpy.props.StringProperty()

    def execute(self, ctx):
        cam = bpy.data.objects.get(self.cam)
        if cam is None:
            return {'CANCELLED'}
        ctx.scene.camera = cam
        for area in ctx.screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.region_3d.view_perspective = 'CAMERA'
        return {'FINISHED'}


class TRAIN_PT_panel(bpy.types.Panel):
    bl_label = 'E235 电车'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = '电车'

    def draw(self, ctx):
        c = ctrl()
        L = self.layout
        if c is None:
            L.label(text='这个文件里没有 Train_Controls')
            return
        b = L.box()
        b.label(text='车门')
        r = b.row(align=True)
        r.operator('train.door', text='开门').open = True
        r.operator('train.door', text='关门').open = False
        b.prop(c, '["door_open"]', text='开度', slider=True)
        r = b.row(align=True)
        side = 'B' if c['door_left'] and c['door_right'] else ('L' if c['door_left'] else 'R')
        for key, label in (('R', '右侧·站台'), ('L', '左侧'), ('B', '两侧')):
            r.operator('train.side', text=label, depress=(side == key)).side = key

        b = L.box()
        b.label(text='灯光')
        r = b.row(align=True)
        r.operator('train.toggle', text='车内灯 开' if c['lights'] > 0.5 else '车内灯 关', depress=c['lights'] > 0.5).prop = 'lights'
        r.operator('train.toggle', text='前照灯' if c['headlight'] else '尾灯', depress=bool(c['headlight'])).prop = 'headlight'
        b.operator('train.toggle', text='夜晚' if c['night'] > 0.5 else '白天', depress=c['night'] > 0.5).prop = 'night'

        b = L.box()
        b.label(text='视角（相机）')
        g = b.grid_flow(columns=2, align=True)
        for cam, label in (('Cam_Exterior', '外观'), ('Cam_Side', '侧面'), ('Cam_Front', '车头'),
                           ('Cam_Interior', '车内'), ('Cam_Cab', '驾驶室'), ('Cam_Under', '转向架')):
            g.operator('train.view', text=label).cam = cam
        L.label(text='视图里按 Z 可切换着色方式')


CLASSES = (TRAIN_OT_door, TRAIN_OT_side, TRAIN_OT_toggle, TRAIN_OT_view, TRAIN_PT_panel)


def _setup_view():
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type == 'VIEW_3D':
                    sp = area.spaces.active
                    sp.shading.type = 'RENDERED'
                    sp.show_region_ui = True
                    sp.region_3d.view_perspective = 'CAMERA'
                    sp.clip_start = 0.05
                    sp.clip_end = 500
    except Exception as e:
        print('[train_ui] view setup skipped:', e)
    return None


def register():
    for cls in CLASSES:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            bpy.utils.unregister_class(cls)
            bpy.utils.register_class(cls)
    bpy.app.timers.register(_setup_view, first_interval=0.5)


if __name__ == '__main__':
    register()
