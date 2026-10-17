extends Node3D
## 主场景: 加载 Blender 导出的 villa.glb → 换材质（程序化贴图）、加碰撞、挂交互 → 海、天空、全局光照、声音、会动的东西
##
## 为什么运行时加载 glb / png / wav，而不是让 Godot 编辑器导入？
##   编辑器导入要先打开一次编辑器生成缓存；运行时加载则 "Blender/Python 重新生成 → 直接运行" 就行，一键 bat 最简单。
##   代价: 启动时多花几秒解析贴图（约 30 张 1024² PNG）和烘焙全局光照。
##
## 物体靠"名字"识别（名字约定见 scene_extras.py 开头）。

const MODEL := "res://model/villa.glb"
const META := "res://model/villa_meta.json"
const TEX := "res://model/tex/"
const HD := "res://hd/"
const ART := "res://art/"
const SETTINGS := "res://settings.cfg"
const PlayerScript := preload("res://player.gd")
const AudioFX := preload("res://audio_fx.gd")
const WorldFX := preload("res://world_fx.gd")
const Tests := preload("res://tests.gd")
const W := preload("res://water_math.gd")
const WaterShader := preload("res://water.gdshader")
const SkyShader := preload("res://sky.gdshader")
const FoliageShader := preload("res://foliage.gdshader")
const TVShader := preload("res://tv.gdshader")

## 不需要碰撞的物体（名字开头）
const NO_COLLISION := ["海面", "远山", "泳池水面", "伞面", "沙滩伞面", "灯位", "窗帘", "沙草", "吊灯_", "可拿_",
	"篝火位", "灯塔灯位", "吊扇叶", "冰箱隔板", "冰箱食材", "水龙头", "台灯", "画_", "画框", "LED_", "筒灯_",
	"烧烤火位", "迪斯科球", "山上树木", "山坡", "对岸城市", "货轮", "AI_flamingo", "山脚房子"]
## 两层楼的海景门（都关着时，屋里听到的海浪是闷的）
const SEA_DOORS := ["滑门_一楼_L", "滑门_一楼_R", "滑门_二楼_L"]

## 四个时间段（切换时 3 秒平滑过渡）
const TIMES := [
	{"name": "清晨", "sun_elev": 9.0, "sun_az": 120.0, "sun_color": Color(1.0, 0.74, 0.52), "sun_energy": 1.1, "moon": 0.0,
	 "top": Color(0.32, 0.48, 0.74), "hor": Color(0.96, 0.76, 0.62), "cloud": Color(1.0, 0.84, 0.74), "cover": 0.45, "stars": 0.0,
	 "ambient": 0.7, "amb_color": Color(0.85, 0.78, 0.72), "fog": Color(0.92, 0.80, 0.72), "fog_d": 0.0012, "exposure": 1.0,
	 "lights": false, "lighthouse": 0.0},
	{"name": "下午", "sun_elev": 38.0, "sun_az": 200.0, "sun_color": Color(1.0, 0.96, 0.9), "sun_energy": 1.5, "moon": 0.0,
	 "top": Color(0.22, 0.42, 0.74), "hor": Color(0.70, 0.80, 0.90), "cloud": Color(1.0, 1.0, 1.0), "cover": 0.33, "stars": 0.0,
	 "ambient": 1.0, "amb_color": Color(0.80, 0.76, 0.70), "fog": Color(0.74, 0.82, 0.90), "fog_d": 0.0010, "exposure": 1.0,
	 "lights": false, "lighthouse": 0.0},
	{"name": "黄昏", "sun_elev": 4.0, "sun_az": 195.0, "sun_color": Color(1.0, 0.55, 0.30), "sun_energy": 1.2, "moon": 0.0,
	 "top": Color(0.18, 0.22, 0.42), "hor": Color(0.98, 0.58, 0.34), "cloud": Color(1.0, 0.60, 0.45), "cover": 0.5, "stars": 0.0,
	 "ambient": 0.55, "amb_color": Color(0.80, 0.62, 0.50), "fog": Color(0.88, 0.60, 0.46), "fog_d": 0.0012, "exposure": 0.95,
	 "lights": true, "lighthouse": 0.6},
	{"name": "夜晚", "sun_elev": -20.0, "sun_az": 200.0, "sun_color": Color(1, 1, 1), "sun_energy": 0.0, "moon": 0.22,
	 "top": Color(0.005, 0.01, 0.03), "hor": Color(0.03, 0.05, 0.10), "cloud": Color(0.13, 0.15, 0.21), "cover": 0.3, "stars": 1.0,
	 "ambient": 0.25, "amb_color": Color(0.20, 0.25, 0.40), "fog": Color(0.02, 0.03, 0.06), "fog_d": 0.0012, "exposure": 1.3,
	 "lights": true, "lighthouse": 1.0},
]

var cfg := ConfigFile.new()
var xr_mode := false
var fx_step := 0
var fx_base := {}
var player: CharacterBody3D
var audio
var fx
var sun: DirectionalLight3D
var moon: DirectionalLight3D
var env: Environment
var sky_mat: ShaderMaterial
var vgi: VoxelGI
var tex_cache := {}
var mats := {}
var water_mats: Array = []
var lamp_mats := {}            # "一楼"/"二楼" -> StandardMaterial3D（灯罩发光）
var light_groups := {}         # "一楼"/"二楼" -> [OmniLight3D]
var lights_on := {}
var doors_open := {}
var curtain_mat: ShaderMaterial
var curtain1_mat: ShaderMaterial
var ktv_mat: ShaderMaterial
var ktv_on := false
var ktv_music: AudioStreamPlayer3D
var ktv_lights: Array = []
var disco_pivot: Node3D
var meta := {}
var probes: Array = []
var time_idx := 1
var cur := {}                  # 当前（插值中的）时间段数值
var points: Array = []
var point_idx := 0
var wt := 0.0                  # 波浪时间
var underwater := false
var fan_pivot: Node3D
var fan_on := true
var fridge_pivot: Node3D
var fridge_open := false
var fridge_light: OmniLight3D
var fridge_mat: StandardMaterial3D
var tv_mat: ShaderMaterial
var tv_on := false
var tv_light: OmniLight3D
var radio: AudioStreamPlayer3D
var ocean_snd: AudioStreamPlayer3D
var wind_snd: AudioStreamPlayer
var under_snd: AudioStreamPlayer
var _pending := {"fridge": [], "boat": [], "fan": null, "lh_marker": null, "lh_glass": null, "fire": null, "grab": []}


