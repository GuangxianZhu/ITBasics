extends RefCounted
## 水的"唯一真相": 海浪参数和高度公式。
## water.gdshader 画浪（GPU），这里算同一个公式（CPU）给小船起伏、游泳浮力用 —— 两边参数都从这里来，保证船和浪对得上。
##
## 原理: Gerstner 波。每个波让水面上的点做小圆周运动（不只是上下），所以浪峰尖、浪谷平，比正弦波像真的海。
## 水深越浅，浪越小（att）；靠近岸边再叠加一个 9 秒周期的整体涨落（swash），水线就会在沙滩上来回推。

const SEA_LEVEL := -0.3
## (方向x, 方向z, 陡度, 波长m)。方向 +z = 朝岸边（Godot 里海在 -Z）
const WAVES := [
	Vector4(0.15, 1.0, 0.10, 18.0),
	Vector4(-0.35, 1.0, 0.08, 9.0),
	Vector4(0.45, 1.0, 0.06, 5.0),
	Vector4(-0.10, 1.0, 0.04, 2.6),
]
const SWASH_AMP := 0.15
const SWASH_PERIOD := 9.0
## 泳池（Godot 坐标 x 1~7, z -9~-6）
const POOL_RECT := Rect2(1.0, -9.0, 6.0, 3.0)
const POOL_WATER := 0.15
const POOL_FLOOR := -2.25


## 沙滩/海底高度: Blender 里 y 30→60 从 0 降到 -3（Godot z = -y）
static func ground_h(_x: float, z: float) -> float:
	return -3.0 * clampf((-z - 30.0) / 30.0, 0.0, 1.0)


static func _att(depth0: float) -> float:
	return smoothstep(-0.3, 2.0, depth0)


static func sea_height(x: float, z: float, t: float) -> float:
	var depth0 := SEA_LEVEL - ground_h(x, z)
	var att := _att(depth0)
	var h := 0.0
	for w in WAVES:
		var k: float = TAU / w.w
		var c: float = sqrt(9.8 / k)
		var d := Vector2(w.x, w.y).normalized()
		var f: float = k * (d.dot(Vector2(x, z)) - c * t)
		h += (w.z / k) * sin(f)
	var shore := 1.0 - smoothstep(3.0, 12.0, depth0)
	return SEA_LEVEL + h * att + SWASH_AMP * sin(TAU * t / SWASH_PERIOD) * shore


## 这个位置的水面高度；没有水返回 -INF
static func water_height(x: float, z: float, t: float) -> float:
	if POOL_RECT.has_point(Vector2(x, z)):
		return POOL_WATER
	var h := sea_height(x, z, t)
	if h > ground_h(x, z):
		return h
	return -INF


## 把波浪参数推给水面着色器
static func apply_to_shader(m: ShaderMaterial) -> void:
	m.set_shader_parameter("sea_level", SEA_LEVEL)
	m.set_shader_parameter("w1", WAVES[0])
	m.set_shader_parameter("w2", WAVES[1])
	m.set_shader_parameter("w3", WAVES[2])
	m.set_shader_parameter("w4", WAVES[3])
	m.set_shader_parameter("swash_amp", SWASH_AMP)
	m.set_shader_parameter("swash_period", SWASH_PERIOD)
	m.set_shader_parameter("pool_floor", POOL_FLOOR)
