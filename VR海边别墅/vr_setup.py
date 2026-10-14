# -*- coding: utf-8 -*-
"""
打开 villa.blend 时由 启动.bat 附带运行（blender villa.blend --python vr_setup.py）。
做三件事:
  1. 启用 Blender 自带的 "VR Scene Inspection" 插件，并保存到用户偏好（下次不用再勾）
  2. 把 3D 视口切到 "渲染预览 + 第一个 VR 点位的相机视角"，远裁剪调到 5km（看得到海平线）
  3. 打开右侧边栏（N 面板），里面的 "VR" 标签就是开始 VR 会话的地方
"""
import bpy
import addon_utils


def enable_vr_addon():
    try:
        loaded_default, loaded_state = addon_utils.check("viewport_vr_preview")
        if not loaded_state:
            addon_utils.enable("viewport_vr_preview", default_set=True, persistent=True)
            bpy.ops.wm.save_userpref()
            print("[vr_setup] VR Scene Inspection enabled and saved to preferences")
    except Exception as e:
        print("[vr_setup] could not enable VR addon:", e)


def setup_view():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type != "VIEW_3D":
                continue
            sp = area.spaces.active
            sp.shading.type = "RENDERED"
            sp.clip_start, sp.clip_end = 0.05, 5000
            sp.show_region_ui = True
            sp.region_3d.view_perspective = "CAMERA"
    return None  # timer 只跑一次


def deferred():
    enable_vr_addon()
    setup_view()
    return None


# 等界面完全加载后再改（启动时直接改有时 screen 还没准备好）
bpy.app.timers.register(deferred, first_interval=1.0)
