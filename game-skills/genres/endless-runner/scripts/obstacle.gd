# obstacle.gd — scrolls left toward the runner at the game's current speed; jumping over it is the
# whole game. Touching the player ends the run. Godot 4.x.
extends Area2D

var _game: Node = null


func _ready() -> void:
	add_to_group("obstacle")
	_game = get_tree().get_first_node_in_group("game")
	body_entered.connect(_on_body_entered)


func _physics_process(delta: float) -> void:
	var spd: float = 320.0
	if _game != null:
		spd = _game.speed
	global_position.x -= spd * delta
	if global_position.x < -80.0:
		queue_free()


func _on_body_entered(body: Node) -> void:
	if body.is_in_group("player") and _game != null and _game.has_method("player_hit"):
		_game.player_hit()
