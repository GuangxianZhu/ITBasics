extends CharacterBody3D
## 玩家: VR 模式（Quest 3 两个手柄）+ 桌面模式（键鼠，没戴头显时自动用）
##
## VR 操作:
##   左摇杆 = 走 / 游（游泳时朝你看的方向游，包括往下潜）   左摇杆按下 = 跑（切换）
##   右摇杆左右 = 每次转 30°
##   食指放在扳机上 = 激光；按扳机: 指地面 = 瞬移，指门/开关/电视/冰箱/篝火 = 操作，指椅子/沙发/躺椅 = 坐下
##   握把（中指）= 抓东西: 手边 30cm 内的直接抓；激光指着远处的球/椰子/杯子按握把 = 隔空吸到手里；松开 = 扔
##   A / X = 换时间（清晨 → 下午 → 黄昏 → 夜晚）    B / Y = 下一个参观点位
## 桌面: WASD 走、鼠标看、左键 = 扳机、E 或右键 = 抓/放、拿着东西时左键 = 扔、Shift 跑、T 时间、Tab/1~8 点位、G 开关全局光照、Esc 放开鼠标

signal time_cycle
signal next_point
signal goto_point(index: int)
signal step(surface: String, pos: Vector3)
signal splash(pos: Vector3)
signal toggle_gi
signal fx_cycle               # 左手柄 ☰ 菜单键: 逐个关画面特效（排查右眼白影用）

const WALK := 1.8
const RUN := 3.6
const SWIM := 1.5
const GRAVITY := 9.8
const STEP_UP := 0.36
const SNAP_TURN := deg_to_rad(30.0)
const DESK_EYE := 1.65
const SIT_EYE := 0.85          # 坐下后眼睛离椅面的高度
const CHEST := 1.05            # 胸口离脚的高度: 胸口没入水中 = 开始游泳
const FLOAT_DEPTH := 1.15      # 游泳时身体原点在水面下多少（头露出水面约 0.45m）
const STRIDE := 0.62           # 一步多远响一次脚步声
const FAR := 6000.0

const C_IDLE := Color(0.55, 0.75, 1.0)
const C_FLOOR := Color(0.3, 1.0, 0.5)
const C_ACT := Color(1.0, 0.85, 0.2)
const C_GRAB := Color(0.3, 0.95, 1.0)

var xr_on := false
var origin: XROrigin3D
var xr_cam: XRCamera3D
var hands: Array = []
var desk_cam: Camera3D
var desk_ray: RayCast3D
var snap_ready := true
var running := false
var font: SystemFont
var water_fn: Callable         # func(x, z) -> 水面高度 或 -INF（main 注入）

var swimming := false
var seated := false
var held := {}                 # 0/1 = 左右手, 2 = 桌面: {rb, off: Transform3D, hist: Array}
var stride_acc := 0.0
var auto_move := Vector2.ZERO  # 自动测试用（模拟摇杆）
var auto_look_pitch := 0.0
var frozen := false            # 测试截图用: 悬在空中不掉下去


func setup(use_xr: bool) -> void:
	xr_on = use_xr
	font = SystemFont.new()
	font.font_names = PackedStringArray(["Microsoft YaHei", "Yu Gothic", "Noto Sans CJK SC", "Noto Sans CJK JP", "sans-serif"])

	var cs := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.22
	cap.height = 1.6
	cs.shape = cap
	cs.position.y = 0.8
	add_child(cs)
	floor_snap_length = 0.4
	floor_max_angle = deg_to_rad(46.0)

	origin = XROrigin3D.new()
	add_child(origin)
	xr_cam = XRCamera3D.new()
	xr_cam.far = FAR
	xr_cam.near = 0.05
	origin.add_child(xr_cam)
	for side in ["left_hand", "right_hand"]:
		hands.append(_make_hand(side))

	desk_cam = Camera3D.new()
	desk_cam.position.y = DESK_EYE
	desk_cam.far = FAR
	desk_cam.near = 0.05
	desk_cam.fov = 80.0
	add_child(desk_cam)
	desk_ray = RayCast3D.new()
	desk_ray.target_position = Vector3(0, 0, -40)
	desk_ray.add_exception(self)
	desk_cam.add_child(desk_ray)

	if xr_on:
		xr_cam.current = true
	else:
		desk_cam.current = true
		for h in hands:
			h.ctrl.visible = false
		_make_desktop_hud()


