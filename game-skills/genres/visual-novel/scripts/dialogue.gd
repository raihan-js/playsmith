# dialogue.gd — Godot 4.x visual-novel dialogue controller template.
# Attach to a CanvasLayer that has:
#   - a RichTextLabel named "Text"      (the dialogue line)
#   - a Label named "Speaker"           (optional: who is talking)
#   - a VBoxContainer named "Choices"   (optional: branching choice Buttons)
# This is the deterministic template referenced by SKILL.md. Adjust `lines`/`choices`;
# the structure is correct for Godot 4 and should not be ported to 3.x.

extends CanvasLayer

# Each entry is "Speaker: text". Press ui_accept (Enter/Space) to advance.
@export var lines: Array[String] = [
	"Narrator: The lighthouse stood alone against the storm.",
	"Keeper: Another night, another watch.",
	"Keeper: ...but tonight something is different.",
]

# Optional branching: map a line index -> array of {text, goto} choices.
# When the current line has choices, the Choices container shows buttons instead of advancing.
var branches: Dictionary = {}

var _index: int = 0

@onready var _text: RichTextLabel = get_node_or_null("Text")
@onready var _speaker: Label = get_node_or_null("Speaker")
@onready var _choices: Node = get_node_or_null("Choices")


func _ready() -> void:
	_show_current()


func _unhandled_input(event: InputEvent) -> void:
	# Advance on accept, unless we are waiting on a choice.
	if event.is_action_pressed("ui_accept") and not _has_active_choices():
		advance()


func advance() -> void:
	_index = min(_index + 1, lines.size() - 1)
	_show_current()


func goto(index: int) -> void:
	_index = clamp(index, 0, lines.size() - 1)
	_show_current()


func _has_active_choices() -> bool:
	return _choices != null and _choices.get_child_count() > 0


func _show_current() -> void:
	if _text == null or _index >= lines.size():
		return
	var line: String = lines[_index]
	var speaker := ""
	var body := line
	if ":" in line:
		var parts := line.split(":", false, 1)
		speaker = parts[0].strip_edges()
		body = parts[1].strip_edges() if parts.size() > 1 else ""
	if _speaker:
		_speaker.text = speaker
	_text.text = body
	_render_choices()


func _render_choices() -> void:
	if _choices == null:
		return
	for child in _choices.get_children():
		child.queue_free()
	if not branches.has(_index):
		return
	for choice in branches[_index]:
		var button := Button.new()
		button.text = str(choice.get("text", "..."))
		var target: int = int(choice.get("goto", _index + 1))
		button.pressed.connect(func() -> void: goto(target))
		_choices.add_child(button)
