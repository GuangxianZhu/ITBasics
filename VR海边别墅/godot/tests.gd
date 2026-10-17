extends Node
## 自动测试（不用头显）:
##   godot --path godot -- --walktest   物理/交互测试，打印每项结果
##   godot --path godot -- --shots      各个场景截图，存到 user:// 目录
## 平时运行不会加载这些逻辑（main.gd 只在带参数时创建本节点）。
## 坐标是 Godot 的: x 同 Blender，z = -Blender y（大海在 -z）。

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


## 边走边检查: 有没有某一刻满足条件
func _walk_until(dir: Vector2, secs: float, cond: Callable) -> bool:
	m.player.auto_move = dir
	var ok := false
	for k in int(secs * 10):
		await get_tree().create_timer(0.1).timeout
		if cond.call():
			ok = true
			break
	m.player.auto_move = Vector2.ZERO
	await get_tree().create_timer(0.2).timeout
	return ok


func _check(name: String, ok: bool, info := "") -> void:
	results.append([name, ok])
	print("[test] %s %s  %s" % ["PASS" if ok else "FAIL", name, info])


func _find(nm: String) -> Node:
	return m.find_child(nm, true, false)


func _interact(nm: String) -> void:
	var n := _find(nm)
	if n == null:
		push_error("not found " + nm)
		return
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
	_check("开门走到外廊", p.global_position.z < -5.5 and absf(p.global_position.y - 0.3) < 0.05, str(p.global_position))

	p.teleport_to(Vector3(-8.0, 0.35, -7.0), 90.0)        # 面向 -x，从平台走下草坪
	await _walk(Vector2(0, 1), 1.5)
	_check("下到草坪", p.global_position.y < 0.1 and p.global_position.x < -9.0, str(p.global_position))
	await _walk(Vector2(0, -1), 1.5)
	_check("迈回平台", absf(p.global_position.y - 0.3) < 0.05, str(p.global_position))

	p.teleport_to(Vector3(-1.5, 0.4, -6.5), 0.0)           # 外廊往海走（两根柱子之间）: 掉进泳池
	await get_tree().create_timer(0.2).timeout
	await _walk(Vector2(0, 1), 2.0)
	await get_tree().create_timer(3.0).timeout
	_check("泳池里浮起来", p.swimming and absf(p.global_position.y - (W.POOL_WATER - 1.15)) < 0.2, str(p.global_position))
	p.global_position = Vector3(2.5, p.global_position.y, -8.95)
	p.rotation.y = deg_to_rad(-90.0)
	var out := await _walk_until(Vector2(0, 1), 6.0, func(): return not p.swimming and p.global_position.y > 0.25 and p.global_position.x > 6.0)
	_check("踩台阶出泳池", out, str(p.global_position))

	p.teleport_to(Vector3(-2.0, 0.4, -9.75), 0.0)
	await get_tree().create_timer(3.0).timeout
	p.desk_cam.rotation.x = -1.1
	await _walk(Vector2(0, 1), 1.2)
	await get_tree().create_timer(0.2).timeout
	_check("潜到水下（画面变蓝）", m.underwater, "eye=%s" % p.get_eye().global_position)
	p.desk_cam.rotation.x = 0.0

	p.teleport_to(Vector3(7.6, 0.4, -12.0), 0.0)            # 下水台阶: 一路走进海里
	var wet := await _walk_until(Vector2(0, 1), 8.0, func(): return p.swimming)
	_check("走下台阶进海里游泳", wet, str(p.global_position))
	p.teleport_to(Vector3(7.6, -4.0, -18.0), 180.0)          # 从海里游回台阶、一级级走上来
	var up := await _walk_until(Vector2(0, 1), 12.0, func(): return p.global_position.y > 0.25 and p.global_position.z > -12.7)
	_check("从海里爬上台阶", up, str(p.global_position))
	p.teleport_to(Vector3(0, 1.0, -40.0), 0.0)
	await get_tree().create_timer(3.0).timeout
	var wh: float = W.water_height(0, -40.0, m.wt)
	_check("海里浮着", p.swimming and absf(p.global_position.y - (wh - 1.15)) < 0.5, "y=%.2f 水面=%.2f" % [p.global_position.y, wh])
	p.teleport_to(Vector3(0, 0.4, -12.0), 0.0)               # 海边步道往海走: 玻璃栏杆挡住
	await _walk(Vector2(0, 1), 2.0)
	_check("海边栏杆挡住", p.global_position.z > -12.7 and p.global_position.y > 0.2, str(p.global_position))

	var ball: RigidBody3D = null
	for rb in get_tree().get_nodes_in_group("grabbable"):
		var cs: CollisionShape3D = rb.get_child(0)
		if cs.shape is SphereShape3D and cs.shape.radius > 0.2:
			ball = rb
			break
	p.teleport_to(Vector3(ball.global_position.x - 2.0, 0.05, ball.global_position.z), -90.0)   # 面向 +x
	await get_tree().create_timer(0.3).timeout
	p.desk_cam.look_at(ball.global_position)
	var got: bool = p._grab(2)
	await get_tree().create_timer(0.3).timeout
	_check("隔空抓起沙滩球", got and ball.freeze, str(ball.global_position))
	p.desk_cam.rotation = Vector3(0.2, 0, 0)
	var start := ball.global_position
	p.desk_throw()
	await get_tree().create_timer(2.5).timeout
	var dist := Vector2(ball.global_position.x - start.x, ball.global_position.z - start.z).length()
	_check("扔出去", dist > 5.0 and not ball.freeze, "飞了 %.1fm" % dist)

	var sofa: Node = m.find_child("AI_sofa_0*", true, false)
	var seat_body: Node = null
	for c in sofa.get_children():
		if c.has_meta("seat"):
			seat_body = c
	p.sit_at(seat_body.get_meta("seat"))
	await get_tree().create_timer(0.5).timeout
	_check("坐沙发", p.seated and absf(p.global_position.y - (0.3 + 0.45)) < 0.12, "y=%.2f" % p.global_position.y)
	await _walk(Vector2(0, 1), 0.4)
	_check("推摇杆站起来", not p.seated)

	_interact("冰箱门")
	await get_tree().create_timer(1.2).timeout
	_check("开冰箱", absf(rad_to_deg(m.fridge_pivot.rotation.y) + 100.0) < 2.0, "%.0f°" % rad_to_deg(m.fridge_pivot.rotation.y))
	_interact("烧烤台")
	_check("点烧烤炉", m.fx.fire_on)
	_interact("电视屏幕")
	_check("开电视", m.tv_on)
	_interact("收音机")
	_check("开收音机", m.radio.playing)
	_interact("KTV屏幕")
	_check("开 KTV", m.ktv_on and m.ktv_music.playing)
	m.set_time(3, true)
	_check("夜晚灯塔亮、自动开灯", m.fx.lh_level > 0.9 and m.lights_on.get("一楼", false))
	var bp0: float = m.fx.boat_pivot.position.y
	await get_tree().create_timer(1.5).timeout
	_check("小船随浪起伏", absf(m.fx.boat_pivot.position.y - bp0) > 0.005, "%.3f → %.3f" % [bp0, m.fx.boat_pivot.position.y])
	var fails := results.filter(func(r): return not r[1]).size()
	print("[test] done: %d/%d passed" % [results.size() - fails, results.size()])


