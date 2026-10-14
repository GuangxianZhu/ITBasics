extends CharacterBody3D
## 玩家: VR 模式（Quest 3 两个手柄）+ 桌面模式（键鼠，没戴头显时自动用，方便测试）
##
## VR 操作:
##   左摇杆 = 走路（朝你看的方向）     右摇杆左右 = 每次转 30°（比平滑转向不容易晕）
##   食指放在扳机上 = 出现激光          按下扳机 = 指着地面就瞬移 / 指着门或开关就操作
##   A / X = 切换 下午 → 黄昏 → 夜晚    B / Y = 瞬移到下一个参观点位
##   左手握把按住 = 走快一点
## 桌面操作: WASD 走、鼠标看、左键 = 同扳机、T = 时间、Tab = 下一个点位、1~6 = 点位、Shift 跑、Esc 放开鼠标

signal time_cycle
signal next_point
signal goto_point(index: int)

const WALK := 1.8
const RUN := 3.6
const GRAVITY := 9.8
const STEP_UP := 0.36          # 能直接迈上去的台阶高度（台基 30cm、门槛 5cm 都靠它）
const SNAP_TURN := deg_to_rad(30.0)
const DESK_EYE := 1.65         # 桌面模式的眼睛高度；VR 模式用你真实的头高
const FAR := 6000.0            # 海面 3km 远，远裁剪要够

const C_IDLE := Color(0.55, 0.75, 1.0)
const C_FLOOR := Color(0.3, 1.0, 0.5)
const C_ACT := Color(1.0, 0.85, 0.2)

var xr_on := false
var origin: XROrigin3D
var xr_cam: XRCamera3D
var hands: Array = []          # 每只手: {ctrl, ray, laser, mat, dot, hit}
var desk_cam: Camera3D
var desk_ray: RayCast3D
var desk_hit := {}
var snap_ready := true
var auto_move := Vector2.ZERO    # 自动测试用（模拟摇杆）
var font: SystemFont


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
	floor_max_angle = deg_to_rad(46.0)    # 楼梯坡道 34°，要能走上去

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


func _make_hand(side: String) -> Dictionary:
	var c := XRController3D.new()
	c.tracker = side
	c.pose = &"aim"
	origin.add_child(c)

	var body := MeshInstance3D.new()           # 简单的手柄模型: 一根小棒
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

	if side == "left_hand":                    # 左手腕上的操作说明
		var tip := Label3D.new()
		tip.text = "左摇杆 走  右摇杆 转身\n扳机 瞬移/开门/开灯\nA/X 时间  B/Y 下个点位"
		tip.font = font
		tip.font_size = 28
		tip.pixel_size = 0.0006
		tip.position = Vector3(0, 0.06, 0.06)
		tip.rotation_degrees = Vector3(-50, 0, 0)
		tip.modulate = Color(1, 1, 1, 0.85)
		c.add_child(tip)

	c.button_pressed.connect(_on_button.bind(c))
	return {"ctrl": c, "ray": ray, "laser": laser, "mat": mat, "dot": dot, "hit": {}}


func _make_desktop_hud() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	var lbl := Label.new()
	lbl.text = "桌面模式（没检测到头显）  WASD 走 · 鼠标看 · 左键 瞬移/开门/开灯 · T 时间 · Tab 下个点位 · 1~6 点位 · Esc 放开鼠标"
	lbl.position = Vector2(12, 8)
	lbl.add_theme_font_override("font", font)
	lbl.add_theme_font_size_override("font_size", 16)
	lbl.add_theme_color_override("font_outline_color", Color.BLACK)
	lbl.add_theme_constant_override("outline_size", 4)
	layer.add_child(lbl)
	var cross := Label.new()
	cross.text = "+"
	cross.add_theme_font_size_override("font_size", 24)
	cross.set_anchors_preset(Control.PRESET_CENTER)
	cross.position -= Vector2(6, 16)
	layer.add_child(cross)


# ------------------------------------------------------------------ 每帧物理
func _physics_process(delta: float) -> void:
	if xr_on:
		_follow_head()
		_snap_turn_input()

	var mv := _move_input()
	var cam: Node3D = xr_cam if xr_on else desk_cam
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
	move_and_slide()

	if global_position.y < -15.0:              # 掉出世界就回到第一个点位
		goto_point.emit(0)

	_update_lasers()


