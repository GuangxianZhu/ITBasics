extends Node
## 自动测试（不用头显）:
##   godot --path godot -- --walktest   物理/交互测试，打印每项结果
##   godot --path godot -- --shots      各个场景截图，存到 user:// 目录
## 平时运行不会加载这些逻辑（main.gd 只在带参数时创建本节点）。

const W := preload("res://water_math.gd")
var m                          # main.gd
var results: Array = []


func run(args: PackedStringArray) -> void:
	await get_tree().create_timer(0.6).timeout
	if "--walktest" in args:
		await walktest()
	if "--shots" in args:
		await shots()
	get_tree().quit()


func _walk(dir: Vector2, secs: float) -> void:
	m.player.auto_move = dir
	await get_tree().create_timer(secs).timeout
	m.player.auto_move = Vector2.ZERO
	await get_tree().create_timer(0.3).timeout


func _check(name: String, ok: bool, info := "") -> void:
	results.append([name, ok])
	print("[test] %s %s  %s" % ["PASS" if ok else "FAIL", name, info])


func _find(nm: String) -> Node:
	return m.find_child(nm, true, false)


func _interact(nm: String) -> void:
	var n := _find(nm)
	for c in n.get_children():
		if c.has_meta("interact"):
			c.get_meta("interact").call()
			return
	push_error("no interact on " + nm)


func walktest() -> void:
	var p = m.player
	p.teleport_to(Vector3(-5.3, 0.35, 4.25), -90.0)
	await _walk(Vector2(0, 1), 3.5)
	_check("上楼梯", absf(p.global_position.y - 3.5) < 0.1, str(p.global_position))

	p.teleport_to(Vector3(-1.0, 0.35, 2.0), 0.0)
	await _walk(Vector2(0, 1), 4.0)
	_check("关着的门挡住人", p.global_position.z > -5.0 and p.global_position.z < -4.4, str(p.global_position))
	_interact("滑门_一楼_L")
	await get_tree().create_timer(1.6).timeout
	await _walk(Vector2(0, 1), 1.5)
	_check("开门走出去", p.global_position.z < -5.5, str(p.global_position))

	p.teleport_to(Vector3(-7.0, 0.35, -7.5), 90.0)
	await _walk(Vector2(0, 1), 1.5)
	_check("下到沙滩", p.global_position.y < 0.1 and p.global_position.x < -8.0, str(p.global_position))
	await _walk(Vector2(0, -1), 1.5)
	_check("迈回平台", absf(p.global_position.y - 0.3) < 0.05, str(p.global_position))

	p.teleport_to(Vector3(4.0, 0.3, -7.5), 0.0)          # 掉进泳池
	await get_tree().create_timer(4.0).timeout
	_check("泳池里浮起来", p.swimming and absf(p.global_position.y - (0.15 - 1.15)) < 0.15, str(p.global_position))
	p.global_position = Vector3(4.0, p.global_position.y, -8.55)
	p.rotation.y = deg_to_rad(-90.0)
	var out := false
	p.auto_move = Vector2(0, 1)
	for k in 60:                                          # 边走边看: 有没有一刻站上了平台
		await get_tree().create_timer(0.1).timeout
		if not p.swimming and p.global_position.y > 0.25 and p.global_position.x > 6.9:
			out = true
			break
	p.auto_move = Vector2.ZERO
	_check("踩台阶出泳池", out, str(p.global_position))

	p.teleport_to(Vector3(3.0, 0.3, -7.5), -90.0)
	await get_tree().create_timer(2.0).timeout
	p.desk_cam.rotation.x = -1.1
	await _walk(Vector2(0, 1), 1.2)
	await get_tree().create_timer(0.2).timeout
	_check("潜到水下（画面变蓝）", m.underwater, "eye=%s" % p.get_eye().global_position)
	p.desk_cam.rotation.x = 0.0

	p.teleport_to(Vector3(0, 2.0, -55.0), 0.0)            # 海里
	await get_tree().create_timer(3.0).timeout
	var wh: float = W.water_height(0, -55.0, m.wt)
	_check("海里游泳", p.swimming and absf(p.global_position.y - (wh - 1.15)) < 0.4, "y=%.2f 水面=%.2f" % [p.global_position.y, wh])

	p.teleport_to(Vector3(13.0, 0.05, -16.0), 0.0)
	await _walk(Vector2(0, 1), 6.0)
	_check("走上栈桥", absf(p.global_position.y - 1.0) < 0.1 and p.global_position.z < -24.0, str(p.global_position))

	var ball: RigidBody3D = null
	for rb in get_tree().get_nodes_in_group("grabbable"):
		if ball == null or rb.global_position.distance_to(Vector3(-1, 0, -15)) < ball.global_position.distance_to(Vector3(-1, 0, -15)):
			ball = rb
	p.teleport_to(Vector3(ball.global_position.x, 0.05, ball.global_position.z + 2.0), 0.0)
	await get_tree().create_timer(0.3).timeout
	p.desk_cam.look_at(ball.global_position)
	var got: bool = p._grab(2)
	await get_tree().create_timer(0.3).timeout
	_check("隔空抓起沙滩球", got and ball.freeze, str(ball.global_position))
	p.desk_cam.rotation.x = 0.2
	var start := ball.global_position
	p.desk_throw()
	await get_tree().create_timer(2.5).timeout
	var dist := Vector2(ball.global_position.x - start.x, ball.global_position.z - start.z).length()
	_check("扔出去", dist > 5.0 and not ball.freeze, "飞了 %.1fm" % dist)

	var sofa := _find("沙发座")
	var seat_body: Node = null
	for c in sofa.get_children():
		if c.has_meta("seat"):
			seat_body = c
	p.sit_at(seat_body.get_meta("seat"))
	await get_tree().create_timer(0.5).timeout
	_check("坐沙发", p.seated and absf(p.global_position.y - (0.3 + 0.42)) < 0.08, "y=%.2f" % p.global_position.y)
	await _walk(Vector2(0, 1), 0.4)
	_check("推摇杆站起来", not p.seated)

	_interact("冰箱门")
	await get_tree().create_timer(1.2).timeout
	_check("开冰箱", absf(rad_to_deg(m.fridge_pivot.rotation.y) + 100.0) < 2.0, "%.0f°" % rad_to_deg(m.fridge_pivot.rotation.y))
	_interact("篝火柴堆")
	_check("点篝火", m.fx.fire_on)
	_interact("电视屏幕")
	_check("开电视", m.tv_on)
	_interact("收音机")
	_check("开收音机", m.radio.playing)
	m.set_time(3, true)
	_check("夜晚灯塔亮", m.fx.lh_level > 0.9 and m.lights_on.get("一楼", false))
	var bp0: float = m.fx.boat_pivot.position.y
	await get_tree().create_timer(1.5).timeout
	_check("小船随浪起伏", absf(m.fx.boat_pivot.position.y - bp0) > 0.005, "%.3f → %.3f" % [bp0, m.fx.boat_pivot.position.y])
	var fails := results.filter(func(r): return not r[1]).size()
	print("[test] done: %d/%d passed" % [results.size() - fails, results.size()])