func _shot(name: String, pos: Vector3, yaw: float, pitch: float, time_i: int, wait := 1.2) -> void:
	m.player.frozen = pos.y > 4.0 or pos.z < -13.0        # 空中/海上的机位: 别掉下去
	m.set_time(time_i, true)
	m.player.teleport_to(pos, yaw)
	m.player.desk_cam.rotation.x = deg_to_rad(pitch)
	await get_tree().create_timer(wait).timeout
	m.get_viewport().get_texture().get_image().save_png("%s/shot_%s.png" % [OS.get_user_data_dir(), name])
	print("[shot] ", name)


func shots() -> void:
	_interact("滑门_一楼_L")
	_interact("滑门_一楼_R")
	await _shot("a_living", Vector3(-0.5, 0.35, 1.8), -15, -6, 1, 2.0)
	await _shot("b_pool_walk", Vector3(-8.2, 0.35, -12.0), -110, -8, 1)
	await _shot("c_bay_bedroom", Vector3(4.2, 3.55, 0.0), 0, -6, 1)
	await _shot("d_billiard_ktv", Vector3(-0.2, 3.55, 3.0), 50, -10, 1)
	await _shot("e_from_sea", Vector3(4.0, 10.0, -45.0), 180, -10, 1)
	await _shot("f_terrace_dusk", Vector3(6.5, 0.35, -11.5), 140, -5, 2, 2.0)
	_interact("KTV屏幕")
	await _shot("g_ktv_night", Vector3(-1.0, 3.55, 1.0), 70, -5, 3, 2.0)
	m.fx.set_fire(true)
	await _shot("h_bbq_night", Vector3(9.0, 0.35, -6.5), -130, -8, 3, 2.0)
	await _shot("i_seawall", Vector3(14.0, 0.35, -12.2), 120, -25, 1)
	await _shot("j_aerial", Vector3(-26.0, 24.0, 22.0), -40, -28, 0)
