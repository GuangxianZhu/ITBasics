// 天空: 渐变 + 太阳/月亮圆盘 + 会飘的云 + 夜里的星星。颜色全部由 main.gd 按时间段推过来。
// 太阳和月亮用"通用"写法画（LIGHTn 都画），因为夜里隐藏太阳后，月亮会变成 LIGHT0。
shader_type sky;

uniform vec3 top_color : source_color = vec3(0.22, 0.42, 0.74);
uniform vec3 horizon_color : source_color = vec3(0.70, 0.80, 0.90);
uniform vec3 ground_color : source_color = vec3(0.05, 0.12, 0.18);
uniform vec3 cloud_color : source_color = vec3(1.0);
uniform float cloud_cover = 0.35;
uniform float stars = 0.0;
uniform sampler2D cloud_noise : filter_linear_mipmap, repeat_enable;

float hash13(vec3 p) {
	p = fract(p * 0.1031);
	p += dot(p, p.zyx + 31.32);
	return fract((p.x + p.y) * p.z);
}

vec3 disc(vec3 d, bool en, vec3 dir, vec3 col, float energy, float size) {
	if (!en) {
		return vec3(0.0);
	}
	float a = acos(clamp(dot(d, dir), -1.0, 1.0));
	float r = max(size * 0.5, 0.009);
	vec3 c = col * min(energy * 4.0, 6.0) * smoothstep(r, r * 0.8, a);
	c += col * energy * (pow(max(dot(d, dir), 0.0), 300.0) * 0.6 + pow(max(dot(d, dir), 0.0), 12.0) * 0.12);
	return c;
}

void sky() {
	vec3 d = EYEDIR;
	float h = d.y;
	vec3 col = mix(horizon_color, top_color, pow(clamp(h, 0.0, 1.0), 0.45));
	if (h < 0.0) {
		col = mix(horizon_color, ground_color, clamp(-h * 5.0, 0.0, 1.0));
	}
	if (!AT_CUBEMAP_PASS && h > 0.0) {
		// 星星: 把方向切成小格，每格随机一颗，闪烁
		float s = hash13(floor(d * 420.0));
		float tw = 0.7 + 0.3 * sin(TIME * 3.0 + s * 60.0);
		col += vec3(smoothstep(0.9975, 1.0, s)) * stars * tw * smoothstep(0.0, 0.2, h) * 2.0;
	}
	col += disc(d, LIGHT0_ENABLED, LIGHT0_DIRECTION, LIGHT0_COLOR, LIGHT0_ENERGY, LIGHT0_SIZE);
	col += disc(d, LIGHT1_ENABLED, LIGHT1_DIRECTION, LIGHT1_COLOR, LIGHT1_ENERGY, LIGHT1_SIZE);
	if (h > 0.0) {
		// 云: 方向投影到一个高空平面，采样噪声，随时间平移
		vec2 uv = d.xz / (h + 0.12) * 0.06;
		float n = texture(cloud_noise, uv + vec2(TIME * 0.0015, TIME * 0.0006)).r * 0.65
				+ texture(cloud_noise, uv * 2.7 + vec2(-TIME * 0.002, 0.3)).r * 0.35;
		float c = smoothstep(1.0 - cloud_cover, 1.0 - cloud_cover + 0.3, n) * smoothstep(0.0, 0.18, h);
		vec3 cc = cloud_color * (0.75 + 0.35 * n);
		col = mix(col, cc, c * 0.92);
	}
	COLOR = col;
}