func get_eye() -> Camera3D:
	return xr_cam if xr_on else desk_cam


func _make_hand(side: String) -> Dictionary:
	var c := XRController3D.new()
	c.tracker = side
	c.pose = &"aim"
	origin.add_child(c)
	var body := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = Vector3(0.035, 0.035, 0.13)
	body.mesh = bm
	body.position.z = 0.06
	var bmat := StandardMaterial3D.new()
	bmat.albedo_color = Color(0.15, 0.15, 0.17)
	body.material_override = bmat
	c.add_child(body)
	var ray := RayCast3D.new()
	ray.target_position = Vector3(0, 0, -40)
	ray.add_exception(self)
	c.add_child(ray)
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_color = C_IDLE
	var laser := MeshInstance3D.new()
	var lm := BoxMesh.new()
	lm.size = Vector3(0.004, 0.004, 1.0)
	laser.mesh = lm
	laser.material_override = mat
	c.add_child(laser)
	var dot := MeshInstance3D.new()
	var sm := SphereMesh.new()
	sm.radius = 0.03
	sm.height = 0.06
	dot.mesh = sm
	dot.material_override = mat
	dot.top_level = true
	c.add_child(dot)
	if side == "left_hand":
		var tip := Label3D.new()
		tip.text = "左摇杆 走/游  按下=跑   右摇杆 转身\n扳机 瞬移/操作/坐下   握把 抓/扔\nA/X 换时间   B/Y 下个点位"
		tip.font = font
		tip.font_size = 28
		tip.pixel_size = 0.0006
		tip.position = Vector3(0, 0.06, 0.06)
		tip.rotation_degrees = Vector3(-50, 0, 0)
		tip.modulate = Color(1, 1, 1, 0.85)
		c.add_child(tip)
	c.button_pressed.connect(_on_button.bind(c))
	return {"ctrl": c, "ray": ray, "laser": laser, "mat": mat, "dot": dot, "hit": {}, "grip": false}


func _make_desktop_hud() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	var lbl := Label.new()
	lbl.text = "桌面模式  WASD 走 · 鼠标看 · 左键 瞬移/操作/坐下 · E/右键 抓放 · 拿着时左键 扔 · Shift 跑 · T 时间 · Tab/1~8 点位 · G 全局光照 · Esc 放开鼠标"
	lbl.position = Vector2(12, 8)
	lbl.add_theme_font_override("font", font)
	lbl.add_theme_font_size_override("font_size", 15)
	lbl.add_theme_color_override("font_outline_color", Color.BLACK)
	lbl.add_theme_constant_override("outline_size", 4)
	layer.add_child(lbl)
	var cross := Label.new()
	cross.text = "+"
	cross.add_theme_font_size_override("font_size", 24)
	cross.set_anchors_preset(Control.PRESET_CENTER)
	cross.position -= Vector2(6, 16)
	layer.add_child(cross)


# ================================================================== 每帧物理
func _physics_process(delta: float) -> void:
	if frozen:
		return
	if xr_on:
		_follow_head()
		_snap_turn_input()
		_grip_input()

	var mv := _move_input()
	if seated and mv.length() > 0.3:
		_stand_up()
	var cam := get_eye()

	var wh: float = water_fn.call(global_position.x, global_position.z) if water_fn.is_valid() else -INF
	var was := swimming
	swimming = global_position.y + CHEST < wh
	if swimming and not was and velocity.y < -1.0:
		splash.emit(global_position + Vector3(0, CHEST, 0))
		velocity.y *= 0.25                               # 入水: 水的阻力一下子把下落速度吃掉大半

	if swimming:
		_swim(delta, mv, cam, wh)
	else:
		_walk(delta, mv, cam)

	if global_position.y < -15.0:
		goto_point.emit(0)
	_update_held(delta)
	_update_lasers()


func _walk(delta: float, mv: Vector2, cam: Node3D) -> void:
	var fwd := -cam.global_basis.z
	fwd.y = 0.0
	fwd = fwd.normalized()
	var right := cam.global_basis.x
	right.y = 0.0
	right = right.normalized()
	var dir := right * mv.x + fwd * mv.y
	var spd := RUN if _running() else WALK
	velocity.x = dir.x * spd
	velocity.z = dir.z * spd
	if is_on_floor() and velocity.y < 0.0:
		velocity.y = 0.0
	velocity.y -= GRAVITY * delta
	var horiz := Vector3(velocity.x, 0, velocity.z) * delta
	if is_on_floor() and horiz.length() > 0.0001:
		_try_step_up(horiz)
	var before := global_position
	move_and_slide()
	if is_on_floor():
		var moved := Vector2(global_position.x - before.x, global_position.z - before.z).length()
		stride_acc += moved
		if stride_acc > STRIDE:
			stride_acc = 0.0
			step.emit(_floor_surface(), global_position)


