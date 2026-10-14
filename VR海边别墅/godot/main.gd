extends Node3D
## 主场景: 加载 Blender 导出的 villa.glb → 加碰撞、换材质、放灯 → 生成玩家 → 处理交互和时间切换
##
## 为什么运行时加载 glb（GLTFDocument），而不是让 Godot 编辑器导入？
##   编辑器导入要先打开一次编辑器生成 .import 缓存；运行时加载则 "Blender 重新生成 → 直接运行" 就行，
##   一键 bat 最简单。代价是每次启动多花不到 1 秒解析模型（模型只有 30 万字节）。

const MODEL := "res://model/villa.glb"
const META := "res://model/villa_meta.json"
const PlayerScript := preload("res://player.gd")
const WaterShader := preload("res://water.gdshader")

## 不需要碰撞的物体（名字前缀/包含）: 海面（人可以走进浅水，被沙坡托着）、远山、树叶、伞面、泳池水
const NO_COLLISION_PREFIX := ["海面", "远山", "泳池水面", "伞面", "灯位"]

## 三个时间段: 太阳高度/方位、光色、天空颜色、环境光
const TIMES := [
	{"name": "下午", "sun_elev": 38.0, "sun_az": 200.0, "sun_color": Color(1.0, 0.96, 0.9), "sun_energy": 1.5,
	 "sky_top": Color(0.22, 0.42, 0.74), "sky_hor": Color(0.70, 0.80, 0.90), "ambient": 1.0, "amb_color": Color(0.80, 0.76, 0.70),
	 "fog": Color(0.74, 0.82, 0.90), "moon": false, "lights": false, "exposure": 1.0},
	{"name": "黄昏", "sun_elev": 5.0, "sun_az": 195.0, "sun_color": Color(1.0, 0.55, 0.30), "sun_energy": 1.2,
	 "sky_top": Color(0.18, 0.22, 0.42), "sky_hor": Color(0.98, 0.58, 0.34), "ambient": 0.55, "amb_color": Color(0.80, 0.62, 0.50),
	 "fog": Color(0.88, 0.60, 0.46), "moon": false, "lights": true, "exposure": 0.95},
	{"name": "夜晚", "sun_elev": -20.0, "sun_az": 200.0, "sun_color": Color(1, 1, 1), "sun_energy": 0.0,
	 "sky_top": Color(0.005, 0.01, 0.03), "sky_hor": Color(0.03, 0.05, 0.10), "ambient": 0.25, "amb_color": Color(0.20, 0.25, 0.40),
	 "fog": Color(0.02, 0.03, 0.06), "moon": true, "lights": true, "exposure": 1.3},
]

var player: CharacterBody3D
var sun: DirectionalLight3D
var moon: DirectionalLight3D
var env: Environment
var sky_mat: ProceduralSkyMaterial
var light_groups := {}         # "一楼" -> [OmniLight3D...]
var lights_on := {}            # "一楼" -> bool
var time_idx := 0
var points: Array = []
var point_idx := 0
var mats := {}


func _ready() -> void:
	var xr_ok := _init_xr()
	_build_environment()
	_build_materials()
	_load_model()
	_load_meta()

	player = PlayerScript.new()
	player.name = "Player"
	add_child(player)
	player.setup(xr_ok)
	player.time_cycle.connect(_cycle_time)
	player.next_point.connect(func(): _goto_point(point_idx + 1))
	player.goto_point.connect(_goto_point)

	_apply_time(0)
	_goto_point.call_deferred(0)
	print("[villa] ready. XR=", xr_ok)

	if "--shots" in OS.get_cmdline_user_args():
		_take_shots()
	if "--walktest" in OS.get_cmdline_user_args():
		_walk_test()


# ------------------------------------------------------------------ OpenXR
func _init_xr() -> bool:
	var xri := XRServer.find_interface("OpenXR")
	if xri and xri.is_initialized():
		get_viewport().use_xr = true
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)   # 帧率交给头显控制
		var rr: float = xri.get("display_refresh_rate") if xri.get("display_refresh_rate") != null else 0.0
		if rr > 0.0:
			Engine.physics_ticks_per_second = int(round(rr))    # 物理频率 = 头显刷新率，移动更顺
		print("[villa] OpenXR OK, refresh=", rr)
		return true
	print("[villa] OpenXR not available -> desktop mode")
	return false


