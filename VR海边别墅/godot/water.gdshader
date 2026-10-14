// 水面着色器（海和泳池共用）: 两层法线贴图朝不同方向滚动 → 波光粼粼。
// 原理: 不移动顶点（平面只有 4 个顶点），只扰动法线 —— 反射/高光跟着动，看起来就像有波浪，开销几乎为零。
shader_type spatial;
render_mode blend_mix, cull_back, depth_draw_opaque, specular_schlick_ggx;

uniform vec3 deep_color : source_color = vec3(0.01, 0.10, 0.18);
uniform vec3 shallow_color : source_color = vec3(0.04, 0.32, 0.38);
uniform sampler2D normal_a : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D normal_b : hint_normal, filter_linear_mipmap, repeat_enable;
uniform float scale_a = 0.045;
uniform float scale_b = 0.11;
uniform float speed = 1.0;
uniform float wave_strength = 0.8;
uniform float shore_z = -33.0;   // 海岸线位置（Godot 坐标，海在 -Z）
uniform float deep_dist = 50.0;  // 离岸多远变成深水色，泳池设为 0 = 全用 shallow_color
uniform float roughness_val = 0.04;

varying vec3 world_pos;

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec2 p = world_pos.xz;
	float t = TIME * speed;
	vec3 na = texture(normal_a, p * scale_a + vec2(t * 0.012, t * 0.007)).rgb * 2.0 - 1.0;
	vec3 nb = texture(normal_b, p * scale_b + vec2(-t * 0.009, t * 0.015)).rgb * 2.0 - 1.0;
	NORMAL_MAP = normalize(vec3(na.xy + nb.xy, na.z * nb.z)) * 0.5 + 0.5;
	// 远处法线减弱，避免地平线闪烁（mipmap 之外的第二道保险）
	float d = length(world_pos - CAMERA_POSITION_WORLD);
	NORMAL_MAP_DEPTH = wave_strength * mix(1.0, 0.2, clamp(d / 400.0, 0.0, 1.0));
	float deep = deep_dist > 0.0 ? smoothstep(0.0, deep_dist, shore_z - world_pos.z) : 0.0;
	ALBEDO = mix(shallow_color, deep_color, deep);
	ROUGHNESS = roughness_val;
	METALLIC = 0.0;
	SPECULAR = 0.6;
}
