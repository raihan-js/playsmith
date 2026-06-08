# game.gd — Godot 4.x platformer game controller (wires coins/spikes/goal + a score HUD).
# Attach to the Main (Node2D). It finds nodes in the "coin", "spike", and "goal" groups and
# connects their Area2D.body_entered signals — so adding more gameplay is just adding nodes to
# those groups (no scene re-wiring needed). Godot 4 only.

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
	_update_hud()


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