# ------------------------------------------------------------------ 天空、太阳、雾
func _build_environment() -> void:
	env = Environment.new()
	sky_mat = ProceduralSkyMaterial.new()
	sky_mat.ground_bottom_color = Color(0.02, 0.10, 0.16)
	sky_mat.sun_angle_max = 20.0
	var sky := Sky.new()
	sky.sky_material = sky_mat
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	# 室内没有实时全局光照，纯天空环境光会让屋里发蓝 → 混一半暖灰色
	env.ambient_light_sky_contribution = 0.55
	env.ambient_light_color = Color(0.80, 0.76, 0.70)
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.fog_enabled = true                  # 远处的空气感，也让海平线自然
	env.fog_density = 0.0012
	env.fog_aerial_perspective = 0.6
	env.fog_sky_affect = 0.3
	env.glow_enabled = true
	env.glow_intensity = 0.4
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

	sun = DirectionalLight3D.new()
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 60.0
	add_child(sun)
	moon = DirectionalLight3D.new()
	moon.light_color = Color(0.55, 0.65, 1.0)
	moon.light_energy = 0.18
	moon.rotation_degrees = Vector3(-35, 160, 0)
	moon.shadow_enabled = true
	moon.directional_shadow_max_distance = 40.0
	add_child(moon)


func _apply_time(i: int) -> void:
	time_idx = i % TIMES.size()
	var t: Dictionary = TIMES[time_idx]
	sun.rotation_degrees = Vector3(-t.sun_elev, t.sun_az, 0)
	sun.light_color = t.sun_color
	sun.light_energy = t.sun_energy
	sun.visible = t.sun_energy > 0.0
	moon.visible = t.moon
	sky_mat.sky_top_color = t.sky_top
	sky_mat.sky_horizon_color = t.sky_hor
	sky_mat.ground_horizon_color = t.sky_hor.darkened(0.2)
	env.ambient_light_energy = t.ambient
	env.ambient_light_color = t.amb_color
	env.fog_light_color = t.fog
	env.tonemap_exposure = t.exposure
	for g in light_groups:
		_set_lights(g, t.lights)
	print("[villa] time -> ", t.name)


func _cycle_time() -> void:
	_apply_time(time_idx + 1)


# ------------------------------------------------------------------ 材质（替换 glTF 里只有纯色的材质）
func _noise_tex(freq: float, c0: Color, c1: Color, seed_: int, normal := false) -> NoiseTexture2D:
	var n := FastNoiseLite.new()
	n.frequency = freq
	n.seed = seed_
	n.fractal_octaves = 4
	var tex := NoiseTexture2D.new()
	tex.width = 512
	tex.height = 512
	tex.seamless = true
	tex.noise = n
	if normal:
		tex.as_normal_map = true
		tex.bump_strength = 6.0
	else:
		var g := Gradient.new()
		g.set_color(0, c0)
		g.set_color(1, c1)
		tex.color_ramp = g
	tex.generate_mipmaps = true
	return tex


func _triplanar(c0: Color, c1: Color, freq: float, scale: Vector3, rough: float, seed_: int) -> StandardMaterial3D:
	# 三向投影 + 世界坐标: 不需要 UV，任意大小的方块纹理密度都一致
	var m := StandardMaterial3D.new()
	m.albedo_texture = _noise_tex(freq, c0, c1, seed_)
	m.uv1_triplanar = true
	m.uv1_world_triplanar = true
	m.uv1_scale = scale
	m.roughness = rough
	return m


func _water(shallow: Color, deep: Color, sa: float, sb: float, deep_dist: float, strength: float) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = WaterShader
	m.set_shader_parameter("normal_a", _noise_tex(0.012, Color.BLACK, Color.WHITE, 3, true))
	m.set_shader_parameter("normal_b", _noise_tex(0.02, Color.BLACK, Color.WHITE, 7, true))
	m.set_shader_parameter("shallow_color", shallow)
	m.set_shader_parameter("deep_color", deep)
	m.set_shader_parameter("scale_a", sa)
	m.set_shader_parameter("scale_b", sb)
	m.set_shader_parameter("deep_dist", deep_dist)
	m.set_shader_parameter("wave_strength", strength)
	return m


