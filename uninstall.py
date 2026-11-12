#!/usr/bin/env python3
"""Remove the auto-switch hooks by restoring settings.json as it was before install.

Same arguments as install.py. Note: restoring the backup also drops any settings change made after install.
"""
import os
import shutil
import sys

from install import settings_path


def main(argv):
    path = settings_path(argv)
    backup, marker = path + ".auto-switch-backup", path + ".auto-switch-absent"
    if os.path.exists(backup):
        shutil.copy2(backup, path)
        os.remove(backup)
        print("restored " + path + " from backup")
    elif os.path.exists(marker):
        if os.path.exists(path):
            os.remove(path)
        os.remove(marker)
        print("removed " + path + " (it did not exist before install)")
    else:
        print("no backup found; nothing restored")
        return 1
    if "--user" not in argv:
        state = os.path.join(os.path.dirname(path), "auto-switch", "state.json")
        if os.path.exists(state):
            os.remove(state)
            print("removed " + state)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
