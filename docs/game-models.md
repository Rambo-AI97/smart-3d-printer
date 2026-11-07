# Game and art models → printable STL

`p3d model FILE` turns any .glb/.obj/.fbx/.stl into one solid, watertight STL with Blender (headless):
it thickens thin parts, voxel-remeshes, optionally cuts a flat base and scales the longest side to `--length` mm.

`p3d game NAME` first exports a model that a Godot project builds in code, then runs the same conversion.
Presets live in `~/.config/p3d/presets.json` (kept out of the repo, since they point at your own projects):

```json
{
  "ship": {"game": "~/projects/my-game", "script": "res://scripts/ship_model.gd", "args": ["small"],
           "hide": "flag,ropes", "drop_thin": 0.05, "length": 85, "flat": 0.07,
           "note": "print with --supports --brim"}
}
```

Fields: `game` (Godot project folder), `script` (class that builds the model), `args` (constructor args),
`hide` (properties to hide), `drop_thin` (skip rope-thin meshes, model units), `length` mm, `flat` (fraction of
the height cut off for a base), optional `thicken` / `voxel`. Needs `godot` and `blender` on the PATH.