func _build_materials() -> void:
	mats["海水"] = _water(Color(0.05, 0.36, 0.40), Color(0.01, 0.09, 0.17), 0.045, 0.11, 50.0, 0.8)
	mats["泳池水"] = _water(Color(0.12, 0.58, 0.66), Color(0.12, 0.58, 0.66), 0.35, 0.8, 0.0, 0.5)
	mats["室内木地板"] = _triplanar(Color(0.36, 0.22, 0.12), Color(0.62, 0.43, 0.26), 0.03, Vector3(0.25, 0.25, 2.5), 0.45, 11)
	mats["户外柚木"] = _triplanar(Color(0.26, 0.16, 0.09), Color(0.50, 0.34, 0.20), 0.03, Vector3(2.5, 0.25, 0.25), 0.7, 12)
	mats["沙滩"] = _triplanar(Color(0.62, 0.48, 0.30), Color(0.82, 0.68, 0.46), 0.05, Vector3(0.6, 0.6, 0.6), 0.95, 13)
	mats["清水混凝土"] = _triplanar(Color(0.44, 0.43, 0.41), Color(0.62, 0.61, 0.58), 0.04, Vector3(0.8, 0.8, 0.8), 0.9, 14)
	mats["椰树干"] = _triplanar(Color(0.26, 0.19, 0.12), Color(0.46, 0.36, 0.25), 0.05, Vector3(2, 0.3, 2), 0.9, 15)
	var glass := StandardMaterial3D.new()
	glass.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	glass.albedo_color = Color(0.78, 0.9, 0.92, 0.14)
	glass.roughness = 0.03
	glass.metallic_specular = 0.9
	glass.cull_mode = BaseMaterial3D.CULL_DISABLED
	mats["玻璃"] = glass
	var leaf := StandardMaterial3D.new()
	leaf.albedo_color = Color(0.13, 0.36, 0.11)
	leaf.roughness = 0.6
	leaf.cull_mode = BaseMaterial3D.CULL_DISABLED      # 叶子是单面片，两面都要画
	mats["椰树叶"] = leaf
	var umb := StandardMaterial3D.new()
	umb.albedo_color = Color(0.93, 0.90, 0.82)
	umb.cull_mode = BaseMaterial3D.CULL_DISABLED
	mats["遮阳伞"] = umb


# ------------------------------------------------------------------ 加载模型 + 逐个物体处理
func _load_model() -> void:
	var doc := GLTFDocument.new()
	var st := GLTFState.new()
	var path := ProjectSettings.globalize_path(MODEL)
	var err := doc.append_from_file(path, st)
	if err != OK:
		push_error("找不到模型 %s（先运行 启动_Godot.bat 让 Blender 生成）err=%d" % [path, err])
		return
	var root := doc.generate_scene(st)
	root.name = "Villa"
	add_child(root)
	var nodes: Array[Node] = []
	_collect(root, nodes)
	for n in nodes:
		_process_node(n)


func _collect(n: Node, out: Array[Node]) -> void:
	out.append(n)
	for c in n.get_children():
		_collect(c, out)


func _process_node(n: Node) -> void:
	var nm := String(n.name)
	if nm.begins_with("灯位_"):
		_add_light(n as Node3D, nm.split("_")[1])
		return
	if not n is MeshInstance3D:
		return
	var mi := n as MeshInstance3D
	_replace_materials(mi)

	if nm.begins_with("碰撞_"):                 # 隐形坡道: 只要碰撞，不显示
		mi.visible = false
		_add_collision(mi)
		return
	for p in NO_COLLISION_PREFIX:
		if nm.begins_with(p):
			return
	if nm.contains("_叶"):
		return
	var body := _add_collision(mi)
	if nm.begins_with("滑门_"):
		_make_sliding_door(mi, body, nm.ends_with("_L"))
	elif nm.begins_with("开关_"):
		var floor_name := nm.split("_")[1]
		body.set_meta("interact", func(): _set_lights(floor_name, not lights_on.get(floor_name, false)))


func _replace_materials(mi: MeshInstance3D) -> void:
	if mi.mesh == null:
		return
	for s in mi.mesh.get_surface_count():
		var m := mi.mesh.surface_get_material(s)
		if m and mats.has(m.resource_name):
			mi.set_surface_override_material(s, mats[m.resource_name])


func _add_collision(mi: MeshInstance3D) -> StaticBody3D:
	var body := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	cs.shape = mi.mesh.create_trimesh_shape()
	body.add_child(cs)
	mi.add_child(body)
	return body


func _make_sliding_door(mi: MeshInstance3D, body: StaticBody3D, to_left: bool) -> void:
	# 门扇顶点是世界坐标、节点在原点；沿 X 推一个门宽（留 5cm 搭接）
	var width := mi.get_aabb().size.x - 0.05
	var closed_x := mi.position.x
	var state := {"open": false}
	body.set_meta("interact", func():
		state.open = not state.open
		var target := closed_x + ((-width if to_left else width) if state.open else 0.0)
		var tw := create_tween()
		tw.tween_property(mi, "position:x", target, 1.4).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	)


# ------------------------------------------------------------------ 室内灯
func _add_light(marker: Node3D, group: String) -> void:
	var l := OmniLight3D.new()
	l.light_color = Color(1.0, 0.82, 0.62)
	l.light_energy = 1.2
	l.omni_range = 7.5
	l.omni_attenuation = 1.2
	l.shadow_enabled = false              # VR 省性能: 室内灯不投影
	marker.add_child(l)
	var lamp := MeshInstance3D.new()       # 吸顶灯的小圆片，开灯时发光
	var cyl := CylinderMesh.new()
	cyl.top_radius = 0.22
	cyl.bottom_radius = 0.22
	cyl.height = 0.04
	lamp.mesh = cyl
	lamp.position.y = 0.37
	var lm := StandardMaterial3D.new()
	lm.albedo_color = Color(0.95, 0.93, 0.88)
	lm.emission = Color(1.0, 0.85, 0.65)
	lamp.material_override = lm
	marker.add_child(lamp)
	if not light_groups.has(group):
		light_groups[group] = []
	light_groups[group].append([l, lm])
	l.visible = false


