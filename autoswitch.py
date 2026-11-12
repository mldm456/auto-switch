#!/usr/bin/env python3
"""auto-switch: plug-ins, connectors and skills on when a job needs them, off when it no longer does.

Hook entry points (Claude Code passes the event as JSON on stdin):
  python3 autoswitch.py prompt   # UserPromptSubmit
  python3 autoswitch.py stop     # Stop

Plug-ins: written to <project>/.claude/settings.json "enabledPlugins"; Claude Code reads it when a session starts.
Connectors: only the chat can switch them, so the hook tells the chat which to switch.
Skills: the hook names the skill to load; Claude Code already loads skill bodies on demand.
Any error exits 0 with no output, so the mod can never block a prompt or a stop.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load_needs(project):
    """AUTO_SWITCH_NEEDS, then the project's .claude/auto-switch/needs.json, then the one beside this file."""
    for path in (os.environ.get("AUTO_SWITCH_NEEDS"),
                 os.path.join(project, ".claude", "auto-switch", "needs.json"),
                 os.path.join(HERE, "needs.json")):
        if path and os.path.isfile(path):
            with open(path) as f:
                return json.load(f)
    return {"needs": []}


def match(prompt, needs):
    """Return {"plugins": set, "connectors": set, "skills": set} for every need whose word is in the prompt."""
    out = {"plugins": set(), "connectors": set(), "skills": set()}
    for need in needs.get("needs", []):
        if any(re.search(r"\b" + re.escape(w) + r"\b", prompt, re.I) for w in need.get("words", [])):
            for kind in out:
                out[kind].update(need.get(kind, []))
    return out


def _read(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)  # atomic, so a crash never leaves half a settings file


def paths(project):
    return (os.path.join(project, ".claude", "settings.json"),
            os.path.join(project, ".claude", "auto-switch", "state.json"))


def on_prompt(event):
    project = event.get("cwd") or os.getcwd()
    settings_path, state_path = paths(project)
    want = match(event.get("prompt", ""), load_needs(project))
    # shortcut: no file lock; two chats in one folder at the same instant could race. Add fcntl.flock if that bites.
    state = _read(state_path, {"turn": 0, "items": {}})
    state["turn"] += 1
    items = state["items"]

    new_plugins = []
    if want["plugins"]:
        settings = _read(settings_path, {})
        enabled = settings.setdefault("enabledPlugins", {})
        for p in sorted(want["plugins"]):
            key = "plugin:" + p
            if key not in items and enabled.get(p) is not True:
                items[key] = {"prior": enabled.get(p, None)}
                enabled[p] = True
                new_plugins.append(p)
        if new_plugins:
            _write(settings_path, settings)

    new_connectors = []
    for c in sorted(want["connectors"]):
        key = "connector:" + c
        if key not in items:
            items[key] = {}
            new_connectors.append(c)

    for kind in ("plugins", "connectors"):
        for name in want[kind]:
            key = "%s:%s" % (kind[:-1], name)
            if key in items:  # a plug-in already on before the mod is never tracked
                items[key]["last"] = state["turn"]
    _write(state_path, state)

    lines = []
    for c in new_connectors:
        lines.append("auto-switch: this job needs the connector '%s'. Switch it on now with "
                     "set_session_connector_enabled(connector='%s', enabled=true); its tools arrive next turn." % (c, c))
    for p in new_plugins:
        lines.append("auto-switch: plug-in '%s' switched on in this folder's .claude/settings.json; "
                     "it loads when the next session starts here." % p)
    for s in sorted(want["skills"]):
        lines.append("auto-switch: load the skill '%s' with the Skill tool before you start." % s)
    if not lines:
        return None
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "\n".join(lines)}}


def on_stop(event):
    project = event.get("cwd") or os.getcwd()
    settings_path, state_path = paths(project)
    state = _read(state_path, None)
    if not state or not state.get("items"):
        return None
    keep = load_needs(project).get("keep_turns", 2)
    idle = [k for k, v in state["items"].items() if state["turn"] - v.get("last", 0) >= keep]
    if not idle:
        return None

    settings = None
    off_connectors = []
    for key in idle:
        kind, name = key.split(":", 1)
        if kind == "plugin":
            settings = settings if settings is not None else _read(settings_path, {})
            enabled = settings.setdefault("enabledPlugins", {})
            prior = state["items"][key].get("prior")
            if prior is None:
                enabled.pop(name, None)
            else:
                enabled[name] = prior
        else:
            off_connectors.append(name)
        del state["items"][key]
    if settings is not None:
        _write(settings_path, settings)
    _write(state_path, state)

    # Ask the chat once to switch connectors off; never re-block a stop the hook itself caused.
    if off_connectors and not event.get("stop_hook_active"):
        calls = "; ".join("set_session_connector_enabled(connector='%s', enabled=false)" % c for c in sorted(off_connectors))
        return {"decision": "block",
                "reason": "auto-switch: no longer needed, switch off: " + calls + ". Then stop."}
    return None


def main(argv):
    try:
        event = json.load(sys.stdin)
        out = {"prompt": on_prompt, "stop": on_stop}[argv[1]](event)
    except Exception:
        return 0
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