func _ready() -> void:
	cfg.load(SETTINGS)
	var xr_ok := _init_xr()
	xr_mode = xr_ok
	audio = AudioFX.new()
	add_child(audio)
	audio.setup()
	_load_meta()
	_build_environment()
	_build_materials()
	fx = WorldFX.new()
	fx.audio = audio
	add_child(fx)
	_load_model()
	_build_sea()
	_build_world_bounds()
	_finish_pending()
	_setup_reflections()

	player = PlayerScript.new()
	player.name = "Player"
	add_child(player)
	player.setup(xr_ok)
	player.water_fn = func(x: float, z: float) -> float: return W.water_height(x, z, wt)
	player.time_cycle.connect(func(): set_time(time_idx + 1))
	player.next_point.connect(func(): _goto_point(point_idx + 1))
	player.goto_point.connect(_goto_point)
	player.step.connect(func(s: String, p: Vector3): audio.play_at("step_%s_%d" % [s, randi() % 3], p, -6.0 if s == "sand" else -2.0))
	player.splash.connect(func(p: Vector3): audio.play_at("splash", p, 0.0))
	player.toggle_gi.connect(_toggle_gi)
	player.fx_cycle.connect(_fx_cycle)

	_setup_ambient_audio()
	fx.setup_birds(7)
	_setup_gi()
	set_time(1, true)
	_goto_point.call_deferred(0)
	print("[villa] ready. XR=", xr_ok)

	var args := OS.get_cmdline_user_args()
	if "--shots" in args or "--walktest" in args:
		var t = Tests.new()
		t.m = self
		add_child(t)
		t.run.call_deferred(args)


# ================================================================== OpenXR
func _init_xr() -> bool:
	var xri := XRServer.find_interface("OpenXR")
	if xri and xri.is_initialized():
		get_viewport().use_xr = true
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
		var rr = xri.get("display_refresh_rate")
		if rr != null and rr > 0.0:
			Engine.physics_ticks_per_second = int(round(rr))
		print("[villa] OpenXR OK, refresh=", rr)
		return true
	print("[villa] OpenXR not available -> desktop mode")
	return false


# ================================================================== 天空、太阳、月亮、雾
func _noise_tex(freq: float, seed_: int, normal := false, size := 512) -> NoiseTexture2D:
	var n := FastNoiseLite.new()
	n.frequency = freq
	n.seed = seed_
	n.fractal_octaves = 5
	var t := NoiseTexture2D.new()
	t.width = size
	t.height = size
	t.seamless = true
	t.noise = n
	t.generate_mipmaps = true
	if normal:
		t.as_normal_map = true
		t.bump_strength = 6.0
	return t


func _build_environment() -> void:
	env = Environment.new()
	sky_mat = ShaderMaterial.new()
	sky_mat.shader = SkyShader
	sky_mat.set_shader_parameter("cloud_noise", _noise_tex(0.006, 5))
	var sky := Sky.new()
	sky.sky_material = sky_mat
	sky.radiance_size = Sky.RADIANCE_SIZE_128
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_sky_contribution = 0.55        # 一半天空色、一半暖灰（屋里不发蓝）
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.fog_enabled = true
	env.fog_aerial_perspective = 0.6
	env.fog_sky_affect = 0.25
	env.glow_enabled = true
	env.glow_intensity = 0.45
	env.ssao_enabled = cfg.get_value("graphics", "ssao", true)
	if xr_mode:
		# VR 双眼渲染下，屏幕空间特效（SSAO、SSR）容易只对左眼正确、右眼出白影 → VR 里默认关
		env.ssao_enabled = cfg.get_value("graphics", "xr_ssao", false)
	env.ssao_radius = 0.8
	env.ssao_intensity = 1.6
	env.ssr_enabled = cfg.get_value("graphics", "ssr", true)      # 屏幕空间反射: 亮面地砖映出家具
	if xr_mode:
		env.ssr_enabled = cfg.get_value("graphics", "xr_ssr", false)
	env.ssr_max_steps = 48
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

	sun = DirectionalLight3D.new()
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 70.0
	sun.light_angular_distance = 0.6
	add_child(sun)
	moon = DirectionalLight3D.new()
	moon.light_color = Color(0.6, 0.7, 1.0)
	moon.rotation_degrees = Vector3(-35, 160, 0)
	moon.shadow_enabled = true
	moon.directional_shadow_max_distance = 40.0
	moon.light_angular_distance = 1.5
	add_child(moon)


func set_time(i: int, instant := false) -> void:
	time_idx = posmod(i, TIMES.size())
	var to: Dictionary = TIMES[time_idx]
	var from := cur.duplicate() if not cur.is_empty() else to.duplicate()
	for g in light_groups:
		_set_lights(g, to.lights)
	if instant:
		_blend_time(from, to, 1.0)
		if not probes.is_empty():
			_setup_reflections.call_deferred()
	else:
		var tw := create_tween()
		tw.tween_method(func(k: float): _blend_time(from, to, k), 0.0, 1.0, 3.0)
		tw.finished.connect(_setup_reflections)            # 光线变了，反射重拍
	print("[villa] time -> ", to.name)


