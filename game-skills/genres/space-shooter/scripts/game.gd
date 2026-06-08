# game.gd — space-shooter director (Godot 4.x). Spawns enemy waves on a timer, tracks score and
# lives, and applies generated art at runtime (background + ship + enemies) so every game looks
# distinct without editing scenes. Attach to the Main (Node2D).
extends Node2D

@export var spawn_interval: float = 0.8

var score: int = 0
var lives: int = 3
var _timer: float = 0.0
var _view: Vector2 = Vector2(1152, 648)

@onready var score_label: Label = get_node_or_null("HUD/Score")
@onready var lives_label: Label = get_node_or_null("HUD/Lives")


func _ready() -> void:
	add_to_group("game")
	_view = _design_size()
	_apply_generated_art()
	_update_hud()
	_spawn_enemy()  # start the action immediately (and guarantees the first wave exists)


func _physics_process(delta: float) -> void:
	if lives <= 0:
		return
	_timer -= delta
	if _timer <= 0.0:
		_spawn_enemy()
		_timer = spawn_interval


func _spawn_enemy() -> void:
	var scene: PackedScene = load("res://Enemy.tscn")
	if scene == null:
		print("PLAYSMITH_DEBUG enemy_scene_null")
		return
	var enemy: Node = scene.instantiate()
	add_child(enemy)
	enemy.global_position = Vector2(randf_range(60.0, _view.x - 60.0), -40.0)
	if ResourceLoader.exists("res://assets/enemy.png"):
		_apply_sprite(enemy, load("res://assets/enemy.png"), 48.0)


func _design_size() -> Vector2:
	# The project's design resolution (NOT get_viewport_rect, which is tiny in headless verify).
	var w: float = float(ProjectSettings.get_setting("display/window/size/viewport_width", 1152))
	var h: float = float(ProjectSettings.get_setting("display/window/size/viewport_height", 648))
	return Vector2(w, h)


func add_score(n: int) -> void:
	score += n
	_update_hud()


func lose_life() -> void:
	lives -= 1
	_update_hud()
	if lives <= 0 and score_label:
		score_label.text = "Game Over — Score: %d" % score


func _update_hud() -> void:
	if score_label and lives > 0:
		score_label.text = "Score: %d" % score
	if lives_label:
		lives_label.text = "Lives: %d" % max(lives, 0)


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
		var ship := get_tree().get_first_node_in_group("player")
		if ship:
			_apply_sprite(ship, load("res://assets/player.png"), 56.0)


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