func _move_input() -> Vector2:
	if auto_move != Vector2.ZERO:
		return auto_move
	var v := Vector2.ZERO
	if xr_on:
		v = hands[0].ctrl.get_vector2("primary")
		if v.length() < 0.15:
			v = Vector2.ZERO
	else:
		v = Input.get_vector(&"ui_left", &"ui_right", &"ui_down", &"ui_up")   # 方向键
		if Input.is_physical_key_pressed(KEY_A): v.x -= 1.0
		if Input.is_physical_key_pressed(KEY_D): v.x += 1.0
		if Input.is_physical_key_pressed(KEY_W): v.y += 1.0
		if Input.is_physical_key_pressed(KEY_S): v.y -= 1.0
	return v.limit_length(1.0)


func _running() -> bool:
	if xr_on:
		return hands[0].ctrl.get_float("grip") > 0.6
	return Input.is_physical_key_pressed(KEY_SHIFT)


## 台阶: 前面被挡住时，试试"抬高 36cm 再往前"能不能过；能过、而且落脚点是平地，就迈上去
## （胶囊底部是半径 22cm 的半球，比这矮的坎它自己会滑上去；30cm 的台基就得靠这里）
func _try_step_up(motion: Vector3) -> void:
	var t := global_transform
	var probe := motion.normalized() * 0.12          # 往前多探一点，比每帧位移(2cm)更可靠
	if not test_move(t, probe):
		return
	var t_up := t.translated(Vector3(0, STEP_UP, 0))
	if test_move(t, Vector3(0, STEP_UP, 0)):         # 头顶有东西
		return
	if test_move(t_up, probe):                       # 抬高后还是被挡 = 是墙，不是台阶
		return
	var t2 := t_up.translated(probe)
	var col := KinematicCollision3D.new()
	if not test_move(t2, Vector3(0, -STEP_UP, 0), col):
		return                                       # 前面没有落脚的地方
	if col.get_normal().y < 0.7:
		return
	global_transform = t2
	move_and_collide(Vector3(0, -STEP_UP - 0.02, 0))


## 房间尺度: 你在现实里走动时，让碰撞体跟着头走（这样墙才挡得住你的"身体"）
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
	var cam: Node3D = xr_cam if xr_on else desk_cam
	var pivot := cam.global_position
	rotate_y(angle)
	var after := cam.global_position
	global_position += Vector3(pivot.x - after.x, 0, pivot.z - after.z)


# ------------------------------------------------------------------ 激光、瞬移、交互
func _update_lasers() -> void:
	if not xr_on:
		desk_hit = _probe(desk_ray)
		return
	for h in hands:
		var c: XRController3D = h.ctrl
		var show_laser := c.get_float("trigger") > 0.02 or c.is_button_pressed("trigger_touch")
		h.hit = _probe(h.ray)
		var length := 40.0
		var col := C_IDLE
		if h.hit.has("point"):
			length = c.global_position.distance_to(h.hit.point)
			col = C_ACT if h.hit.interact else (C_FLOOR if h.hit.floor else C_IDLE)
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
		"interact": obj != null and obj.has_meta("interact"),
		"floor": ray.get_collision_normal().y > 0.7,
		"obj": obj,
	}


func _act(hit: Dictionary) -> void:
	if not hit.has("point"):
		return
	if hit.interact:
		(hit.obj.get_meta("interact") as Callable).call()
	elif hit.floor:
		teleport_to(hit.point)


func _on_button(name: String, c: XRController3D) -> void:
	match name:
		"trigger_click":
			for h in hands:
				if h.ctrl == c:
					_act(_probe(h.ray))
		"ax_button":
			time_cycle.emit()
		"by_button":
			next_point.emit()


## 瞬移: 把"你的头"放到目标点正上方（VR 里头和身体原点不一定重合）
func teleport_to(p: Vector3, yaw_deg = null) -> void:
	velocity = Vector3.ZERO
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


# ------------------------------------------------------------------ 桌面模式输入
func _unhandled_input(event: InputEvent) -> void:
	if xr_on:
		return
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		rotate_y(-event.relative.x * 0.003)
		desk_cam.rotation.x = clampf(desk_cam.rotation.x - event.relative.y * 0.003, -1.45, 1.45)
	elif event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		if Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
			Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
		else:
			_act(_probe(desk_ray))
	elif event is InputEventKey and event.pressed and not event.echo:
		match event.physical_keycode:
			KEY_ESCAPE:
				Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
			KEY_T:
				time_cycle.emit()
			KEY_TAB:
				next_point.emit()
			KEY_1, KEY_2, KEY_3, KEY_4, KEY_5, KEY_6, KEY_7, KEY_8, KEY_9:
				goto_point.emit(event.physical_keycode - KEY_1)