func _blend_time(a: Dictionary, b: Dictionary, k: float) -> void:
	for key in b:
		var va = a.get(key, b[key])
		var vb = b[key]
		if vb is float:
			cur[key] = lerpf(va, vb, k)
		elif vb is Color:
			cur[key] = va.lerp(vb, k)
		else:
			cur[key] = vb if k > 0.5 else va
	sun.rotation_degrees = Vector3(-cur.sun_elev, cur.sun_az, 0)
	sun.light_color = cur.sun_color
	sun.light_energy = cur.sun_energy if cur.sun_elev > -2.0 else 0.0
	sun.visible = sun.light_energy > 0.01
	moon.light_energy = cur.moon
	moon.visible = cur.moon > 0.01
	sky_mat.set_shader_parameter("top_color", cur.top)
	sky_mat.set_shader_parameter("horizon_color", cur.hor)
	sky_mat.set_shader_parameter("ground_color", cur.hor.darkened(0.75))
	sky_mat.set_shader_parameter("cloud_color", cur.cloud)
	sky_mat.set_shader_parameter("cloud_cover", cur.cover)
	sky_mat.set_shader_parameter("stars", cur.stars)
	env.ambient_light_energy = cur.ambient
	env.ambient_light_color = cur.amb_color
	env.tonemap_exposure = cur.exposure
	if not underwater:
		env.fog_light_color = cur.fog
		env.fog_density = cur.fog_d
	if fx:
		fx.set_lighthouse(cur.lighthouse)


# ================================================================== 贴图与材质
func _tex(name: String) -> Texture2D:
	if tex_cache.has(name):
		return tex_cache[name]
	var tex: Texture2D = null
	for p in [HD + name + ".png", HD + name + ".jpg", TEX + name + ".png"]:
		var path := ProjectSettings.globalize_path(p)
		if FileAccess.file_exists(path):
			var img := Image.load_from_file(path)
			if img:
				img.generate_mipmaps()
				tex = ImageTexture.create_from_image(img)
				break
	tex_cache[name] = tex
	return tex


func _pbr(set_name: String, tile_m: float, tint := Color.WHITE, rough := 1.0) -> StandardMaterial3D:
	# 三向投影 + 世界坐标: 不需要 UV；贴图按"米"铺，任何大小的方块纹理密度都一致
	var m := StandardMaterial3D.new()
	m.albedo_texture = _tex(set_name + "_albedo")
	m.albedo_color = tint
	var n := _tex(set_name + "_normal")
	if n:
		m.normal_enabled = true
		m.normal_texture = n
	m.roughness_texture = _tex(set_name + "_rough")
	m.roughness = rough
	m.uv1_triplanar = true
	m.uv1_world_triplanar = true
	m.uv1_scale = Vector3.ONE / tile_m
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	return m


func _foliage(mode: int, col: Color, wind := 1.0) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = FoliageShader
	m.set_shader_parameter("mode", mode)
	m.set_shader_parameter("albedo", col)
	m.set_shader_parameter("wind", wind)
	m.set_shader_parameter("roughness_v", 0.95 if mode == 2 else 0.6)
	return m


func _water_mat(pool := false, waves := true) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = WaterShader
	W.apply_to_shader(m)
	m.set_shader_parameter("normal_a", _noise_tex(0.012, 3, true))
	m.set_shader_parameter("normal_b", _noise_tex(0.02, 7, true))
	m.set_shader_parameter("foam_noise", _noise_tex(0.03, 11))
	m.set_shader_parameter("waves_on", 1.0 if waves else 0.0)
	if pool:
		m.set_shader_parameter("pool_mode", 1.0)
		m.set_shader_parameter("shallow_color", Color(0.12, 0.58, 0.66))
		m.set_shader_parameter("deep_color", Color(0.06, 0.40, 0.55))
		m.set_shader_parameter("scale_a", 0.35)
		m.set_shader_parameter("scale_b", 0.8)
		m.set_shader_parameter("normal_strength", 0.35)
	water_mats.append(m)
	return m


