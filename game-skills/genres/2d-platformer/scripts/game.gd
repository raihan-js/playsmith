# game.gd — Godot 4.x platformer game controller (gameplay + applies generated art).
# Attach to the Main (Node2D). Wires coins/spikes/goal by group and, at runtime, applies any
# generated art at res://assets/background.png and res://assets/player.png (so graphics are
# reliable without editing scene files). Godot 4 only.

extends Node2D

var score: int = 0
var won: bool = false

@onready var hud: Label = get_node_or_null("HUD/Score")


func _ready() -> void:
	for coin in get_tree().get_nodes_in_group("coin"):
		coin.body_entered.connect(_on_coin.bind(coin))
	for spike in get_tree().get_nodes_in_group("spike"):
		spike.body_entered.connect(_on_spike)
	for goal in get_tree().get_nodes_in_group("goal"):
		goal.body_entered.connect(_on_goal)
	_apply_generated_art()
	_update_hud()


func _apply_generated_art() -> void:
	# Background (covers the camera view).
	var bg_path := "res://assets/background.png"
	var bg := get_node_or_null("Background")
	if bg and ResourceLoader.exists(bg_path):
		var tex: Texture2D = load(bg_path)
		if tex:
			bg.texture = tex
			var w := float(tex.get_width())
			var h := float(tex.get_height())
			if w > 0.0 and h > 0.0:
				bg.scale = Vector2(1152.0 / w, 648.0 / h)
			print("PLAYSMITH_BG_APPLIED")
	# Player sprite (optional).
	var p_path := "res://assets/player.png"
	if ResourceLoader.exists(p_path):
		var ptex: Texture2D = load(p_path)
		var player := _find_player(self)
		if ptex and player:
			var spr := player.get_node_or_null("Sprite2D")
			if spr and spr is Sprite2D:
				spr.texture = ptex


func _find_player(node: Node) -> Node:
	if node is CharacterBody2D:
		return node
	for child in node.get_children():
		var found := _find_player(child)
		if found:
			return found
	return null


func _on_coin(body: Node, coin: Node) -> void:
	if body is CharacterBody2D:
		coin.queue_free()
		score += 1
		_update_hud()


func _on_spike(body: Node) -> void:
	if body is CharacterBody2D and not won:
		get_tree().reload_current_scene()


func _on_goal(body: Node) -> void:
	if body is CharacterBody2D:
		won = true
		if hud:
			hud.text = "You win!  Coins: %d" % score


func _update_hud() -> void:
	if hud and not won:
		hud.text = "Coins: %d" % score
