#!/usr/bin/env python3
"""Install the auto-switch hooks.

Usage: python3 install.py [PROJECT_DIR]   (default: current dir)
       python3 install.py --user          (~/.claude/settings.json)
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def settings_path(argv):
    if "--user" in argv:
        return os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
    args = [a for a in argv[1:] if not a.startswith("--")]
    return os.path.join(os.path.abspath(args[0] if args else "."), ".claude", "settings.json")


def main(argv):
    path = settings_path(argv)
    backup, marker = path + ".auto-switch-backup", path + ".auto-switch-absent"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(backup) or os.path.exists(marker):
        print("backup already present; kept")
    elif os.path.exists(path):
        shutil.copy2(path, backup)
        print("backed up to " + backup)
    else:
        open(marker, "w").close()
        print("no settings file; marker " + marker)

    settings = {}
    if os.path.exists(path):
        with open(path) as f:
            settings = json.load(f)
    script = os.path.join(HERE, "autoswitch.py")
    for event, arg in (("UserPromptSubmit", "prompt"), ("Stop", "stop")):
        entries = settings.setdefault("hooks", {}).setdefault(event, [])
        if not any("autoswitch.py" in h.get("command", "") for e in entries for h in e.get("hooks", [])):
            entries.append({"hooks": [{"type": "command", "command": 'python3 "%s" %s' % (script, arg)}]})
    with open(path, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    print("changed " + path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