func _build_materials() -> void:
	mats["白墙"] = _pbr("plaster", 2.0)
	mats["清水混凝土"] = _pbr("concrete", 2.0)
	mats["室内木地板"] = _pbr("wood_floor", 2.4)
	mats["户外柚木"] = _pbr("deck", 1.2)
	mats["阳台石材"] = _pbr("stone_tile", 1.2)
	mats["泳池瓷砖"] = _pbr("pool_tile", 0.6)
	mats["泳池条石"] = _pbr("pool_stone", 1.2)
	mats["抛光地砖"] = _pbr("porcelain", 1.6, Color.WHITE, 1.0)
	mats["大理石"] = _pbr("marble", 1.2)
	mats["露台石材"] = _pbr("stone_tile", 1.2, Color(0.82, 0.82, 0.80))
	mats["海堤毛石"] = _pbr("seawall", 3.0)
	mats["草坪"] = _pbr("grass", 3.0)
	mats["山林"] = _pbr("forest", 40.0)
	mats["树冠"] = _pbr("forest", 9.0, Color(1.15, 1.15, 1.1))
	mats["岩石"] = _pbr("rock", 3.0)
	# AI 家具: 颜色/质感来自 ai_furniture/furniture.json（经 villa_meta.json 传过来）
	for k in meta.get("ai_materials", {}):
		var am: Dictionary = meta.ai_materials[k]
		var c: Array = am.get("color", [0.7, 0.7, 0.7])
		var col := Color(c[0], c[1], c[2])
		var tex: String = am.get("tex", "")
		var m: StandardMaterial3D
		if tex != "":
			m = _pbr(tex, {"fabric": 0.4, "marble": 1.0, "wood_floor": 1.2}.get(tex, 1.0), col * 1.25, am.get("rough", 0.6))
		else:
			m = StandardMaterial3D.new()
			m.albedo_color = col
			m.roughness = am.get("rough", 0.6)
		m.metallic = am.get("metal", 0.0)
		mats[k] = m
	mats["沙滩"] = _pbr("sand", 3.0)
	mats["椰树干"] = _pbr("bark", 1.5)
	mats["岩石"] = _pbr("rock", 3.0)
	mats["沙发布"] = _pbr("fabric", 0.4, Color(1.0, 0.97, 0.9))
	mats["床品"] = _pbr("fabric", 0.4, Color(1.1, 1.1, 1.08))
	mats["地毯"] = _pbr("fabric", 0.25, Color(0.9, 0.82, 0.7))
	mats["靠垫蓝"] = _pbr("fabric", 0.3, Color(0.22, 0.38, 0.6))
	var glass := StandardMaterial3D.new()
	glass.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	glass.albedo_color = Color(0.78, 0.9, 0.92, 0.12)
	glass.roughness = 0.03
	glass.metallic_specular = 0.9
	glass.cull_mode = BaseMaterial3D.CULL_DISABLED
	mats["玻璃"] = glass
	mats["椰树叶"] = _foliage(0, Color(0.13, 0.36, 0.11))
	mats["_沙草"] = _foliage(1, Color(0.42, 0.45, 0.22))
	curtain_mat = _foliage(2, Color(0.93, 0.90, 0.84), 0.3)
	mats["窗帘"] = curtain_mat
	curtain1_mat = _foliage(2, Color(0.20, 0.36, 0.42), 0.3)
	curtain1_mat.set_shader_parameter("top_y", 3.17)
	mats["窗帘_一楼"] = curtain1_mat
	var plant := StandardMaterial3D.new()
	plant.albedo_color = Color(0.10, 0.32, 0.12)
	plant.cull_mode = BaseMaterial3D.CULL_DISABLED
	plant.roughness = 0.5
	mats["绿植叶"] = plant
	for n in ["遮阳伞", "浴巾条纹", "浴巾蓝", "船身"]:
		mats[n] = null              # 只改成双面（见 _replace_materials）
	# 画: godot/art/ 里有图就用（比如你用 ComfyUI 生成的），否则用程序化海景画
	var art_files: Array = []
	var d := DirAccess.open(ProjectSettings.globalize_path(ART))
	if d:
		for f in d.get_files():
			if f.get_extension().to_lower() in ["png", "jpg", "jpeg", "webp"]:
				art_files.append(f)
		art_files.sort()
	for k in 3:
		var pm := StandardMaterial3D.new()
		var t: Texture2D = null
		if k < art_files.size():
			var img := Image.load_from_file(ProjectSettings.globalize_path(ART + art_files[k]))
			if img:
				img.generate_mipmaps()
				t = ImageTexture.create_from_image(img)
		pm.albedo_texture = t if t else _tex("painting_%d" % k)
		pm.roughness = 0.8
		mats["画布_%d" % k] = pm
	tv_mat = ShaderMaterial.new()
	tv_mat.shader = TVShader
	mats["电视屏幕"] = tv_mat
	ktv_mat = ShaderMaterial.new()
	ktv_mat.shader = TVShader
	mats["KTV屏幕"] = ktv_mat
	mats["泳池水"] = _water_mat(true, false)
	fridge_mat = StandardMaterial3D.new()
	fridge_mat.albedo_color = Color(0.95, 0.97, 1.0)
	fridge_mat.emission = Color(0.9, 0.95, 1.0)
	mats["冰箱内壁"] = fridge_mat
	var lh := StandardMaterial3D.new()
	lh.albedo_color = Color(0.95, 0.92, 0.7)
	mats["灯室玻璃"] = lh
	_pending.lh_glass = lh
	for g in ["一楼", "二楼"]:
		var lm := StandardMaterial3D.new()
		lm.albedo_color = Color(0.95, 0.90, 0.78)
		lm.emission = Color(1.0, 0.82, 0.6)
		lm.emission_energy_multiplier = 0.9
		lm.roughness = 0.9
		lamp_mats[g] = lm


