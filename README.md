# auto-switch

A small mod for [Claude Code](https://claude.com/claude-code) that switches plug-ins, connectors and skills **on when a job needs them and off when it no longer does**, with no step by you.

Every plug-in, connector and skill you keep loaded costs context on every turn. Most are needed for one job in ten. auto-switch keeps them off until your prompt says the job needs them, then puts them away again.

Python 3 standard library only. No network calls. Two hooks and one JSON file.

## How it works

1. **You write a need-list** (`needs.json`): job words mapped to the plug-ins, connectors and skills that job needs.
2. **A `UserPromptSubmit` hook** reads each prompt. When a job word appears, it:
   - turns the **plug-in** on in the project's `.claude/settings.json` (`enabledPlugins`);
   - tells the chat to turn the **connector** on (`set_session_connector_enabled`);
   - tells the chat to load the **skill**.
3. **A `Stop` hook** runs at the end of each turn. When a plug-in or connector has not been needed for `keep_turns` prompts (default 2), it:
   - puts the plug-in back to how it was before auto-switch touched it;
   - asks the chat, once, to turn the connector off.

A plug-in that was already on before auto-switch is never tracked and never turned off.

State lives in `<project>/.claude/auto-switch/state.json`.

## What it cannot do, and why

Checked on Claude Code 2.1 in the macOS desktop app. The CLI follows the same settings rules for local plug-ins.

| Thing | Automatic? | Why |
|---|---|---|
| **Local plug-ins** (installed from a marketplace on your machine) | Yes, from the next session | Claude Code reads `enabledPlugins` when a session starts. A plug-in switched on mid-chat loads in the next chat started in that folder, not in the running one. The desktop app was tested and obeys a project's `enabledPlugins` for local plug-ins. |
| **Account plug-ins** (synced from your claude.ai account) | **No** | In the desktop app they load into every chat whatever `enabledPlugins` says, and no chat tool switches them. Cut them once, by hand, to a small always-on set in your claude.ai account settings. Install the ones you need now and then as local plug-ins instead, and list them in the need-list. |
| **Connectors** (claude.ai connectors such as Gmail) | Yes, by the chat | Only the chat can call `set_session_connector_enabled`; a hook cannot. The hook tells the chat to make the call. The connector's tools arrive on the chat's **next** turn. In default permission mode you approve each call. |
| **Skills** | Already on demand | Claude Code lists only each skill's one-line description; the body loads when used. The hook just names the skill the job needs, so the chat does not miss it. |

**Connector switches are shared.** In the desktop app, switching a connector also sets the default for new chats. If two chats are open, one chat switching a connector off affects the other's default too.

**Plain word matching.** The hook matches whole words, case-insensitive. It does not read meaning. Choose words that name the job, not words that turn up in every prompt.

## Install

```bash
git clone <this repo> auto-switch
cd your-project
python3 /path/to/auto-switch/install.py
```

This installs into the current project (`./.claude/settings.json`). To install for every project instead:

```bash
python3 /path/to/auto-switch/install.py --user
```

Before it changes anything, `install.py` copies your settings file to `settings.json.auto-switch-backup` (or leaves a `settings.json.auto-switch-absent` marker if there was none). Running it twice adds nothing twice and keeps the first backup.

Then cut your always-on set: turn off the plug-ins and connectors you do not use every day, and add them to the need-list instead.

## Uninstall

```bash
python3 /path/to/auto-switch/uninstall.py          # project install
python3 /path/to/auto-switch/uninstall.py --user   # user install
```

It copies the backup back over your settings file, byte for byte, and removes the state file. Any settings change you made after install is dropped with it, so look at the backup first if you have edited settings since.

## Extend the need-list

Edit `needs.json` beside `autoswitch.py`, or put a project's own list at `<project>/.claude/auto-switch/needs.json` (it wins). The environment variable `AUTO_SWITCH_NEEDS` wins over both.

```json
{
  "keep_turns": 2,
  "needs": [
    {
      "name": "email",
      "words": ["email", "inbox", "reply to"],
      "connectors": ["Gmail"]
    },
    {
      "name": "github work",
      "words": ["pull request", "pr", "github"],
      "plugins": ["github@claude-plugins-official"]
    },
    {
      "name": "pdf",
      "words": ["pdf"],
      "skills": ["pdf"]
    }
  ]
}
```

- `words`: whole words or phrases that mean the job has started.
- `plugins`: plug-in keys exactly as in `enabledPlugins` (`name@marketplace`).
- `connectors`: connector names as the desktop app lists them.
- `skills`: skill names as the Skill tool takes them.
- `keep_turns`: how many prompts without a match before a thing is switched off.

A need may list any mix of the three.

## Test

```bash
python3 -m unittest discover -s tests -v
```

The tests feed sample hook events (`tests/events/`) to the hooks in a temporary folder and check the output and the settings file. They never touch your real settings.

## License

MIT. See `LICENSE`.
