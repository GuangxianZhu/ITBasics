"""3D 水槽场景要显示的状态（纯函数，ui 只照着设）"""


def scene_state(ctrl) -> dict:
    plc, tank = ctrl.plc, ctrl.tank
    return {
        "level": tank.level,
        "inlet_open": bool(plc.output("Y0")),
        "drain_open": bool(plc.output("Y1")),
        "lamp_on": bool(plc.output("Y2")),
        "x2_on": bool(plc.get("X2")),
        "x3_on": bool(plc.get("X3")),
        "overflow": bool(tank.overflow),
        "level_text": f"水位 {tank.level:.1f}%",
    }