## 游泳: 没有重力；朝视线方向游（含上下）；不按摇杆时浮力把人托到"头露出水面"
func _swim(delta: float, mv: Vector2, cam: Node3D, wh: float) -> void:
	var fwd := -cam.global_basis.z
	var right := cam.global_basis.x
	right.y = 0.0
	right = right.normalized()
	var dir := (fwd * mv.y + right * mv.x)
	var target := dir * SWIM
	if absf(fwd.y * mv.y) < 0.25:
		target.y = clampf(((wh - FLOAT_DEPTH) - global_position.y) * 2.0, -1.0, 1.6)   # 浮力: 往上快、往下慢
	if global_position.y > wh - FLOAT_DEPTH + 0.1 and target.y > 0.0:
		target.y = 0.0                                   # 游到水面就不再往上冲
	velocity = velocity.lerp(target, clampf(delta * 3.0, 0.0, 1.0))
	var horiz := Vector3(velocity.x, 0, velocity.z) * delta
	if horiz.length() > 0.0001:
		_try_step_up(horiz)                              # 能踩着泳池台阶走出来
	move_and_slide()


func _floor_surface() -> String:
	var q := PhysicsRayQueryParameters3D.create(global_position + Vector3(0, 0.3, 0), global_position - Vector3(0, 0.4, 0))
	q.exclude = [get_rid()]
	var r := get_world_3d().direct_space_state.intersect_ray(q)
	if r and r.collider and r.collider.has_meta("surface"):
		return r.collider.get_meta("surface")
	return "stone"


func _move_input() -> Vector2:
	if auto_move != Vector2.ZERO:
		return auto_move
	var v := Vector2.ZERO
	if xr_on:
		v = hands[0].ctrl.get_vector2("primary")
		if v.length() < 0.15:
			v = Vector2.ZERO
	else:
		v = Input.get_vector(&"ui_left", &"ui_right", &"ui_down", &"ui_up")
		if Input.is_physical_key_pressed(KEY_A): v.x -= 1.0
		if Input.is_physical_key_pressed(KEY_D): v.x += 1.0
		if Input.is_physical_key_pressed(KEY_W): v.y += 1.0
		if Input.is_physical_key_pressed(KEY_S): v.y -= 1.0
	return v.limit_length(1.0)


func _running() -> bool:
	if xr_on:
		return running
	return Input.is_physical_key_pressed(KEY_SHIFT)


## 台阶: 前面被挡住时，试试"抬高 36cm 再往前"能不能过；能过、而且落脚点是平地，就迈上去
func _try_step_up(motion: Vector3) -> void:
	var t := global_transform
	var probe := motion.normalized() * 0.12
	if not test_move(t, probe):
		return
	var t_up := t.translated(Vector3(0, STEP_UP, 0))
	if test_move(t, Vector3(0, STEP_UP, 0)):
		return
	if test_move(t_up, probe):
		return
	var t2 := t_up.translated(probe)
	var col := KinematicCollision3D.new()
	if not test_move(t2, Vector3(0, -STEP_UP, 0), col):
		return
	if col.get_normal().y < 0.7:
		return
	global_transform = t2
	move_and_collide(Vector3(0, -STEP_UP - 0.02, 0))


func _follow_head() -> void:
	var off := xr_cam.global_position - global_position
	off.y = 0.0
	if off.length() < 0.02:
		return
	var before := global_position
	move_and_collide(off)
	origin.global_position -= global_position - before


func _snap_turn_input() -> void:
	var x: float = hands[1].ctrl.get_vector2("primary").x
	if absf(x) < 0.3:
		snap_ready = true
	elif snap_ready and absf(x) > 0.7:
		snap_ready = false
		_turn_around_head(-SNAP_TURN if x > 0.0 else SNAP_TURN)


func _turn_around_head(angle: float) -> void:
	var cam := get_eye()
	var pivot := cam.global_position
	rotate_y(angle)
	var after := cam.global_position
	global_position += Vector3(pivot.x - after.x, 0, pivot.z - after.z)