# ================================================================== 加载模型 + 逐个物体处理
func _load_model() -> void:
	var doc := GLTFDocument.new()
	var st := GLTFState.new()
	var path := ProjectSettings.globalize_path(MODEL)
	var err := doc.append_from_file(path, st)
	if err != OK:
		push_error("找不到模型 %s（先运行 启动_Godot版.bat 让 Blender 生成）err=%d" % [path, err])
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
	if nm.begins_with("可拿_"):
		_pending.grab.append([nm, (n as Node3D).global_position])
		return
	if nm == "灯塔灯位":
		_pending.lh_marker = n
		return
	if nm == "篝火位" or nm == "烧烤火位":
		_pending.fire = n
		return
	if not n is MeshInstance3D:
		return
	var mi := n as MeshInstance3D
	_replace_materials(mi, nm)

	if nm == "海面":
		mi.visible = false                       # 换成 _build_sea() 里会起伏的海
		return
	if nm.begins_with("碰撞_"):
		mi.visible = false
		_add_collision(mi)
		return
	if nm.contains("_叶") and nm.begins_with("椰树"):
		var bb := mi.get_aabb()
		mi.set_instance_shader_parameter("crown_r", maxf(bb.size.x, bb.size.z) * 0.5)
	if nm.begins_with("窗帘") or nm.begins_with("滑门") or nm.begins_with("冰箱门") or nm.begins_with("吊扇叶") \
			or nm.begins_with("小船"):
		mi.gi_mode = GeometryInstance3D.GI_MODE_DYNAMIC
	if nm == "吊扇叶":
		_pending.fan = mi
	if nm == "迪斯科球":
		_pending["disco"] = mi
	if nm.begins_with("AI_flamingo"):
		_pending["float"] = mi
	if nm.begins_with("冰箱门"):
		_pending.fridge.append(mi)

	for p in NO_COLLISION:
		if nm.begins_with(p):
			return
	if nm.contains("_叶"):
		return
	var body := _add_collision(mi, nm.begins_with("小船"))
	if nm.begins_with("小船"):
		_pending.boat.append(mi)
	if nm.begins_with("AI_") and nm.contains("_座"):
		# AI 家具: 名字里写着座面高度（厘米），座位点 = 家具原点（底面中心）往上 seat_h
		var seat_h := float(nm.get_slice("_座", 1).to_int()) / 100.0
		body.set_meta("seat", mi.global_position + Vector3(0, seat_h, 0))
	elif nm.contains("座") or nm.ends_with("_垫"):
		var bb := mi.global_transform * mi.get_aabb()
		body.set_meta("seat", Vector3(bb.get_center().x, bb.end.y, bb.get_center().z))

	if nm.begins_with("滑门_"):
		_make_sliding_door(mi, body, nm.ends_with("_L"), nm)
	elif nm.begins_with("开关_"):
		var floor_name := nm.split("_")[1]
		body.set_meta("interact", func():
			_set_lights(floor_name, not lights_on.get(floor_name, false))
			audio.play_at("click", mi.global_transform * mi.get_aabb().get_center()))
	elif nm.begins_with("冰箱门"):
		body.set_meta("interact", _toggle_fridge)
	elif nm.begins_with("收音机"):
		body.set_meta("interact", _toggle_radio)
	elif nm == "电视" or nm == "电视屏幕":
		body.set_meta("interact", _toggle_tv)
	elif nm == "吊扇电机":
		body.set_meta("interact", func(): fan_on = not fan_on; audio.play_at("click", Vector3(-4.0, 6.2, 0.6)))
	elif nm == "KTV电视" or nm == "KTV屏幕":
		body.set_meta("interact", _toggle_ktv)
	elif nm == "篝火柴堆" or nm == "篝火石圈" or nm == "烧烤台" or nm.begins_with("AI_bbq_grill"):
		body.set_meta("interact", func(): fx.set_fire(not fx.fire_on); audio.play_at("click", body.global_position, -6.0))


func _replace_materials(mi: MeshInstance3D, nm: String) -> void:
	if mi.mesh == null:
		return
	for s in mi.mesh.get_surface_count():
		var m := mi.mesh.surface_get_material(s)
		if m == null:
			continue
		var key := m.resource_name
		if nm == "沙草":
			key = "_沙草"
		if nm.begins_with("LED_") or nm.begins_with("筒灯_"):
			mi.set_surface_override_material(s, lamp_mats[nm.split("_")[1]])
			continue
		if nm.begins_with("吊灯_") and nm.ends_with("_罩") or nm == "落地灯罩":
			mi.set_surface_override_material(s, lamp_mats["一楼"])
			continue
		if nm == "台灯罩":
			mi.set_surface_override_material(s, lamp_mats["二楼"])
			continue
		if mats.has(key):
			if mats[key] == null:
				var dup := m.duplicate() as BaseMaterial3D
				if dup:
					dup.cull_mode = BaseMaterial3D.CULL_DISABLED
					mi.set_surface_override_material(s, dup)
			else:
				mi.set_surface_override_material(s, mats[key])


const SURFACE := {"室内木地板": "wood", "户外柚木": "wood", "家具木": "wood", "沙滩": "sand", "海岬草地": "sand", "草坪": "sand"}


func _add_collision(mi: MeshInstance3D, animatable := false) -> PhysicsBody3D:
	var body: PhysicsBody3D = AnimatableBody3D.new() if animatable else StaticBody3D.new()
	var cs := CollisionShape3D.new()
	cs.shape = mi.mesh.create_trimesh_shape()
	body.add_child(cs)
	mi.add_child(body)
	var m := mi.mesh.surface_get_material(0)
	body.set_meta("surface", SURFACE.get(m.resource_name if m else "", "stone"))
	return body


func _make_sliding_door(mi: MeshInstance3D, body: PhysicsBody3D, to_left: bool, nm: String) -> void:
	var width := mi.get_aabb().size.x - 0.05
	var closed_x := mi.position.x
	doors_open[nm] = false
	body.set_meta("interact", func():
		doors_open[nm] = not doors_open[nm]
		var target := closed_x + ((-width if to_left else width) if doors_open[nm] else 0.0)
		var tw := create_tween()
		tw.tween_property(mi, "position:x", target, 1.4).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
		audio.play_at("door_slide", mi.global_transform * mi.get_aabb().get_center(), -2.0)
		curtain_mat.set_shader_parameter("wind", 1.0 if doors_open.get("滑门_二楼_L", false) else 0.3)
		var open1: bool = doors_open.get("滑门_一楼_L", false) or doors_open.get("滑门_一楼_R", false)
		curtain1_mat.set_shader_parameter("wind", 1.0 if open1 else 0.3))


func _pivot_for(parts: Array, at: Vector3) -> Node3D:
	var pv := Node3D.new()
	add_child(pv)
	pv.global_position = at
	for p in parts:
		var gt: Transform3D = p.global_transform
		p.get_parent().remove_child(p)
		pv.add_child(p)
		p.global_transform = gt
	return pv


