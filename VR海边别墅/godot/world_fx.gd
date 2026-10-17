extends Node3D
## 会动的世界: 海鸥、随浪起伏的小船、灯塔光束、篝火。

const W := preload("res://water_math.gd")

var audio                     # audio_fx.gd
var wave_time := 0.0          # 由 main 每帧写入（和水面着色器同一个时间）

var birds: Array = []
var boat_pivot: Node3D
var boat_base := Vector3.ZERO
var lh_pivot: Node3D
var lh_beams: Array = []
var lh_light: SpotLight3D
var lh_glass: StandardMaterial3D
var lh_level := 0.0
var fire_root: Node3D
var fire_light: OmniLight3D
var fire_sound: AudioStreamPlayer3D
var fire_on := false


# ================================================================== 海鸥
func setup_birds(n: int) -> void:
	var white := StandardMaterial3D.new()
	white.albedo_color = Color(0.95, 0.95, 0.93)
	var grey := StandardMaterial3D.new()
	grey.albedo_color = Color(0.45, 0.47, 0.5)
	for i in n:
		var b := Node3D.new()
		var body := MeshInstance3D.new()
		var sm := SphereMesh.new()
		sm.radius = 0.09
		sm.height = 0.18
		body.mesh = sm
		body.scale = Vector3(1, 0.9, 2.6)
		body.material_override = white
		b.add_child(body)
		var wings: Array = []
		for side in [-1, 1]:
			var piv := Node3D.new()
			piv.position = Vector3(0.06 * side, 0.02, 0)
			b.add_child(piv)
			var w := MeshInstance3D.new()
			var bm := BoxMesh.new()
			bm.size = Vector3(0.55, 0.015, 0.16)
			w.mesh = bm
			w.position = Vector3(0.27 * side, 0, 0)
			w.material_override = grey
			piv.add_child(w)
			wings.append([piv, side])
		add_child(b)
		birds.append({
			"node": b, "wings": wings,
			"c": Vector3(randf_range(-40, 40), 0, randf_range(-70, -30)),
			"r": randf_range(25, 60), "h": randf_range(14, 30), "w": randf_range(0.05, 0.1) * (1 if i % 2 else -1),
			"a": randf() * TAU, "ph": randf() * 10.0, "call": randf_range(3, 12),
		})


func _update_birds(delta: float) -> void:
	var t := Time.get_ticks_msec() / 1000.0
	for b in birds:
		b.a += b.w * delta
		var pos: Vector3 = b.c + Vector3(cos(b.a) * b.r, b.h + sin(b.a * 2.0 + b.ph) * 2.5, sin(b.a) * b.r)
		var ahead: Vector3 = b.c + Vector3(cos(b.a + 0.05 * sign(b.w)) * b.r, b.h, sin(b.a + 0.05 * sign(b.w)) * b.r)
		var n: Node3D = b.node
		n.position = pos
		if pos.distance_to(ahead) > 0.001:
			n.look_at(Vector3(ahead.x, pos.y, ahead.z), Vector3.UP)
		n.rotation.z = -sign(b.w) * 0.35                       # 转弯时侧倾
		var gliding: bool = sin(t * 0.25 + b.ph) > 0.2
		var flap := 0.12 if gliding else sin(t * 9.0 + b.ph) * 0.6
		for wp in b.wings:
			wp[0].rotation.z = flap * wp[1]
		b.call -= delta
		if b.call <= 0.0:
			b.call = randf_range(8, 20)
			if audio:
				audio.play_at("gull_%d" % (randi() % 2), pos, -4.0, 0.15, "Amb")


# ================================================================== 小船
func setup_boat(parts: Array, center: Vector3) -> void:
	boat_pivot = Node3D.new()
	boat_pivot.name = "BoatPivot"
	add_child(boat_pivot)
	boat_base = Vector3(center.x, 0, center.z)
	boat_pivot.position = boat_base
	for p in parts:
		var gt: Transform3D = p.global_transform
		p.get_parent().remove_child(p)
		boat_pivot.add_child(p)
		p.global_transform = Transform3D(gt.basis, gt.origin)