func _set_lights(group: String, on: bool) -> void:
	lights_on[group] = on
	for pair in light_groups.get(group, []):
		pair[0].visible = on
		pair[1].emission_enabled = on


# ------------------------------------------------------------------ 参观点位
func _load_meta() -> void:
	var f := FileAccess.open(META, FileAccess.READ)
	if f == null:
		return
	var data = JSON.parse_string(f.get_as_text())
	if data is Dictionary:
		points = data.get("vr_points", [])


func _goto_point(i: int) -> void:
	if points.is_empty() or player == null:
		return
	point_idx = posmod(i, points.size())
	var p: Dictionary = points[point_idx]
	var pos := Vector3(p.pos[0], p.pos[1] + 0.05, p.pos[2])
	player.teleport_to(pos, p.yaw_deg)
	print("[villa] point -> ", p.name)


# ------------------------------------------------------------------ 自动截图（测试用: godot -- --shots）
func _take_shots() -> void:
	var dir := OS.get_user_data_dir()
	await get_tree().create_timer(1.0).timeout
	var plan := [[0, 0, "a"], [1, 0, "b"], [2, 0, "c"], [3, 1, "d"], [4, 0, "e"], [5, 2, "f"]]
	for step in plan:
		_goto_point(step[0])
		_apply_time(step[1])
		await get_tree().create_timer(0.8).timeout
		get_viewport().get_texture().get_image().save_png("%s/shot_%s.png" % [dir, step[2]])
	# 推开一楼两扇门再拍一张
	for n in find_children("滑门_一楼_*", "MeshInstance3D", true, false):
		for c in n.get_children():
			if c.has_meta("interact"):
				c.get_meta("interact").call()
	_apply_time(0)
	_goto_point(1)
	await get_tree().create_timer(2.0).timeout
	get_viewport().get_texture().get_image().save_png("%s/shot_g_door.png" % dir)
	print("[villa] shots saved to ", dir)
	get_tree().quit()


# ------------------------------------------------------------------ 自动走路测试（godot -- --walktest）
func _walk(dir: Vector2, secs: float) -> void:
	player.auto_move = dir
	await get_tree().create_timer(secs).timeout
	player.auto_move = Vector2.ZERO
	await get_tree().create_timer(0.3).timeout


func _walk_test() -> void:
	await get_tree().create_timer(0.5).timeout
	var p := player
	# 1) 楼梯: 站到第一级前，面向 +X（yaw -90°）往前走
	p.teleport_to(Vector3(-5.3, 0.35, 4.25), -90.0)
	await _walk(Vector2(0, 1), 3.5)
	print("[test] stairs  pos=", p.global_position, "  (expect y≈3.5)")
	# 2) 客厅往海走，门关着应被挡住（墙在 z=-4.8 一线）
	p.teleport_to(Vector3(-1.0, 0.35, 2.0), 0.0)
	await _walk(Vector2(0, 1), 4.0)
	print("[test] closed door  pos=", p.global_position, "  (expect z≈-4.5, blocked)")
	# 3) 开门再走
	for n in find_children("滑门_一楼_L", "MeshInstance3D", true, false):
		for c in n.get_children():
			if c.has_meta("interact"):
				c.get_meta("interact").call()
	await get_tree().create_timer(1.6).timeout
	await _walk(Vector2(0, 1), 1.5)
	print("[test] open door  pos=", p.global_position, "  (expect z < -5.5, on deck y≈0.3)")
	# 4) 从平台侧边下到沙滩，再走回来（台基 30cm，靠迈台阶）
	p.teleport_to(Vector3(-7.0, 0.35, -7.5), 90.0)   # 面向 -X
	await _walk(Vector2(0, 1), 1.5)
	print("[test] off deck  pos=", p.global_position, "  (expect y≈0, x<-8)")
	await _walk(Vector2(0, -1), 1.5)
	print("[test] back on deck  pos=", p.global_position, "  (expect y≈0.3)")
	# 5) 二楼走到阳台（二楼门关着 → 先开）
	for n in find_children("滑门_二楼_L", "MeshInstance3D", true, false):
		for c in n.get_children():
			if c.has_meta("interact"):
				c.get_meta("interact").call()
	await get_tree().create_timer(1.6).timeout
	p.teleport_to(Vector3(1.4, 3.55, 0.0), 0.0)
	await _walk(Vector2(0, 1), 2.5)
	print("[test] balcony  pos=", p.global_position, "  (expect z<-3, y≈3.5, stopped by railing z>-5)")
	get_tree().quit()
