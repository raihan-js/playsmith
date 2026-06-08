# bullet.gd — a player projectile that travels up and destroys the first enemy it overlaps.
# Godot 4.x only.
extends Area2D

@export var speed: float = 560.0


func _ready() -> void:
	add_to_group("bullet")
	area_entered.connect(_on_area_entered)


func _physics_process(delta: float) -> void:
	global_position.y -= speed * delta
	if global_position.y < -40.0:
		queue_free()


func _on_area_entered(area: Area2D) -> void:
	if area.is_in_group("enemy"):
		if area.has_method("hit"):
			area.hit()
		queue_free()
