# enemy.gd — an enemy ship that descends; a bullet destroys it (score), reaching the bottom
# or touching the player costs a life. Godot 4.x only.
extends Area2D

@export var speed: float = 150.0


func _ready() -> void:
	add_to_group("enemy")
	body_entered.connect(_on_body_entered)


func _physics_process(delta: float) -> void:
	global_position.y += speed * delta
	if global_position.y > 720.0:
		_cost_life()


func hit() -> void:
	# Called by a bullet that overlaps this enemy.
	var game := _game()
	if game and game.has_method("add_score"):
		game.add_score(1)
	queue_free()


func _on_body_entered(body: Node) -> void:
	if body.is_in_group("player"):
		_cost_life()


func _cost_life() -> void:
	var game := _game()
	if game and game.has_method("lose_life"):
		game.lose_life()
	queue_free()


func _game() -> Node:
	return get_tree().get_first_node_in_group("game")