func _shot(name: String, pos: Vector3, yaw: float, pitch: float, time_i: int, wait := 1.2) -> void:
	m.set_time(time_i, true)
	m.player.teleport_to(pos, yaw)
	m.player.desk_cam.rotation.x = deg_to_rad(pitch)
	await get_tree().create_timer(wait).timeout
	m.get_viewport().get_texture().get_image().save_png("%s/shot_%s.png" % [OS.get_user_data_dir(), name])
	print("[shot] ", name)


func shots() -> void:
	_interact("滑门_一楼_L")
	_interact("滑门_一楼_R")
	await _shot("a_living", Vector3(0.5, 0.35, 1.2), 0, -5, 1)
	await _shot("b_kitchen", Vector3(1.5, 0.35, 0.8), 75, -8, 1)
	await _shot("c_tv_night", Vector3(3.6, 0.35, -2.0), 160, -5, 3)
	_interact("电视屏幕")
	await _shot("c_tv_night_on", Vector3(3.6, 0.35, -2.0), 160, -5, 3)
	await _shot("d_bedroom_morning", Vector3(1.6, 3.55, 1.8), 50, -8, 0)
	await _shot("e_pool", Vector3(7.6, 0.35, -9.6), 150, -12, 1)
	m.fx.set_fire(true)
	await _shot("f_bonfire_dusk", Vector3(-7.0, 0.05, -19.0), 10, -10, 2, 2.5)
	await _shot("g_beach_night", Vector3(3.0, 0.05, -30.0), 30, 2, 3, 2.0)
	await _shot("h_pier", Vector3(13.0, 1.05, -62.0), -20, -8, 1)
	await _shot("i_shore", Vector3(-4.0, 0.05, -29.0), -25, -12, 1)
	await _shot("j_aerial", Vector3(-26.0, 22.0, 18.0), -55, -30, 1)
	m.player.teleport_to(Vector3(4.0, 0.3, -7.5), 0.0)
	await get_tree().create_timer(1.5).timeout
	m.player.global_position.y = -2.2
	m.player.desk_cam.rotation.x = 0.1
	await get_tree().create_timer(0.6).timeout
	m.get_viewport().get_texture().get_image().save_png("%s/shot_k_underwater.png" % OS.get_user_data_dir())
	print("[shot] underwater=", m.underwater)
