// 风: 只在顶点着色器里按正弦晃动顶点，几何体本身不变 —— 几乎零开销。
// mode 0 = 椰树叶冠（模型局部坐标，离树心越远晃得越多）
// mode 1 = 沙草（世界坐标，越高晃得越多）
// mode 2 = 窗帘（世界坐标，挂杆处不动、下摆往屋里飘；wind 由"阳台门开没开"控制）
shader_type spatial;
render_mode cull_disabled;

uniform vec3 albedo : source_color = vec3(0.13, 0.36, 0.11);
uniform float roughness_v = 0.6;
uniform float wind = 1.0;
uniform int mode = 0;
uniform float top_y = 6.1;
instance uniform float crown_r = 3.0;

void vertex() {
	vec3 wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float t = TIME;
	float ph = wp.x * 0.21 + wp.z * 0.17;
	if (mode == 0) {
		float d = clamp(length(VERTEX.xz) / crown_r, 0.0, 1.0);   // 叶冠中心就是模型原点的正上方
		float g = wind * (0.6 + 0.4 * sin(t * 0.37 + ph));
		VERTEX.y += (sin(t * 2.1 + ph + d * 2.0) * 0.10 + sin(t * 3.3 + ph * 2.0) * 0.04) * d * g;
		VERTEX.x += sin(t * 1.3 + ph) * 0.12 * d * g;
		VERTEX.z += cos(t * 1.1 + ph) * 0.09 * d * g;
	} else if (mode == 1) {
		float h = clamp(VERTEX.y / 0.7, 0.0, 1.0);
		VERTEX.x += sin(t * 1.8 + ph * 3.0) * 0.07 * h * h * wind;
		VERTEX.z += cos(t * 1.5 + ph * 2.0) * 0.05 * h * h * wind;
	} else {
		float h = clamp((top_y - VERTEX.y) / 2.6, 0.0, 1.0);
		float x = VERTEX.x;
		VERTEX.z += ((sin(t * 1.2 + x * 3.0) * 0.5 + 0.5) * 0.18 + sin(t * 2.3 + x * 5.0) * 0.03) * h * wind;
		VERTEX.x += sin(t * 0.9 + VERTEX.y) * 0.03 * h * wind;
	}
}

void fragment() {
	ALBEDO = albedo;
	ROUGHNESS = roughness_v;
	BACKLIGHT = albedo * 0.4;      // 叶子/布被阳光从背后照透
}