func _finish_pending() -> void:
	if _pending.fan:
		fan_pivot = _pivot_for([_pending.fan], Vector3(4.25, 6.08, -0.3))
	if _pending.get("disco"):
		disco_pivot = _pivot_for([_pending.disco], Vector3(-5.4, 5.9, 1.4))
	if _pending.get("float"):
		fx.setup_float(_pending.float)
	if not _pending.fridge.is_empty():
		fridge_pivot = _pivot_for(_pending.fridge, Vector3(-6.10, 0.0, 4.78))   # 铰链在靠北墙那条边
		fridge_light = OmniLight3D.new()
		fridge_light.light_color = Color(0.85, 0.92, 1.0)
		fridge_light.omni_range = 1.6
		fridge_light.light_energy = 0.0
		add_child(fridge_light)
		fridge_light.global_position = Vector3(-6.0, 1.4, 4.4)
	if not _pending.boat.is_empty():
		fx.setup_boat(_pending.boat, Vector3(9.8, 0.0, -16.6))
	if _pending.lh_marker:
		fx.setup_lighthouse(_pending.lh_marker, _pending.lh_glass)
	if _pending.fire:
		fx.setup_fire(_pending.fire)
	for g in _pending.grab:
		_spawn_grabbable(g[0], g[1])
	# 电视的蓝光、收音机
	tv_light = OmniLight3D.new()
	tv_light.light_color = Color(0.6, 0.75, 1.0)
	tv_light.omni_range = 4.0
	tv_light.visible = false
	add_child(tv_light)
	tv_light.global_position = Vector3(5.7, 1.6, 2.1)
	var rnode := Node3D.new()
	add_child(rnode)
	rnode.global_position = Vector3(2.49, 1.15, -0.16)
	radio = audio.loop_3d("radio", rnode, -4.0, 2.5, "SFX", false)


# ================================================================== 交互
func _toggle_fridge() -> void:
	fridge_open = not fridge_open
	var tw := create_tween()
	tw.tween_property(fridge_pivot, "rotation:y", deg_to_rad(-100.0) if fridge_open else 0.0, 0.9) \
		.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_OUT)
	fridge_mat.emission_enabled = fridge_open
	fridge_light.light_energy = 1.2 if fridge_open else 0.0
	audio.play_at("click", fridge_light.global_position, -4.0)


func _toggle_radio() -> void:
	if radio.playing:
		radio.stop()
	else:
		radio.play()
	audio.play_at("click", radio.global_position)


func _toggle_tv() -> void:
	tv_on = not tv_on
	var on := tv_on
	tv_mat.set_shader_parameter("on", 1.0 if on else 0.0)
	tv_light.visible = on
	audio.play_at("click", tv_light.global_position)


# ================================================================== 能拿起来的东西
func _ball_tex() -> ImageTexture:
	var img := Image.create(256, 128, false, Image.FORMAT_RGB8)
	var cols := [Color(0.9, 0.15, 0.1), Color(0.97, 0.97, 0.95), Color(0.1, 0.35, 0.85),
		Color(0.98, 0.8, 0.1), Color(0.97, 0.97, 0.95), Color(0.15, 0.65, 0.3)]
	for x in 256:
		var c: Color = cols[int(x / 256.0 * 6.0)]
		for y in 128:
			img.set_pixel(x, y, c if (y > 8 and y < 120) else Color(0.97, 0.97, 0.95))
	return ImageTexture.create_from_image(img)


func _spawn_grabbable(nm: String, pos: Vector3) -> void:
	var rb := RigidBody3D.new()
	rb.add_to_group("grabbable")
	rb.continuous_cd = true
	rb.contact_monitor = true
	rb.max_contacts_reported = 2
	var pm := PhysicsMaterial.new()
	var cs := CollisionShape3D.new()
	var mi := MeshInstance3D.new()
	var m := StandardMaterial3D.new()
	if nm.begins_with("可拿_沙滩球"):
		var s := SphereShape3D.new()
		s.radius = 0.22
		cs.shape = s
		var sm := SphereMesh.new()
		sm.radius = 0.22
		sm.height = 0.44
		mi.mesh = sm
		m.albedo_texture = _ball_tex()
		m.roughness = 0.35
		rb.mass = 0.3
		pm.bounce = 0.75
		rb.linear_damp = 0.3
	elif nm.begins_with("可拿_椰子"):
		var s := SphereShape3D.new()
		s.radius = 0.1
		cs.shape = s
		var sm := SphereMesh.new()
		sm.radius = 0.1
		sm.height = 0.24
		mi.mesh = sm
		m.albedo_color = Color(0.35, 0.22, 0.1)
		m.roughness = 0.9
		rb.mass = 1.2
		pm.bounce = 0.2
	else:
		var s := CylinderShape3D.new()
		s.radius = 0.045
		s.height = 0.1
		cs.shape = s
		var cm := CylinderMesh.new()
		cm.top_radius = 0.045
		cm.bottom_radius = 0.038
		cm.height = 0.1
		mi.mesh = cm
		m.albedo_color = [Color(0.95, 0.95, 0.93), Color(0.2, 0.4, 0.6), Color(0.85, 0.5, 0.3)][randi() % 3]
		m.roughness = 0.15
		rb.mass = 0.25
		pm.bounce = 0.1
	mi.material_override = m
	mi.gi_mode = GeometryInstance3D.GI_MODE_DYNAMIC
	rb.physics_material_override = pm
	rb.add_child(cs)
	rb.add_child(mi)
	add_child(rb)
	rb.global_position = pos
	rb.body_entered.connect(func(_b):
		var v := rb.linear_velocity.length()
		if v > 1.2:
			audio.play_at("ball" if nm.contains("球") else "step_stone_0", rb.global_position, linear_to_db(clampf(v / 8.0, 0.1, 1.0))))


