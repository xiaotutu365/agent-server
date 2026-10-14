"""自定义业务工具（示例：计算器、单位换算）。"""

from langchain_core.tools import tool


@tool
def calculator(expression: str) -> str:
    """计算数学表达式。支持 + - * / ** // % 与括号，以及 math 模块函数（如 sqrt、sin）。
    示例: calculator("2 ** 10 + sqrt(144)")"""
    import math

    allowed = {k: v for k, v in vars(math).items() if not k.startswith("_")}
    try:
        result = eval(expression, {"__builtins__": {}}, allowed)  # noqa: S307
        return f"{expression} = {result}"
    except Exception as exc:  # noqa: BLE001
        return f"计算失败: {exc}"


@tool
def unit_convert(value: float, from_unit: str, to_unit: str) -> str:
    """单位换算。支持长度(m/km/ft/mi/in)、重量(kg/g/lb/oz)、温度(c/f/k)。
    示例: unit_convert(100, "c", "f")"""
    f, t = from_unit.lower().strip(), to_unit.lower().strip()

    length = {"m": 1.0, "km": 1000.0, "cm": 0.01, "mm": 0.001,
              "ft": 0.3048, "mi": 1609.344, "in": 0.0254}
    weight = {"kg": 1.0, "g": 0.001, "mg": 1e-6, "lb": 0.45359237, "oz": 0.028349523}

    if f == t:
        return f"{value} {from_unit} = {value} {to_unit}"

    if f in length and t in length:
        return f"{value} {from_unit} = {value * length[f] / length[t]:.6f} {to_unit}"
    if f in weight and t in weight:
        return f"{value} {from_unit} = {value * weight[f] / weight[t]:.6f} {to_unit}"

    if {f, t} <= {"c", "f", "k"}:
        def to_c(x: float, u: str) -> float:
            return x if u == "c" else (x - 32) * 5 / 9 if u == "f" else x - 273.15
        def from_c(x: float, u: str) -> float:
            return x if u == "c" else x * 9 / 5 + 32 if u == "f" else x + 273.15
        return f"{value} {from_unit} = {from_c(to_c(value, f), t):.4f} {to_unit}"

    return f"不支持的换算: {from_unit} -> {to_unit}"


CUSTOM_TOOLS = [calculator, unit_convert]
