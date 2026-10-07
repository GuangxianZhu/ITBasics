"""生成虚构的示例 Excel（与实际设备无关），用于试跑查询器。

用法:  python make_sample.py        → 在 sample_data/ 下生成 4 个 Excel
"""
from pathlib import Path
import pandas as pd

OUT = Path(__file__).parent / "sample_data"


def main():
    OUT.mkdir(exist_ok=True)

    # 地址符号：符号 → 各机台地址（机台C 故意缺一个地址）
    symbols = pd.DataFrame([
        ["TANK1_LV_H",  "1号槽 液位上限",   "DI", "X0100", "X0100", "X0200"],
        ["TANK1_LV_L",  "1号槽 液位下限",   "DI", "X0101", "X0101", "X0201"],
        ["TANK1_TEMP",  "1号槽 温度",       "AI", "D1000", "D1000", "D2000"],
        ["PUMP1_RUN",   "1号泵 运转指令",   "DO", "Y0010", "Y0012", "Y0010"],
        ["PUMP1_FB",    "1号泵 运转反馈",   "DI", "X0110", "X0112", "X0210"],
        ["VALVE_IN1",   "进液阀1 开指令",   "DO", "Y0020", "Y0020", "Y0030"],
        ["VALVE_IN1_OP","进液阀1 开到位",   "DI", "X0120", "X0120", "X0220"],
        ["FLOW1",       "1号流量计",        "AI", "D1010", "D1010", "D2010"],
        ["HEATER1_ON",  "1号加热器 开",     "DO", "Y0030", "Y0030", ""],
        ["SPARE_01",    "预留",             "DI", "X0199", "X0199", "X0299"],  # 故意没人用
    ], columns=["符号", "说明", "类型", "机台A", "机台B", "机台C"])

    # 报警：分两页，演示多 sheet 读取（A-108 故意引用不存在的符号）
    alarm_heavy = pd.DataFrame([
        ["A-101", "1号槽 液位过高",     "TANK1_LV_H",            "P-01", "重"],
        ["A-102", "1号槽 液位过低",     "TANK1_LV_L",            "P-02", "重"],
        ["A-103", "1号泵 运转异常",     "PUMP1_RUN, PUMP1_FB",   "P-03", "重"],
        ["A-104", "1号槽 温度过高",     "TANK1_TEMP, HEATER1_ON","P-04", "重"],
    ], columns=["报警号", "报警内容", "触发符号", "相关参数", "等级"])
    alarm_light = pd.DataFrame([
        ["A-105", "进液阀1 开超时",     "VALVE_IN1, VALVE_IN1_OP", "P-05", "轻"],
        ["A-106", "1号流量 偏低",       "FLOW1",                   "P-06", "轻"],
        ["A-107", "1号槽 补液超时",     "VALVE_IN1, TANK1_LV_L",   "P-05", "轻"],
        ["A-108", "2号泵 运转异常",     "PUMP2_FB",                "",     "轻"],
    ], columns=alarm_heavy.columns)

    params = pd.DataFrame([
        ["P-01", "液位上限 判定延时", "2",   "s",   "0~10",  "TANK1_LV_H"],
        ["P-02", "液位下限 判定延时", "2",   "s",   "0~10",  "TANK1_LV_L"],
        ["P-03", "泵反馈 等待时间",   "3",   "s",   "1~10",  "PUMP1_RUN、PUMP1_FB"],
        ["P-04", "温度上限",          "80",  "℃",  "20~90", "TANK1_TEMP"],
        ["P-05", "进液阀 开超时",     "15",  "s",   "5~60",  "VALVE_IN1"],
        ["P-06", "流量下限",          "5.0", "L/min","0~20", "FLOW1"],
        ["P-07", "加热器 最长连续时间","600", "s",  "0~3600","HEATER1_ON"],
    ], columns=["参数号", "参数名", "设定值", "单位", "范围", "相关符号"])

    configs = pd.DataFrame([
        ["CFG-HEATER", "有", "是否装有加热器",   "A-104",        "HEATER1_ON"],
        ["CFG-FLOW",   "有", "是否装有流量计",   "A-106",        "FLOW1"],
        ["CFG-AUTOFILL","无","是否启用自动补液", "A-105, A-107", "VALVE_IN1"],
    ], columns=["配置项", "设定值", "说明", "关联报警", "关联符号"])

    symbols.to_excel(OUT / "地址符号.xlsx", index=False)
    with pd.ExcelWriter(OUT / "报警.xlsx") as w:
        alarm_heavy.to_excel(w, sheet_name="重故障", index=False)
        alarm_light.to_excel(w, sheet_name="轻故障", index=False)
    params.to_excel(OUT / "参数.xlsx", index=False)
    configs.to_excel(OUT / "固定配置.xlsx", index=False)
    print(f"已生成示例数据: {OUT}")


if __name__ == "__main__":
    main()