# ================================================================== 海
func _build_sea() -> void:
	# 近岸: 400×236m、每米一格的细分网格 → 顶点真的起伏；远处: 只有法线波光的大平面
	var near := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(400, 238)
	pm.subdivide_width = 399
	pm.subdivide_depth = 237
	near.mesh = pm
	near.position = Vector3(0, W.SEA_LEVEL, -131)
	near.material_override = _water_mat()
	near.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	near.extra_cull_margin = 2.0
	add_child(near)
	var far_m := _water_mat(false, false)
	for r in [Rect2(-3000, -3000, 6000, 2750), Rect2(-3000, -250, 2800, 238), Rect2(200, -250, 2800, 238)]:
		var f := MeshInstance3D.new()
		var fm := PlaneMesh.new()
		fm.size = r.size
		f.mesh = fm
		f.position = Vector3(r.get_center().x, W.SEA_LEVEL, r.get_center().y)
		f.material_override = far_m
		f.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(f)


func _build_world_bounds() -> void:
	# 看不见的围墙: 游不出 120m、走不出后山
	var body := StaticBody3D.new()
	add_child(body)
	for b in [[Vector3(-120, 10, -40), Vector3(2, 60, 260)], [Vector3(120, 10, -40), Vector3(2, 60, 260)],
			[Vector3(0, 10, -150), Vector3(240, 60, 2)], [Vector3(0, 10, 60), Vector3(240, 60, 2)]]:
		var cs := CollisionShape3D.new()
		var bs := BoxShape3D.new()
		bs.size = b[1]
		cs.shape = bs
		cs.position = b[0]
		body.add_child(cs)


# ================================================================== 灯
func _add_light(marker: Node3D, group: String) -> void:
	var l := OmniLight3D.new()
	l.light_color = Color(1.0, 0.82, 0.62)
	l.light_energy = 1.1
	l.omni_range = 7.5
	l.omni_attenuation = 1.2
	l.shadow_enabled = false
	marker.add_child(l)
	var lamp := MeshInstance3D.new()
	var cyl := CylinderMesh.new()
	cyl.top_radius = 0.22
	cyl.bottom_radius = 0.22
	cyl.height = 0.04
	lamp.mesh = cyl
	lamp.position.y = 0.37
	lamp.material_override = lamp_mats[group]
	marker.add_child(lamp)
	if not light_groups.has(group):
		light_groups[group] = []
	light_groups[group].append(l)
	l.visible = false


func _set_lights(group: String, on: bool) -> void:
	lights_on[group] = on
	for l in light_groups.get(group, []):
		l.visible = on
	if lamp_mats.has(group):
		lamp_mats[group].emission_enabled = on


# ================================================================== 全局光照（光在屋里反弹）
func _setup_gi() -> void:
	var mode: String = cfg.get_value("graphics", "gi", "voxel")
	if mode == "voxel":
		# VoxelGI: 把房子切成 256 格的体素，记住"哪里有墙、什么颜色"；光照本身每帧实时算 →
		# 换时间段、开关灯，反弹光都会跟着变（这就是能保留昼夜切换的原因）
		vgi = VoxelGI.new()
		vgi.position = Vector3(0, 3.7, -1.3)
		vgi.size = Vector3(19, 9, 15)
		vgi.subdiv = VoxelGI.SUBDIV_256
		add_child(vgi)
		var t0 := Time.get_ticks_msec()
		vgi.bake()
		if vgi.data:
			vgi.data.energy = 1.0
			vgi.data.propagation = 0.75
			vgi.data.use_two_bounces = true
		print("[villa] VoxelGI baked in %d ms" % (Time.get_ticks_msec() - t0))
	elif mode == "sdfgi":
		env.sdfgi_enabled = true
		env.sdfgi_use_occlusion = true
	print("[villa] GI = ", mode)


func _toggle_gi() -> void:
	if vgi:
		vgi.visible = not vgi.visible
		print("[villa] VoxelGI ", vgi.visible)
	else:
		env.sdfgi_enabled = not env.sdfgi_enabled


# ================================================================== 声音
func _setup_ambient_audio() -> void:
	var on := Node3D.new()
	add_child(on)
	ocean_snd = audio.loop_3d("ocean", on, 4.0, 18.0)
	wind_snd = audio.loop_2d("wind", -14.0)
	under_snd = audio.loop_2d("underwater", -80.0)


func _process(delta: float) -> void:
	wt += delta
	for m in water_mats:
		m.set_shader_parameter("wave_time", wt)
	fx.wave_time = wt
	if fan_pivot and fan_on:
		fan_pivot.rotate_y(delta * 4.0)
	if disco_pivot and ktv_on:
		disco_pivot.rotate_y(delta * 1.2)
		for i in ktv_lights.size():
			var a := wt * (1.3 + i * 0.4) + i * 2.1
			ktv_lights[i].position = Vector3(-4.6 + cos(a) * 1.4, 4.4, 0.8 + sin(a) * 1.6)
	if player == null:
		return
	var eye: Vector3 = player.get_eye().global_position
	# 海浪声源始终在"离你最近的那段海岸线"上
	if ocean_snd:
		ocean_snd.get_parent().global_position = Vector3(clampf(eye.x, -150, 150), W.SEA_LEVEL + 0.5, -13.8)
	# 水下: 画面变蓝变雾、声音变闷
	var wh := W.water_height(eye.x, eye.z, wt)
	var under := eye.y < wh
	if under != underwater:
		underwater = under
		if under:
			env.fog_light_color = Color(0.03, 0.22, 0.28)
			env.fog_density = 0.6
		else:
			env.fog_light_color = cur.fog
			env.fog_density = cur.fog_d
		under_snd.volume_db = -6.0 if under else -80.0
	var inside := absf(eye.x) < 7.0 and absf(eye.z) < 5.0 and eye.y < 7.0
	var open_any := false
	for d in SEA_DOORS:
		open_any = open_any or doors_open.get(d, false)
	var cutoff := 20000.0
	if under:
		cutoff = 450.0
	elif inside:
		cutoff = 3500.0 if open_any else 900.0
	audio.set_muffle(cutoff)
	if wind_snd:
		wind_snd.volume_db = lerpf(wind_snd.volume_db, -24.0 if inside else -14.0, delta * 2.0)


