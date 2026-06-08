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
	_randomize_layout()
	_apply_generated_art()
	_update_hud()


func _randomize_layout() -> void:
	# Vary platform + coin placement each build so two platformers aren't identical. The floor and
	# player are untouched, so player_on_floor / player_not_falling stay reliable.
	var p1 := get_node_or_null("Platform1")
	if p1 and p1 is Node2D:
		p1.position = Vector2(randf_range(300.0, 560.0), randf_range(380.0, 500.0))
	var p2 := get_node_or_null("Platform2")
	if p2 and p2 is Node2D:
		p2.position = Vector2(randf_range(680.0, 940.0), randf_range(300.0, 460.0))
	for coin in get_tree().get_nodes_in_group("coin"):
		if coin is Node2D:
			coin.position = Vector2(randf_range(160.0, 1000.0), randf_range(220.0, 520.0))


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
	# Player sprite (scaled to a sane height so a 1024px generated PNG isn't gigantic).
	var player := _find_player(self)
	if player and ResourceLoader.exists("res://assets/player.png"):
		var ptex: Texture2D = load("res://assets/player.png")
		if ptex:
			_apply_sprite(player, ptex, 44.0)
	# Per-element art by group — contextual sprites for coins, spikes and the goal.
	var slot_heights := {"coin": 26.0, "spike": 30.0, "goal": 42.0}
	for slot in slot_heights:
		var path := "res://assets/%s.png" % slot
		if not ResourceLoader.exists(path):
			continue
		var stex: Texture2D = load(path)
		if not stex:
			continue
		for node in get_tree().get_nodes_in_group(slot):
			if node is Node2D:
				_apply_sprite(node, stex, slot_heights[slot])


func _apply_sprite(node: Node, tex: Texture2D, target_h: float) -> void:
	# Set the texture on the node's Sprite2D (creating one if needed), scaled to target_h px tall.
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
