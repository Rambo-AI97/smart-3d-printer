"""Print ideas board: one Markdown file (default <data_dir>/../ideas.md), sections per status, one line per idea.

  - [#3] Text with #tags | note: free text | model: phone_stand.scad | job: 20261109-1120-phone_stand

Edit it by hand (any Markdown editor): move a line under another heading to change its status; a line without [#id] gets one on the next save.
"""
import re

from . import config

STATUSES = ["idea", "maybe", "needs-thought", "planned", "printed", "dropped"]
HEAD = {"idea": "Idea", "maybe": "Maybe", "needs-thought": "Needs thought", "planned": "Planned", "printed": "Printed",
        "dropped": "Dropped"}
_BY_HEAD = {v.lower(): k for k, v in HEAD.items()}
LINE = re.compile(r"^\s*-\s+(?:\[#(\d+)\]\s*)?(.*\S)\s*$")
FIELDS = ("note", "model", "job")


def parse_line(text):
    """'Text #tag | note: x | job: y' -> {text, tags, note, model, job}."""
    parts = [p.strip() for p in text.split(" | ")]
    d = {"text": parts[0], "note": "", "model": "", "job": ""}
    for p in parts[1:]:
        k, _, v = p.partition(":")
        if k.strip() in FIELDS:
            d[k.strip()] = v.strip()
        else:
            d["note"] = (d["note"] + " " + p).strip()
    d["tags"] = re.findall(r"(?<!\S)#([\w-]+)", d["text"])
    return d


def parse(md):
    items, status = [], "idea"
    for raw in md.splitlines():
        h = re.match(r"^##\s+(.*\S)", raw)
        if h:
            status = _BY_HEAD.get(h.group(1).strip().lower(), status)
            continue
        m = LINE.match(raw)
        if m and m.group(2) and not re.match(r"^\[[ x]\]", m.group(2)):
            items.append({"id": int(m.group(1)) if m.group(1) else None, "status": status, **parse_line(m.group(2))})
    nxt = max([i["id"] or 0 for i in items] + [0]) + 1
    for i in items:
        if i["id"] is None:
            i["id"], nxt = nxt, nxt + 1
    return items


def render(items):
    out = ["# Print ideas", "", "<!-- p3d idea add/list/move/done edits this file. Hand edits are fine: "
           "move a line under another heading to change its status. -->", ""]
    for st in STATUSES:
        out.append(f"## {HEAD[st]}")
        for i in [x for x in items if x["status"] == st]:
            line = f"- [#{i['id']}] {i['text']}"
            for k in FIELDS:
                if i.get(k):
                    line += f" | {k}: {i[k]}"
            out.append(line)
        out.append("")
    return "\n".join(out)


def load():
    try:
        return parse(config.get().ideas.read_text())
    except FileNotFoundError:
        return []


def save(items):
    p = config.get().ideas
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render(items))


def add(items, text, status="idea", tags=(), note="", model=""):
    if status not in STATUSES:
        raise ValueError(f"status: {', '.join(STATUSES)}")
    text = text.strip()
    for t in tags:
        if f"#{t}" not in text:
            text += f" #{t.lstrip('#')}"
    nid = max([i["id"] for i in items] + [0]) + 1
    items.append({"id": nid, "status": status, "note": note, "model": model, "job": "", **parse_line(text)})
    return items[-1]


def get(items, iid):
    for i in items:
        if i["id"] == int(iid):
            return i
    raise ValueError(f"no idea #{iid} (p3d idea list)")


def move(items, iid, status):
    if status not in STATUSES:
        raise ValueError(f"status: {', '.join(STATUSES)}")
    i = get(items, iid)
    i["status"] = status
    return i


def done(items, iid, job):
    i = move(items, iid, "printed")
    i["job"] = job
    return i


def show(i):
    return f"#{i['id']:<3} {i['status']:13} {i['text']}" + (f"  [{i['job']}]" if i.get("job") else "")


def cmd(a):
    items = load()
    try:
        if a.action == "add":
            it = add(items, " ".join(a.args), a.status or "idea", a.tag or [])
            save(items)
            print("added", show(it))
        elif a.action == "move":
            it = move(items, a.args[0], a.args[1])
            save(items)
            print(show(it))
        elif a.action == "done":
            if not a.job:
                raise ValueError("p3d idea done ID --job NAME")
            it = done(items, a.args[0], a.job)
            save(items)
            print(show(it))
        else:
            sel = [i for i in items if not a.status or i["status"] == a.status]
            for i in sel:
                print(show(i))
            if not sel:
                print("no ideas" + (f" with status {a.status}" if a.status else "") + f" [{config.get().ideas}]")
    except (ValueError, IndexError) as e:
        usage = "usage: p3d idea add TEXT | list | move ID STATUS | done ID --job NAME"
        raise SystemExit(str(e) if isinstance(e, ValueError) else usage) from None
