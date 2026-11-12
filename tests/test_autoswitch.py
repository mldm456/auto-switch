import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import autoswitch  # noqa: E402

GH = "github@claude-plugins-official"


def run(cmd, event, script="autoswitch.py"):
    p = subprocess.run([sys.executable, os.path.join(ROOT, script), cmd], input=json.dumps(event),
                       capture_output=True, text=True)
    return p.returncode, (json.loads(p.stdout) if p.stdout.strip() else None)


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["AUTO_SWITCH_NEEDS"] = os.path.join(ROOT, "needs.json")
        self.settings = os.path.join(self.tmp, ".claude", "settings.json")

    def tearDown(self):
        os.environ.pop("AUTO_SWITCH_NEEDS", None)
        shutil.rmtree(self.tmp)

    def ev(self, name, **kw):
        with open(os.path.join(ROOT, "tests", "events", name + ".json")) as f:
            e = json.load(f)
        e["cwd"] = self.tmp
        e.update(kw)
        return e

    def prompt(self, name):
        return run("prompt", self.ev(name))

    def stop(self, **kw):
        return run("stop", self.ev("stop", **kw))

    def plugins(self):
        with open(self.settings) as f:
            return json.load(f).get("enabledPlugins", {})

    def pre(self, data):
        os.makedirs(os.path.dirname(self.settings))
        with open(self.settings, "w") as f:
            json.dump(data, f)

    def needs(self):
        with open(os.path.join(ROOT, "needs.json")) as f:
            return json.load(f)

    def test_01_match(self):
        m = autoswitch.match("open a pull request and email Sam", self.needs())
        self.assertEqual(m, {"plugins": {GH}, "connectors": {"Gmail"}, "skills": set()})

    def test_02_word_boundary(self):
        m = autoswitch.match("approve the prize", self.needs())
        self.assertEqual(m, {"plugins": set(), "connectors": set(), "skills": set()})

    def test_03_plain(self):
        self.assertEqual(self.prompt("prompt_plain"), (0, None))

    def test_04_github(self):
        rc, out = self.prompt("prompt_github")
        self.assertIn(GH, out["hookSpecificOutput"]["additionalContext"])
        self.assertIs(self.plugins()[GH], True)

    def test_05_already_on(self):
        self.pre({"enabledPlugins": {GH: True}})
        before = open(self.settings).read()
        self.assertEqual(self.prompt("prompt_github"), (0, None))
        self.assertEqual(open(self.settings).read(), before)
        self.prompt("prompt_plain")
        self.prompt("prompt_plain")
        self.stop()
        self.assertIs(self.plugins()[GH], True)

    def test_06_connector_and_skill(self):
        _, out = self.prompt("prompt_email_pdf")
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("set_session_connector_enabled(connector='Gmail', enabled=true)", ctx)
        self.assertIn("skill 'pdf'", ctx)

    def test_07_stop_keeps_recent(self):
        self.prompt("prompt_github")
        self.assertEqual(self.stop(), (0, None))
        self.assertIs(self.plugins()[GH], True)

    def _idle_email(self):
        self.prompt("prompt_email_pdf")
        self.prompt("prompt_plain")
        self.prompt("prompt_plain")

    def test_08_stop_connector_off(self):
        self._idle_email()
        _, out = self.stop()
        self.assertEqual(out["decision"], "block")
        self.assertIn("connector='Gmail', enabled=false", out["reason"])
        self.assertEqual(self.stop(), (0, None))

    def test_09_stop_restores_plugin(self):
        self.prompt("prompt_github")
        self.prompt("prompt_plain")
        self.prompt("prompt_plain")
        self.stop()
        self.assertNotIn(GH, self.plugins())

    def test_09b_prior_false(self):
        self.pre({"enabledPlugins": {GH: False}})
        self.prompt("prompt_github")
        self.prompt("prompt_plain")
        self.prompt("prompt_plain")
        self.stop()
        self.assertIs(self.plugins()[GH], False)

    def test_10_stop_hook_active(self):
        self._idle_email()
        self.assertEqual(self.stop(stop_hook_active=True), (0, None))
        with open(os.path.join(self.tmp, ".claude", "auto-switch", "state.json")) as f:
            self.assertEqual(json.load(f)["items"], {})

    def test_11_bad_input(self):
        p = subprocess.run([sys.executable, os.path.join(ROOT, "autoswitch.py"), "prompt"],
                           input="not json", capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout), (0, ""))

    def test_12_project_override(self):
        os.environ.pop("AUTO_SWITCH_NEEDS")
        d = os.path.join(self.tmp, ".claude", "auto-switch")
        os.makedirs(d)
        with open(os.path.join(d, "needs.json"), "w") as f:
            json.dump({"needs": [{"words": ["deploy"], "skills": ["deploy-check"]}]}, f)
        _, out = run("prompt", self.ev("prompt_plain", prompt="deploy it now"))
        self.assertIn("deploy-check", out["hookSpecificOutput"]["additionalContext"])

    def _script(self, name):
        return subprocess.run([sys.executable, os.path.join(ROOT, name), self.tmp],
                              capture_output=True, text=True)

    def test_13_round_trip(self):
        original = b'{"model": "x"}\n'
        self.pre({})
        with open(self.settings, "wb") as f:
            f.write(original)
        self._script("install.py")
        self._script("install.py")
        with open(self.settings) as f:
            hooks = json.load(f)["hooks"]
        for event in ("UserPromptSubmit", "Stop"):
            self.assertEqual(len(hooks[event]), 1)
            self.assertIn("autoswitch.py", hooks[event][0]["hooks"][0]["command"])
        backup = self.settings + ".auto-switch-backup"
        self.assertTrue(os.path.exists(backup))
        self._script("uninstall.py")
        with open(self.settings, "rb") as f:
            self.assertEqual(f.read(), original)
        self.assertFalse(os.path.exists(backup))

    def test_14_no_settings(self):
        self._script("install.py")
        marker = self.settings + ".auto-switch-absent"
        self.assertTrue(os.path.exists(self.settings) and os.path.exists(marker))
        self._script("uninstall.py")
        self.assertFalse(os.path.exists(self.settings) or os.path.exists(marker))


if __name__ == "__main__":
    unittest.main()