# ================================================================== 参观点位
func _load_meta() -> void:
	var f := FileAccess.open(META, FileAccess.READ)
	if f == null:
		return
	var data = JSON.parse_string(f.get_as_text())
	if data is Dictionary:
		meta = data
		points = data.get("vr_points", [])


func _goto_point(i: int) -> void:
	if points.is_empty() or player == null:
		return
	point_idx = posmod(i, points.size())
	var p: Dictionary = points[point_idx]
	player.teleport_to(Vector3(p.pos[0], p.pos[1] + 0.05, p.pos[2]), p.yaw_deg)
	print("[villa] point -> ", p.name)


# ================================================================== KTV（二楼娱乐室）
func _toggle_ktv() -> void:
	ktv_on = not ktv_on
	ktv_mat.set_shader_parameter("on", 1.0 if ktv_on else 0.0)
	if ktv_music == null:
		var n := Node3D.new()
		add_child(n)
		n.global_position = Vector3(-6.4, 5.0, 1.4)
		ktv_music = audio.loop_3d("radio", n, 0.0, 3.0, "SFX", false)
		for c in [Color(1, 0.2, 0.6), Color(0.2, 0.6, 1), Color(0.4, 1, 0.3)]:
			var l := OmniLight3D.new()
			l.light_color = c
			l.omni_range = 3.0
			l.light_energy = 0.7
			add_child(l)
			ktv_lights.append(l)
	if ktv_on:
		ktv_music.play()
	else:
		ktv_music.stop()
	for l in ktv_lights:
		l.visible = ktv_on
	audio.play_at("click", Vector3(-6.4, 4.5, 1.4))


# ================================================================== 反射（抛光地砖、玻璃要能映出东西）
## ReflectionProbe = 在房间中间拍一张 360° 照片当反射贴图；box_projection 让反射按房间形状校正，
## 不会"飘在无穷远"。换时间段后重拍（UPDATE_ONCE 不会自己更新）。
func _setup_reflections() -> void:
	for p in probes:
		p.queue_free()
	probes.clear()
	for spec in [[Vector3(0, 1.9, 0), Vector3(14, 3.0, 10)], [Vector3(0, 5.0, -0.5), Vector3(14, 3.0, 11)]]:
		var rp := ReflectionProbe.new()
		rp.position = spec[0]
		rp.size = spec[1]
		rp.box_projection = true
		rp.update_mode = ReflectionProbe.UPDATE_ONCE
		rp.intensity = 0.9
		add_child(rp)
		probes.append(rp)



# ================================================================== 画面特效排查（左手柄 ☰ / 桌面 F 键）
## 每按一次多关一个特效，眼前显示当前状态；找到"关了哪个之后右眼白影消失"就知道是谁的问题。
const FX_STEPS := [
	["全部按设置", []],
	["关 屏幕反射SSR", ["ssr"]],
	["关 SSR + 环境光遮蔽SSAO", ["ssr", "ssao"]],
	["关 SSR + SSAO + 辉光", ["ssr", "ssao", "glow"]],
	["关 SSR + SSAO + 辉光 + 全局光照", ["ssr", "ssao", "glow", "gi"]],
	["再关 雾", ["ssr", "ssao", "glow", "gi", "fog"]],
	["再关 阴影", ["ssr", "ssao", "glow", "gi", "fog", "shadow"]],
]


func _fx_cycle() -> void:
	if fx_base.is_empty():
		fx_base = {"ssr": env.ssr_enabled, "ssao": env.ssao_enabled, "glow": env.glow_enabled, "fog": env.fog_enabled,
			"gi": vgi.visible if vgi else env.sdfgi_enabled, "shadow": sun.shadow_enabled}
	fx_step = (fx_step + 1) % FX_STEPS.size()
	var off: Array = FX_STEPS[fx_step][1]
	env.ssr_enabled = fx_base.ssr and not off.has("ssr")
	env.ssao_enabled = fx_base.ssao and not off.has("ssao")
	env.glow_enabled = fx_base.glow and not off.has("glow")
	env.fog_enabled = fx_base.fog and not off.has("fog")
	if vgi:
		vgi.visible = fx_base.gi and not off.has("gi")
	else:
		env.sdfgi_enabled = fx_base.gi and not off.has("gi")
	sun.shadow_enabled = fx_base.shadow and not off.has("shadow")
	moon.shadow_enabled = sun.shadow_enabled
	var state := "SSR%s SSAO%s 辉光%s GI%s 雾%s 阴影%s" % [
		"开" if env.ssr_enabled else "关", "开" if env.ssao_enabled else "关", "开" if env.glow_enabled else "关",
		("开" if vgi.visible else "关") if vgi else ("开" if env.sdfgi_enabled else "关"),
		"开" if env.fog_enabled else "关", "开" if sun.shadow_enabled else "关"]
	player.notice("特效 %d/%d: %s\n%s" % [fx_step + 1, FX_STEPS.size(), FX_STEPS[fx_step][0], state])
