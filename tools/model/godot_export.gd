extends SceneTree
## Export a code-built Godot model (any script that builds meshes in _ready) to .glb.
## Only visible meshes are exported, flattened to world space.
## Env: GD_SCRIPT=res://scripts/x.gd  GD_ARGS='["faering"]' (constructor args, JSON)
##      GD_HIDE='oars,flag,telltales' (properties holding a Node or Array of Nodes to hide)
##      OUT=/abs/path/out.glb
## Run: godot --headless --path GAME_DIR -s godot_export.gd   (p3d godot does this)
var model: Node3D
var frames := 0

func _init() -> void:
	var scr: Script = load(OS.get_environment("GD_SCRIPT"))
	var args: Array = JSON.parse_string(OS.get_environment("GD_ARGS")) if OS.get_environment("GD_ARGS") != "" else []
	model = scr.new.callv(args)
	root.add_child(model)

func _process(_d: float) -> bool:
	frames += 1
	if frames == 4:
		for p in OS.get_environment("GD_HIDE").split(",", false):
			var v = model.get(p.strip_edges())
			if v is Node3D: v.visible = false
			elif v is Array:
				for n in v:
					if n is Node3D: n.visible = false
	if frames < 6:
		return false
	var flat := Node3D.new()
	root.add_child(flat)
	_copy(model, flat)
	var doc := GLTFDocument.new()
	var st := GLTFState.new()
	doc.append_from_scene(flat, st)
	var err := doc.write_to_filesystem(st, OS.get_environment("OUT"))
	print("EXPORT ", OS.get_environment("OUT"), " err=", err, " meshes=", flat.get_child_count())
	return true

func _copy(n: Node, out: Node3D) -> void:
	if n is Node3D and not n.is_visible_in_tree():
		return
	if n is MeshInstance3D and n.mesh:
		var m := MeshInstance3D.new()
		m.mesh = n.mesh
		out.add_child(m)
		m.global_transform = n.global_transform
	for c in n.get_children():
		_copy(c, out)