func _update_boat() -> void:
	if boat_pivot == null:
		return
	var x := boat_base.x
	var z := boat_base.z
	var h := W.sea_height(x, z, wave_time) - W.SEA_LEVEL
	var hf := W.sea_height(x, z - 1.6, wave_time)
	var hb := W.sea_height(x, z + 1.6, wave_time)
	var hl := W.sea_height(x - 0.6, z, wave_time)
	var hr := W.sea_height(x + 0.6, z, wave_time)
	boat_pivot.position = Vector3(x, h * 0.9, z)
	boat_pivot.rotation = Vector3(atan2(hf - hb, 3.2) * 0.8, 0, atan2(hl - hr, 1.2) * 0.6)


# ================================================================== 灯塔
func setup_lighthouse(marker: Node3D, glass: StandardMaterial3D) -> void:
	lh_glass = glass
	lh_pivot = Node3D.new()
	add_child(lh_pivot)
	lh_pivot.global_position = marker.global_position
	var sh := Shader.new()
	sh.code = """
shader_type spatial;
render_mode unshaded, blend_add, cull_disabled, depth_draw_never, shadows_disabled;
uniform float level = 0.0;
varying float along;
void vertex() { along = VERTEX.y; }
void fragment() {
	float fall = clamp((along + 80.0) / 160.0, 0.0, 1.0);          // 灯这头亮、远处淡
	float rim = pow(abs(dot(NORMAL, VIEW)), 1.5);
	ALBEDO = vec3(1.0, 0.93, 0.72);
	ALPHA = level * 0.35 * fall * fall * rim;
}
"""
	for k in 2:
		var arm := Node3D.new()
		arm.rotation.y = PI * k
		lh_pivot.add_child(arm)
		var beam := MeshInstance3D.new()
		var cm := CylinderMesh.new()
		cm.top_radius = 0.35
		cm.bottom_radius = 9.0
		cm.height = 160.0
		cm.radial_segments = 24
		cm.cap_top = false
		cm.cap_bottom = false
		beam.mesh = cm
		var m := ShaderMaterial.new()
		m.shader = sh
		beam.material_override = m
		beam.rotation_degrees.x = 90.0
		beam.position = Vector3(0, 0, -80.0)
		beam.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		arm.add_child(beam)
		lh_beams.append(m)
	lh_light = SpotLight3D.new()
	lh_light.light_color = Color(1.0, 0.92, 0.7)
	lh_light.spot_range = 250.0
	lh_light.spot_angle = 3.5
	lh_light.light_energy = 0.0
	lh_pivot.add_child(lh_light)


func set_lighthouse(level: float) -> void:
	lh_level = level
	for m in lh_beams:
		m.set_shader_parameter("level", level)
	if lh_light:
		lh_light.light_energy = level * 60.0
		lh_light.visible = level > 0.01
	if lh_glass:
		lh_glass.emission_enabled = level > 0.01
		lh_glass.emission = Color(1.0, 0.9, 0.6)
		lh_glass.emission_energy_multiplier = 4.0 * level


# ================================================================== 篝火
func _soft_dot() -> GradientTexture2D:
	var g := Gradient.new()
	g.set_color(0, Color(1, 1, 1, 1))
	g.set_color(1, Color(1, 1, 1, 0))
	var t := GradientTexture2D.new()
	t.gradient = g
	t.fill = GradientTexture2D.FILL_RADIAL
	t.fill_from = Vector2(0.5, 0.5)
	t.fill_to = Vector2(0.5, 0.0)
	t.width = 64
	t.height = 64
	return t


