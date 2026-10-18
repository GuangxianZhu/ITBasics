import unreal
B = "/Game/XRFramework/Blueprints/WBP_Menu.WBP_Menu:WidgetTree."
src_btn = unreal.load_object(None, B + "ResetOrientationButton")
src_txt = unreal.load_object(None, B + "Text_ResetOrientationButton")
src_slot = src_btn.get_editor_property("slot")
src_bslot = src_txt.get_editor_property("slot")
for btn_name, txt_name, label in [("TimeButton", "Text_TimeButton", u"时间：黄昏"), ("TurnButton", "Text_TurnButton", u"转向：45°")]:
    b = unreal.load_object(None, B + btn_name)
    t = unreal.load_object(None, B + txt_name)
    for p in ("widget_style", "click_method", "touch_method", "press_method", "is_focusable", "color_and_opacity", "background_color"):
        try: b.set_editor_property(p, src_btn.get_editor_property(p))
        except Exception as e: print("btn", p, e)
    s = b.get_editor_property("slot")
    for p in ("padding", "size", "horizontal_alignment", "vertical_alignment"):
        try: s.set_editor_property(p, src_slot.get_editor_property(p))
        except Exception as e: print("slot", p, e)
    bs = t.get_editor_property("slot")
    for p in ("padding", "horizontal_alignment", "vertical_alignment"):
        try: bs.set_editor_property(p, src_bslot.get_editor_property(p))
        except Exception as e: print("bslot", p, e)
    for p in ("color_and_opacity", "font", "justification", "shadow_offset", "shadow_color_and_opacity"):
        try: t.set_editor_property(p, src_txt.get_editor_property(p))
        except Exception as e: print("txt", p, e)
    t.set_editor_property("text", unreal.Text(label))
    print(btn_name, "ok", t.get_editor_property("text"), s.get_editor_property("size"))
f = src_txt.get_editor_property("font")
print("font", f.get_editor_property("font_object"), f.get_editor_property("size"), f.get_editor_property("typeface_font_name"))
wbp = unreal.load_asset("/Game/XRFramework/Blueprints/WBP_Menu")
wbp.modify()
