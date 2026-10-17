extends Node
## 声音: 读取 make_assets.py 生成的 wav（godot/hd/ 里有同名 .wav/.ogg 就优先用），管理两条总线:
##   Amb（环境: 海浪、风、海鸥）—— 带低通滤波器。进屋关门 / 潜到水下时把高频切掉，听起来就"闷"了
##   SFX（脚步、开关、门……）
## 3D 声源（AudioStreamPlayer3D）按距离衰减、左右耳有差，所以戴耳机能听出海在哪边。

const SND_DIR := "res://model/snd/"
const HD_DIR := "res://hd/"
const LOOPS := ["ocean", "wind", "fire", "underwater", "radio"]

var streams := {}
var amb_bus := 0
var lowpass: AudioEffectLowPassFilter
var _muffle_target := 20000.0


func setup() -> void:
	amb_bus = _add_bus("Amb")
	_add_bus("SFX")
	lowpass = AudioEffectLowPassFilter.new()
	lowpass.cutoff_hz = 20000.0
	AudioServer.add_bus_effect(amb_bus, lowpass)
	var d := DirAccess.open(ProjectSettings.globalize_path(SND_DIR))
	if d == null:
		push_warning("没有声音文件（先运行 make_assets.py）")
		return
	for f in d.get_files():
		if f.ends_with(".wav"):
			var name := f.get_basename()
			var s = _load(name)
			if s:
				streams[name] = s


func _add_bus(name: String) -> int:
	var i := AudioServer.get_bus_index(name)
	if i >= 0:
		return i
	AudioServer.add_bus()
	i = AudioServer.bus_count - 1
	AudioServer.set_bus_name(i, name)
	AudioServer.set_bus_send(i, "Master")
	return i


func _load(name: String) -> AudioStream:
	var hd := ProjectSettings.globalize_path(HD_DIR + name)
	if FileAccess.file_exists(hd + ".ogg"):
		var o := AudioStreamOggVorbis.load_from_file(hd + ".ogg")
		if o:
			o.loop = name in LOOPS
			return o
	var path := hd + ".wav"
	if not FileAccess.file_exists(path):
		path = ProjectSettings.globalize_path(SND_DIR + name + ".wav")
	var s := AudioStreamWAV.load_from_file(path)
	if s and name in LOOPS:
		s.loop_mode = AudioStreamWAV.LOOP_FORWARD
		s.loop_begin = 0
		s.loop_end = s.data.size() / 2          # 16bit 单声道: 每帧 2 字节
	return s


## 一次性 3D 声音（播完自动删除）
func play_at(name: String, pos: Vector3, vol_db := 0.0, pitch_rand := 0.08, bus := "SFX") -> void:
	if not streams.has(name):
		return
	var p := AudioStreamPlayer3D.new()
	p.stream = streams[name]
	p.volume_db = vol_db
	p.pitch_scale = 1.0 + randf_range(-pitch_rand, pitch_rand)
	p.bus = bus
	p.unit_size = 4.0
	add_child(p)
	p.global_position = pos
	p.finished.connect(p.queue_free)
	p.play()


## 循环 3D 声源（挂在某个节点下）
func loop_3d(name: String, parent: Node, vol_db := 0.0, unit := 5.0, bus := "Amb", autoplay := true) -> AudioStreamPlayer3D:
	var p := AudioStreamPlayer3D.new()
	p.stream = streams.get(name)
	p.volume_db = vol_db
	p.unit_size = unit
	p.bus = bus
	p.max_db = 6.0
	parent.add_child(p)
	if autoplay and p.stream:
		p.play()
	return p


func loop_2d(name: String, vol_db := 0.0, bus := "Amb") -> AudioStreamPlayer:
	var p := AudioStreamPlayer.new()
	p.stream = streams.get(name)
	p.volume_db = vol_db
	p.bus = bus
	add_child(p)
	if p.stream:
		p.play()
	return p


## 闷音: 低通截止频率（20000 = 不闷）。平滑过渡，避免突变
func set_muffle(cutoff_hz: float) -> void:
	_muffle_target = cutoff_hz


func _process(delta: float) -> void:
	if lowpass:
		lowpass.cutoff_hz = lerpf(lowpass.cutoff_hz, _muffle_target, clampf(delta * 4.0, 0.0, 1.0))
