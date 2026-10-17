// 电视画面: 程序化的"海洋纪录片"——日落、起伏的海、跳出水面的鱼影、扫描线。on=0 时是黑色亮面屏。
shader_type spatial;

uniform float on = 0.0;

void fragment() {
	vec2 uv = UV;                 // (0,0) 在左上
	float t = TIME;
	float hz = 0.48 + 0.015 * sin(t * 0.4);
	vec3 sky = mix(vec3(0.98, 0.55, 0.30), vec3(0.25, 0.35, 0.65), clamp((hz - uv.y) / hz, 0.0, 1.0));
	vec2 sp = vec2(0.65 + 0.05 * sin(t * 0.05), hz - 0.12);
	float sun = smoothstep(0.08, 0.07, length((uv - sp) * vec2(1.6, 1.0)));
	sky = mix(sky, vec3(1.0, 0.9, 0.6), sun);
	float wave = sin(uv.x * 30.0 + t * 1.5 + sin(uv.y * 40.0 - t) * 2.0) * 0.5 + 0.5;
	vec3 sea = mix(vec3(0.05, 0.15, 0.30), vec3(0.95, 0.6, 0.35), wave * (1.0 - smoothstep(0.0, 0.3, abs(uv.x - sp.x))) * 0.5);
	sea *= 0.7 + 0.3 * smoothstep(hz, 1.0, uv.y);
	vec3 c = uv.y < hz ? sky : sea;
	// 一条跳出水面的鱼（每 6 秒一次的抛物线）
	float ph = mod(t, 6.0) / 1.2;
	if (ph < 1.0) {
		vec2 fp = vec2(0.25 + ph * 0.2, hz - 0.18 * sin(ph * 3.14159));
		c = mix(c, vec3(0.05), smoothstep(0.025, 0.018, length((uv - fp) * vec2(1.0, 2.2))));
	}
	c *= 0.9 + 0.1 * sin(uv.y * 600.0);
	ALBEDO = vec3(0.01);
	ROUGHNESS = 0.08;
	EMISSION = c * on * 1.6;
}
