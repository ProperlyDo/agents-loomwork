# loomwork

Weaves shared agent rules through your projects. One repo holds the rules; `loom` puts the right ones into each project, in the place every agent reads them.

It is the tool only — the rules live in their own repo, like [ProperlyDo/agents-rules](https://github.com/ProperlyDo/agents-rules).

## How it works

1. **A project declares what it wants**, in a committed `.agents.toml`:

   ```toml
   source = "github.com/ProperlyDo/agents-rules"
   rules = ["python", "django"]
   ```

2. **`loom` copies those rules in**, to `.agents/rules/<namespace>/`, and points each installed agent at them: `.claude/rules` for Claude Code, `.aiassistant/rules/` for JetBrains, the global `AGENTS.md` for OpenCode.

3. **Sessions keep themselves fresh.** Claude's plugin runs `loom sync` at session start, which pulls the rules repo and rewrites what changed. Each project is wired for the tools it was added with, so a Claude session never creates JetBrains wiring.

## Install

```bash
uv tool install git+ssh://git@github.com/ProperlyDo/agents-loomwork   # provides `loom`

cd <project>
loom add                                                       # reads .agents.toml, fetches the rules, wires the project
```

`add` clones the declared source into `~/.local/share/loomwork/sources/` when the machine hasn't got it, so a new machine needs nothing else. Repeat `loom add` once per project.

With the Claude Code plugin installed instead, even that is unnecessary: the plugin ships the rules and its hook wires each project it opens.

**Developing the rules themselves?** `loom init .` inside your rules checkout points the machine at that working copy instead of a fetched clone, so edits take effect without pushing.

### What to ignore

`loom` writes machine-local files into a project. Commit `.agents.toml` and ignore the rest:

```gitignore
.agents/
.claude/*
!.claude/settings.json     # keep if the project commits shared Claude settings
.aiassistant/
```

## Commands

| | |
|---|---|
| `init [source]` | point this machine at a rules checkout, defaulting to the current directory |
| `add [project]` | ask which installed tools to wire this project for, then wire and record it. `--agents claude,jetbrains` skips the question |
| `remove [project]` | unwire it and forget it |
| `sync [project]` | pull the source, rewire one project or all of them |
| `status` | the source, and every project under management |
| `uninstall` | undo everything on this machine |

`--namespace NAME` overrides the name the rules are filed under; it defaults to the source's owner segment.

## Why copies, not links

Claude treats a symlinked project rule whose target sits outside the project as an external import, and those stay unloaded until an approval that only an `@path` import can raise — so a linked rule is silently ignored. Everything loom writes is therefore a copy carrying a trailing `<!-- written by loomwork -->` marker, which is what makes it ours to replace or prune: the project's rules, `~/.agents/`, and the user-level bridges alike. Copying the user bridges also survives Cowork sessions, which skip a symlinked `~/.claude/CLAUDE.md`.

The single exception is `.claude/rules → ../.agents/rules`, a link that resolves inside the project. It saves writing every rule twice: once where the `.agents` standard expects it, once where Claude looks.

## Layout

| | |
|---|---|
| `loomwork/cli.py` | argument parsing, nothing else |
| `loomwork/loom.py` | what a command means: which projects, which agents, what gets recorded |
| `loomwork/installation.py` | the mechanism: copy, link, prune, reconcile, ownership |
| `loomwork/registry.py` | what this machine remembers — source, namespace, projects |
| `loomwork/declaration.py` | the project's committed `.agents.toml` |
| `loomwork/agents/` | one module per tool; each overrides only the surfaces its tool can consume |
| `tests/` | `python -m unittest discover` |

Adding a tool is one module in `loomwork/agents/` and one entry in the roster. Anything that names a directory or file format belonging to one tool belongs in that tool's module — `installation.py` stays agent-agnostic.

## Notes

- `~/.agents` is fixed, not a knob: the skills CLI and OpenCode both look for that exact path.
- The registry lives in `~/.agents/.loomwork.json` and records whatever gets wired, whether by `add` or by a session hook.
- A project that declares another namespace is left alone rather than wired wrongly.
- `add` records the tools you picked, and every later `sync` wires exactly those. A project a session hook meets for the first time is wired for the tool whose hook it was.
- Running a second source on one machine is not supported yet: one source, one namespace.
- Project-specific instructions belong in the project's own `AGENTS.md`, which loom never writes — Claude reads it natively, OpenCode directly, and JetBrains through a `project.md` link. Beware adding your own `CLAUDE.local.md`: its presence stops Claude reading `AGENTS.md` natively unless the file starts with `@AGENTS.md`.

## Development

```bash
git clone git@github.com:ProperlyDo/agents-loomwork.git && cd agents-loomwork
uv sync                        # creates .venv, installs click and this package, editable
uv run python -m unittest discover
```

Run the tool itself the same way, from whichever project you are testing against:

```bash
cd <project>
uv run --project <path-to-this-clone> loom add
```

Both forms run your working copy, so an edit takes effect on the next invocation — no install, no reinstall. `source .venv/bin/activate` in this repo is the alternative: it puts `loom` and `python` on PATH until you `deactivate`, after which `loom add` works from any directory without the `--project` flag.

Tests need nothing but the venv and never touch `~/.agents`: every case builds a source, a project and an agents dir under a temp directory, and `Loom` takes `agents_dir` explicitly so a forgotten argument can't reach the real one.
