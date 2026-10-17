// 水面（海、泳池共用）
// 海: Gerstner 波让顶点真的起伏（近岸网格是细分的），远处平面只用法线贴图。
// 岸边泡沫: 不读深度缓冲（VR 双眼渲染下读深度贴图有兼容风险），而是用"已知的沙滩坡度公式"直接算水深 → 水浅处起泡、变透明。
shader_type spatial;
render_mode blend_mix, depth_draw_always, cull_disabled, specular_schlick_ggx;

uniform vec3 deep_color : source_color = vec3(0.01, 0.10, 0.18);
uniform vec3 shallow_color : source_color = vec3(0.05, 0.40, 0.42);
uniform vec3 foam_color : source_color = vec3(0.92, 0.95, 0.95);
uniform sampler2D normal_a : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D normal_b : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D foam_noise : filter_linear_mipmap, repeat_enable;
uniform float scale_a = 0.045;
uniform float scale_b = 0.11;
uniform float normal_strength = 0.6;
uniform float wave_time = 0.0;
uniform float sea_level = -2.8;
uniform float wall_z = -13.4;      // 海堤外侧（浪拍墙的地方起白沫）
uniform float seabed = -7.0;
uniform float waves_on = 1.0;       // 0 = 远海平面 / 泳池
uniform vec4 w1;
uniform vec4 w2;
uniform vec4 w3;
uniform vec4 w4;
uniform float swash_amp = 0.15;
uniform float swash_period = 9.0;
uniform vec4 grid_bounds = vec4(-200.0, 200.0, -250.0, -12.0);   // x_min x_max z_min z_max
uniform float pool_mode = 0.0;
uniform float pool_floor = -2.25;

varying vec3 wpos;
varying float crest;
varying float wdepth;

float ground_h(vec2 p) {
	return p.y > wall_z ? 0.3 : seabed;
}

vec3 gerstner(vec4 w, vec2 p, float t, inout vec3 tang, inout vec3 binorm) {
	float k = 6.2831853 / w.w;
	float c = sqrt(9.8 / k);
	vec2 d = normalize(w.xy);
	float f = k * (dot(d, p) - c * t);
	float a = w.z / k;
	float s = w.z * sin(f);
	float co = w.z * cos(f);
	tang += vec3(-d.x * d.x * s, d.x * co, -d.x * d.y * s);
	binorm += vec3(-d.x * d.y * s, d.y * co, -d.y * d.y * s);
	return vec3(d.x * a * cos(f), a * sin(f), d.y * a * cos(f));
}

void vertex() {
	vec3 p = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vec3 disp = vec3(0.0);
	vec3 tang = vec3(1.0, 0.0, 0.0);
	vec3 binorm = vec3(0.0, 0.0, 1.0);
	crest = 0.0;
	if (pool_mode < 0.5 && waves_on > 0.5) {
		float depth0 = sea_level - ground_h(p.xz);
		float edge = (1.0 - smoothstep(grid_bounds.y - 40.0, grid_bounds.y, abs(p.x)))
				* smoothstep(grid_bounds.z, grid_bounds.z + 40.0, p.z);
		float att = smoothstep(-0.3, 2.0, depth0) * edge;
		vec3 t2 = vec3(0.0);
		vec3 b2 = vec3(0.0);
		vec3 off = gerstner(w1, p.xz, wave_time, t2, b2) + gerstner(w2, p.xz, wave_time, t2, b2)
				+ gerstner(w3, p.xz, wave_time, t2, b2) + gerstner(w4, p.xz, wave_time, t2, b2);
		tang += t2 * att;
		binorm += b2 * att;
		disp = off * att;
		crest = off.y * att;
		float shore = (1.0 - smoothstep(3.0, 12.0, depth0)) * edge;
		disp.y += swash_amp * sin(6.2831853 * wave_time / swash_period) * shore;
	}
	VERTEX += disp;
	NORMAL = normalize(cross(binorm, tang));
	wpos = p + disp;
	wdepth = pool_mode > 0.5 ? (wpos.y - pool_floor) : (wpos.y - ground_h(p.xz));
}

void fragment() {
	vec2 uv = wpos.xz;
	float t = wave_time;
	vec3 na = texture(normal_a, uv * scale_a + vec2(t * 0.012, t * 0.007)).rgb;
	vec3 nb = texture(normal_b, uv * scale_b + vec2(-t * 0.009, t * 0.015)).rgb;
	NORMAL_MAP = mix(na, nb, 0.5);
	float dist = length(wpos - CAMERA_POSITION_WORLD);
	NORMAL_MAP_DEPTH = normal_strength * mix(1.0, 0.25, clamp(dist / 300.0, 0.0, 1.0));

	float dep = clamp(wdepth, 0.0, 60.0);
	vec3 col = mix(shallow_color, deep_color, smoothstep(0.0, 6.0, dep));
	float fn = texture(foam_noise, uv * 0.35 + vec2(0.0, t * 0.05)).r;
	float shore_foam = (1.0 - smoothstep(0.0, 0.4, dep)) * smoothstep(0.35, 0.6, fn + 0.35 * (1.0 - dep / 0.4));
	float crest_foam = smoothstep(0.36, 0.56, crest + fn * 0.1) * smoothstep(0.45, 0.8, fn) * 0.7;
	// 浪拍海堤: 离墙 2m 内起白沫，跟着涌浪（swash）一起一涨一退
	float wall_d = wall_z - wpos.z;
	float surge = 0.55 + 0.45 * sin(6.2831853 * wave_time / swash_period + 1.2);
	float wall_foam = (1.0 - smoothstep(0.0, 1.2 + 1.6 * surge, wall_d)) * smoothstep(0.3, 0.6, fn + 0.3 * surge);
	float foam = max(max(shore_foam, crest_foam), wall_foam) * (1.0 - pool_mode);

	ALBEDO = mix(col, foam_color, foam);
	ROUGHNESS = mix(0.03, 0.7, foam);
	SPECULAR = 0.5;
	ALPHA = mix(clamp(0.2 + dep * 0.5, 0.2, 0.96), 1.0, foam);
	if (pool_mode > 0.5) {
		ALPHA = 0.5;
	}
	if (!FRONT_FACING) {        // 从水下往上看
		ALBEDO = col * 0.7 + vec3(0.04, 0.10, 0.12);
		ALPHA = 0.8;
		NORMAL = -NORMAL;
	}
}
