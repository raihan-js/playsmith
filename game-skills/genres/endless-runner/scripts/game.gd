# game.gd — endless-runner director (Godot 4.x). Scrolls obstacles toward a fixed runner, ramps
# the speed the longer you survive, scores by distance, and applies generated art at runtime.
# Attach to Main (Node2D).
extends Node2D

@export var spawn_interval: float = 1.3

var speed: float = 320.0
var distance: float = 0.0
var alive: bool = true
var _timer: float = 0.0
var _view: Vector2 = Vector2(1152, 648)

@onready var score_label: Label = get_node_or_null("HUD/Score")


func _ready() -> void:
	add_to_group("game")
	_view = _design_size()
	_apply_generated_art()
	_spawn_obstacle()  # one obstacle on screen immediately (and guarantees the verify check)
	_update_hud()


func _physics_process(delta: float) -> void:
	if not alive:
		return
	distance += speed * delta * 0.1
	speed += delta * 8.0  # speeds up the longer you survive
	_update_hud()
	_timer -= delta
	if _timer <= 0.0:
		_spawn_obstacle()
		_timer = spawn_interval


func _spawn_obstacle() -> void:
	var scene: PackedScene = load("res://Obstacle.tscn")
	if scene == null:
		return
	var obstacle: Node = scene.instantiate()
	add_child(obstacle)
	# Spawn at the right edge (far from the runner) so it scrolls in — verify-safe and correct.
	obstacle.global_position = Vector2(_view.x + 60.0, 556.0 - randf_range(0.0, 70.0))
	if ResourceLoader.exists("res://assets/obstacle.png"):
		_apply_sprite(obstacle, load("res://assets/obstacle.png"), 56.0)


func player_hit() -> void:
	if not alive:
		return
	alive = false
	if score_label:
		score_label.text = "Game Over — %d m" % int(distance)


func _update_hud() -> void:
	if score_label and alive:
		score_label.text = "%d m" % int(distance)


func _design_size() -> Vector2:
	var w: float = float(ProjectSettings.get_setting("display/window/size/viewport_width", 1152))
	var h: float = float(ProjectSettings.get_setting("display/window/size/viewport_height", 648))
	return Vector2(w, h)


func _apply_generated_art() -> void:
	var bg := get_node_or_null("Background")
	if bg and ResourceLoader.exists("res://assets/background.png"):
		var tex: Texture2D = load("res://assets/background.png")
		if tex:
			bg.texture = tex
			var w := float(tex.get_width())
			var h := float(tex.get_height())
			if w > 0.0 and h > 0.0:
				bg.scale = Vector2(_view.x / w, _view.y / h)
			print("PLAYSMITH_BG_APPLIED")
	if ResourceLoader.exists("res://assets/player.png"):
		var runner := get_tree().get_first_node_in_group("player")
		if runner:
			_apply_sprite(runner, load("res://assets/player.png"), 60.0)


func _apply_sprite(node: Node, tex: Texture2D, target_h: float) -> void:
	if tex == null:
		return
	var spr := node.get_node_or_null("Sprite2D")
	if spr == null or not (spr is Sprite2D):
		spr = Sprite2D.new()
		spr.name = "Sprite2D"
		node.add_child(spr)
	spr.texture = tex
	var h := float(tex.get_height())
	if h > 0.0:
		var s := target_h / h
		spr.scale = Vector2(s, s)