# ================================================================== 坐下
func sit_at(top: Vector3) -> void:
	teleport_to(top + Vector3(0, 0.02, 0))
	seated = true
	if xr_on:
		origin.position.y = -maxf(xr_cam.position.y - SIT_EYE, 0.0)
	else:
		desk_cam.position.y = SIT_EYE


func _stand_up() -> void:
	seated = false
	origin.position.y = 0.0
	desk_cam.position.y = DESK_EYE


# ================================================================== 抓 / 扔
func _grip_input() -> void:
	for i in 2:
		var h: Dictionary = hands[i]
		var g: float = h.ctrl.get_float("grip")
		if not h.grip and g > 0.6:
			h.grip = true
			_grab(i)
		elif h.grip and g < 0.35:
			h.grip = false
			_release(i)


func _holder_xform(i: int) -> Transform3D:
	if i == 2:
		return desk_cam.global_transform * Transform3D(Basis(), Vector3(0.22, -0.22, -0.65))
	return hands[i].ctrl.global_transform


func _grab(i: int) -> bool:
	if held.has(i):
		return false
	var hx := _holder_xform(i)
	var best: RigidBody3D = null
	var bd := 0.3
	if i != 2:
		for rb in get_tree().get_nodes_in_group("grabbable"):
			var d: float = rb.global_position.distance_to(hx.origin)
			if d < bd and not _is_held(rb):
				bd = d
				best = rb
	var off := Transform3D.IDENTITY
	if best:
		off = hx.affine_inverse() * best.global_transform
	else:                                                   # 隔空吸: 激光指着的
		var hit := _probe(desk_ray if i == 2 else hands[i].ray)
		if hit.has("obj") and hit.obj is RigidBody3D and hit.obj.is_in_group("grabbable") \
				and not _is_held(hit.obj) and hit.point.distance_to(hx.origin) < 12.0:
			best = hit.obj
			off = Transform3D(Basis(), Vector3(0, 0, -0.12) if i != 2 else Vector3.ZERO)
	if best == null:
		return false
	best.freeze_mode = RigidBody3D.FREEZE_MODE_KINEMATIC
	best.freeze = true
	best.add_collision_exception_with(self)
	held[i] = {"rb": best, "off": off, "hist": []}
	return true


func _is_held(rb) -> bool:
	for k in held:
		if held[k].rb == rb:
			return true
	return false


func _release(i: int, throw_vel := Vector3.ZERO) -> void:
	if not held.has(i):
		return
	var e: Dictionary = held[i]
	held.erase(i)
	var rb: RigidBody3D = e.rb
	var v := Vector3.ZERO
	if throw_vel != Vector3.ZERO:
		v = throw_vel
	elif e.hist.size() > 1:
		var n: int = e.hist.size()
		v = (e.hist[n - 1] - e.hist[0]) / ((n - 1) / float(Engine.physics_ticks_per_second)) * 1.3   # 最近几帧手的平均速度，略放大
	rb.freeze = false
	rb.linear_velocity = v.limit_length(25.0)
	rb.angular_velocity = Vector3(randf_range(-3, 3), randf_range(-3, 3), randf_range(-3, 3))
	get_tree().create_timer(0.6).timeout.connect(func():
		if is_instance_valid(rb): rb.remove_collision_exception_with(self))


func _update_held(_delta: float) -> void:
	for i in held:
		var e: Dictionary = held[i]
		var x: Transform3D = _holder_xform(i) * e.off
		e.rb.global_transform = x
		e.hist.append(x.origin)
		if e.hist.size() > 6:
			e.hist.pop_front()


## 桌面: E / 右键
func desk_grab_toggle() -> void:
	if held.has(2):
		_release(2, velocity)
	else:
		_grab(2)


func desk_throw() -> void:
	if held.has(2):
		_release(2, -desk_cam.global_basis.z * 8.0 + Vector3(0, 1.5, 0) + velocity)