func _particles(amount: int, life: float, size: float, vel: Vector2, grav: float, colors: Array,
		additive: bool, radius: float) -> GPUParticles3D:
	var p := GPUParticles3D.new()
	p.amount = amount
	p.lifetime = life
	p.randomness = 0.4
	var pm := ParticleProcessMaterial.new()
	pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_SPHERE
	pm.emission_sphere_radius = radius
	pm.direction = Vector3(0, 1, 0)
	pm.spread = 12.0
	pm.initial_velocity_min = vel.x
	pm.initial_velocity_max = vel.y
	pm.gravity = Vector3(0, grav, 0)
	pm.scale_min = 0.6
	pm.scale_max = 1.0
	var curve := Curve.new()
	curve.add_point(Vector2(0, 0.6))
	curve.add_point(Vector2(0.3, 1.0))
	curve.add_point(Vector2(1, 0.1 if additive else 1.6))
	var ct := CurveTexture.new()
	ct.curve = curve
	pm.scale_curve = ct
	var g := Gradient.new()
	g.offsets = PackedFloat32Array([0.0, 0.4, 1.0])
	g.colors = PackedColorArray(colors)
	var gt := GradientTexture1D.new()
	gt.gradient = g
	pm.color_ramp = gt
	p.process_material = pm
	var q := QuadMesh.new()
	q.size = Vector2(size, size)
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	m.vertex_color_use_as_albedo = true
	m.albedo_texture = _soft_dot()
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	if additive:
		m.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	q.material = m
	p.draw_pass_1 = q
	p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	return p


func setup_fire(marker: Node3D) -> void:
	fire_root = Node3D.new()
	add_child(fire_root)
	fire_root.global_position = marker.global_position
	fire_root.add_child(_particles(70, 0.9, 0.5, Vector2(0.5, 1.1), 1.2,
		[Color(1.0, 0.85, 0.4, 0.9), Color(1.0, 0.45, 0.1, 0.7), Color(0.6, 0.1, 0.02, 0.0)], true, 0.22))
	var embers := _particles(25, 2.2, 0.05, Vector2(1.0, 2.5), 0.6,
		[Color(1.0, 0.8, 0.3, 1.0), Color(1.0, 0.4, 0.1, 0.9), Color(0.5, 0.1, 0.0, 0.0)], true, 0.3)
	(embers.process_material as ParticleProcessMaterial).spread = 30.0
	fire_root.add_child(embers)
	var smoke := _particles(24, 3.5, 0.9, Vector2(0.4, 0.8), 0.3,
		[Color(0.3, 0.3, 0.3, 0.0), Color(0.35, 0.35, 0.35, 0.25), Color(0.5, 0.5, 0.5, 0.0)], false, 0.2)
	smoke.position.y = 0.6
	fire_root.add_child(smoke)
	fire_light = OmniLight3D.new()
	fire_light.light_color = Color(1.0, 0.6, 0.3)
	fire_light.omni_range = 9.0
	fire_light.shadow_enabled = true
	fire_light.position.y = 0.5
	fire_root.add_child(fire_light)
	if audio:
		fire_sound = audio.loop_3d("fire", fire_root, 0.0, 3.0, "SFX", false)
	set_fire(false)


func set_fire(on: bool) -> void:
	fire_on = on
	if fire_root == null:
		return
	for c in fire_root.get_children():
		if c is GPUParticles3D:
			c.emitting = on
	fire_light.visible = on
	if fire_sound:
		if on:
			fire_sound.play()
		else:
			fire_sound.stop()


# ================================================================== 每帧
func _process(delta: float) -> void:
	_update_birds(delta)
	if lh_pivot and lh_level > 0.0:
		lh_pivot.rotate_y(TAU / 8.0 * delta)            # 8 秒转一圈
	if fire_on and fire_light:
		var t := Time.get_ticks_msec() / 1000.0
		fire_light.light_energy = 2.2 + 0.5 * sin(t * 13.0) + 0.3 * sin(t * 23.0 + 1.0) + randf_range(-0.2, 0.2)


func _physics_process(_delta: float) -> void:
	_update_boat()
