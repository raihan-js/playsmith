extends Node

var _frames := 0

func _ready() -> void:
	var target := OS.get_environment("PLAYSMITH_TARGET_SCENE")
	if target != "":
		var packed = load(target)
		if packed:
			add_child(packed.instantiate())

func _process(_delta: float) -> void:
	_frames += 1
	if _frames == 15:
		var out := OS.get_environment("PLAYSMITH_SCREENSHOT")
		if out != "":
			var img := get_viewport().get_texture().get_image()
			img.save_png(out)
		get_tree().quit()