# ================================================================== 激光、瞬移、交互
func _update_lasers() -> void:
	if not xr_on:
		return
	for h in hands:
		var c: XRController3D = h.ctrl
		var show_laser := c.get_float("trigger") > 0.02 or c.is_button_pressed("trigger_touch")
		h.hit = _probe(h.ray)
		var length := 40.0
		var col := C_IDLE
		if h.hit.has("point"):
			length = c.global_position.distance_to(h.hit.point)
			if h.hit.grab:
				col = C_GRAB
			elif h.hit.interact:
				col = C_ACT
			elif h.hit.floor:
				col = C_FLOOR
			h.dot.global_position = h.hit.point
		h.laser.visible = show_laser
		h.dot.visible = show_laser and h.hit.has("point")
		h.laser.scale = Vector3(1, 1, length)
		h.laser.position = Vector3(0, 0, -length * 0.5)
		h.mat.albedo_color = col


func _probe(ray: RayCast3D) -> Dictionary:
	ray.force_raycast_update()
	if not ray.is_colliding():
		return {}
	var obj := ray.get_collider()
	return {
		"point": ray.get_collision_point(),
		"normal": ray.get_collision_normal(),
		"interact": obj != null and (obj.has_meta("interact") or obj.has_meta("seat")),
		"grab": obj != null and obj is RigidBody3D and obj.is_in_group("grabbable"),
		"floor": ray.get_collision_normal().y > 0.7,
		"obj": obj,
	}


func _act(hit: Dictionary) -> void:
	if not hit.has("point"):
		return
	if hit.obj.has_meta("interact"):
		(hit.obj.get_meta("interact") as Callable).call()
	elif hit.obj.has_meta("seat"):
		sit_at(hit.obj.get_meta("seat"))
	elif hit.floor and not hit.grab:
		teleport_to(hit.point)


func _on_button(name: String, c: XRController3D) -> void:
	match name:
		"trigger_click":
			for h in hands:
				if h.ctrl == c:
					_act(_probe(h.ray))
		"ax_button":
			time_cycle.emit()
		"menu_button":
			fx_cycle.emit()
		"by_button":
			next_point.emit()
		"primary_click":
			if c == hands[0].ctrl:
				running = not running


func teleport_to(p: Vector3, yaw_deg = null) -> void:
	velocity = Vector3.ZERO
	if seated:
		_stand_up()
	if xr_on:
		var off := xr_cam.global_position - global_position
		off.y = 0.0
		global_position = p - off
		if yaw_deg != null:
			_turn_around_head(deg_to_rad(yaw_deg) - xr_cam.global_rotation.y)
	else:
		global_position = p
		if yaw_deg != null:
			rotation.y = deg_to_rad(yaw_deg)
			desk_cam.rotation.x = 0.0


# ================================================================== 桌面模式输入
func _unhandled_input(event: InputEvent) -> void:
	if xr_on:
		return
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		rotate_y(-event.relative.x * 0.003)
		desk_cam.rotation.x = clampf(desk_cam.rotation.x - event.relative.y * 0.003, -1.45, 1.45)
	elif event is InputEventMouseButton and event.pressed:
		if Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
			Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
		elif event.button_index == MOUSE_BUTTON_LEFT:
			if held.has(2):
				desk_throw()
			else:
				_act(_probe(desk_ray))
		elif event.button_index == MOUSE_BUTTON_RIGHT:
			desk_grab_toggle()
	elif event is InputEventKey and event.pressed and not event.echo:
		match event.physical_keycode:
			KEY_ESCAPE:
				Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
			KEY_E:
				desk_grab_toggle()
			KEY_T:
				time_cycle.emit()
			KEY_G:
				toggle_gi.emit()
			KEY_F:
				fx_cycle.emit()
			KEY_TAB:
				next_point.emit()
			KEY_1, KEY_2, KEY_3, KEY_4, KEY_5, KEY_6, KEY_7, KEY_8, KEY_9:
				goto_point.emit(event.physical_keycode - KEY_1)



## 在眼前显示一行字，几秒后消失（VR 里没有屏幕 UI，只能放 3D 文字）
var _notice: Label3D


func notice(text: String, secs := 4.0) -> void:
	if _notice == null:
		_notice = Label3D.new()
		_notice.font = font
		_notice.font_size = 40
		_notice.pixel_size = 0.0008
		_notice.outline_size = 8
		_notice.no_depth_test = true
		_notice.fixed_size = false
		get_eye().add_child(_notice)
	_notice.position = Vector3(0, -0.12, -0.9)
	_notice.text = text
	_notice.visible = true
	var t := get_tree().create_timer(secs)
	t.timeout.connect(func(): if _notice and _notice.text == text: _notice.visible = false)
	print("[villa] ", text)
