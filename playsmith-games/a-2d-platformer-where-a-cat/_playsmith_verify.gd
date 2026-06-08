extends Node

var _frames := 0
var _player: Node = null
var _start_y := 0.0
var _max_y := -1.0e20

func _ready() -> void:
	var target := OS.get_environment("PLAYSMITH_TARGET_SCENE")
	if target != "":
		var packed = load(target)
		if packed:
			add_child(packed.instantiate())
	_player = _find_body(self)

func _find_body(node: Node) -> Node:
	if node is CharacterBody2D or node is CharacterBody3D:
		return node
	for child in node.get_children():
		var found = _find_body(child)
		if found != null:
			return found
	return null

func _physics_process(_delta: float) -> void:
	_frames += 1
	if _player != null and (_player is Node2D or _player is Node3D):
		var y: float = _player.global_position.y
		if _frames == 1:
			_start_y = y
		_max_y = max(_max_y, y)
	if _frames >= 90:
		_emit()

func _has_ui(node: Node) -> bool:
	if node is Label or node is RichTextLabel or node is Button:
		return true
	for child in node.get_children():
		if _has_ui(child):
			return true
	return false

func _emit() -> void:
	var wanted := OS.get_environment("PLAYSMITH_CHECKS").split(",", false)
	var on_floor := false
	if _player != null and _player.has_method("is_on_floor"):
		on_floor = _player.is_on_floor()
	var fell := (_max_y - _start_y) > 2000.0
	var results := {
		"player_exists": _player != null,
		"player_on_floor": on_floor,
		"player_not_falling": not fell,
		"scene_loads": get_child_count() > 0,
		"has_dialogue_ui": _has_ui(self),
	}
	for key in results.keys():
		if wanted.is_empty() or wanted.has(key):
			print("PLAYSMITH_ASSERT ", key, "=", "true" if results[key] else "false")
	get_tree().quit()
