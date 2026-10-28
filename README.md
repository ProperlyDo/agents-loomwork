# loomwork

> **Draft.**\
> Still shaping: commands, the declaration's keys and where files land can change between releases.

Weaves shared agent rules through your projects. One repo holds the rules; `loom` puts the right ones into each project, in the place every agent reads them.

This repo is loom alone — the rules live in a repo of their own, which loom calls a source.

## How it works

1. **A project declares what it wants**, in a committed `.agents.toml` — `loom init` writes it from your answers:

   ```toml
   [[source]]
   source = "git.example.com/your-team/agent-rules"
   rules = ["python", "django"]
   skills = ["i18n-translate"]
   ```

   A second `[[source]]` block adds a second rules repo — copies land in one flat directory, and a later source wins a filename it shares with an earlier one.

2. **`loom` copies in what it names**: rules into `.agents/rules/`, skills into `.agents/skills/`. Each wired agent is then pointed at them, beside whatever the project keeps for that agent: `.claude/rules/loom` and one `.claude/skills/<name>` link per skill for Claude Code. OpenCode gets no per-project pointer: the global rules land in `~/.config/opencode/rules/`, and the source's `AGENTS.md`, copied to `~/.config/opencode/AGENTS.md`, sends it to `.agents/rules/` itself.

3. **Sessions keep themselves fresh.** `loom init` registers a `SessionStart` hook in Claude's settings; it runs `loom sync` only where a `.agents.toml` exists, so a project that never opted in costs nothing. Each project is wired for the agents it was set up for.

### The two files

**`.agents.toml`** sits in a project and is committed: what the project takes. One `[[source]]` block per source, each with:

- `source` — where the rules repo is: a clone url, a bare `<host>/<owner>/<repo>` with an optional folder after it when the rules sit in a subdirectory, or a path on this machine. A relative path counts from the project.
- `rules` — names from the source's `rules/<name>.md`.
- `skills` — names from the source's `skills/<name>/`.

With a single source, the header can go:

```toml
source = "git.example.com/your-team/agent-rules"
rules = ["python", "django"]
```

**`loom.toml`** sits in a source, beside its `rules/` and `skills/`: what the source hands out. It is optional.

```toml
# a source this one builds on — recorded first, so this one wins a filename they share
[[source]]
source = "git.example.com/your-team/base-rules"

# what every project gets, declared or not
[global]
rules = ["git"]
skills = []
```

A `[[source]]` here uses the same spellings as in `.agents.toml`, with a relative path counting from this source. A name under `[global]` that the source does not ship is skipped. The source's `AGENTS.md` is its universal layer, copied to each agent's user-level file — only when the source has a `loom.toml`, so a third-party repo keeps its contributor `AGENTS.md` to itself.

A source is any directory with a `rules/` or a `skills/` directory. Two spellings of one repo — a clone url, a bare `<host>/<owner>/<repo>`, a checkout on this machine — resolve to the same source, so a project declaring the url and a machine reading the checkout are using the same rules.

## Install

macOS and Linux. On Windows, run loom, the agent and the project inside WSL — on Windows itself, loom's locks, links and hook do not work.

```bash
uv tool install loomwork                                             # provides `loom`
cd <project> && loom init                                             # declares, wires, registers the hook
```

To run the latest `main` instead of a release: `uv tool install git+https://github.com/ProperlyDo/agents-loomwork`.

`init` is the only command a new machine needs. It asks which agents to wire, where the rules come from — unless the project's declaration already says, in which case it takes that — and which rules and skills this project uses.

The hook calls loom by the full path `init` was started from, so a checkout run with `uv run` works as well as an install. Rerun `init` after moving either. Avoid `uvx` for `init`: its path is a cache entry that can be cleared.

From then on, opening any project that carries a `.agents.toml` wires it: the hook reads the declaration, fetches the source if this machine lacks it, and copies the rules in. Projects without one are untouched — the hook checks for the file before calling loom at all.

**Not using Claude?** `loom init` in a project does the same work by hand, and `loom sync` refreshes afterwards.

**Developing the rules themselves?** `loom init --source <rules-checkout>` points the machine at that working copy instead of a fetched clone, so edits take effect without pushing.

### Keeping profiles apart

A profile is one Claude config dir — `~/.claude` unless `--config-dir` names another. Everything loom does for it lands there: the user-level rules and skills, the session hook, and the registry of its sources and projects. Two profiles never see each other's rules, so a second one keeps, say, a client's rules away from your own:

```bash
loom --config-dir ~/.claude-client init                  # wires this project into that profile
alias claude-client='CLAUDE_CONFIG_DIR=~/.claude-client claude'
```

Start Claude for that work through the alias. The hook carries the flag, so each session syncs only the profile it was started with. `init` asks for the dir when the flag is left out and `~/.claude` doesn't know the project yet.

- **One project, one profile.** A project's `.agents/` is shared by every profile that wires it, and each would clear the other's copies.
- **Only Claude's user-level files are per profile.** OpenCode reads `~/.config/opencode` whatever the profile, so the global rules of every profile that wires it land there together.

### What to ignore

`loom` writes machine-local files into a project, and `init` offers to add them to its `.gitignore` when it writes the declaration. `.agents.toml` is the only file to commit:

```gitignore
.agents/
.claude/
```

Keep `.claude/settings.json` if the project commits shared Claude settings — ignore `.claude/*` with an exception for it instead.

## Commands

| | |
|---|---|
| `init [project]` | set up this profile and the project: declaration, agents, wiring, and the session hook. `--agents claude,opencode` skips the question; `--source` names where the rules come from |
| `remove [project]` | unwire it and forget it |
| `sync [project]` | update its sources and rewire the project, defaulting to the current one; `--all` walks every project in this profile |
| `status` | the sources added to this profile, what it hands every project, and every wired project |
| `uninstall` | undo everything this profile installed |

## Why copies, not links

Claude treats a symlinked project rule whose target sits outside the project as an external import, and those stay unloaded until an approval that only an `@path` import can raise — so a linked rule is silently ignored. Everything loom writes is therefore a copy, and what makes one ours to replace or delete is a trailing `<!-- written by loomwork -->` marker on a rule file, or the registry's record for a skill folder, which cannot carry one. Copying the user bridges also survives Cowork sessions, which skip a symlinked `~/.claude/CLAUDE.md`.

Links are used only where the target resolves inside the project: `.claude/rules/loom` and each `.claude/skills/<name>` onto `.agents/`. That saves writing every rule twice — once where the `.agents` standard expects it, once where the agent looks.

## Layout

| | |
|---|---|
| `loomwork/cli.py` | argument parsing, nothing else |
| `loomwork/questions.py` | what `init` asks — one function per thing a command needs to know |
| `loomwork/prompts.py` | the terminal prompts those questions use: typed answers, checkbox picks, confirmations |
| `loomwork/loom.py` | what a command means: which rules a project takes, which agents, what gets recorded |
| `loomwork/installation.py` | the mechanism: copy, link, clear what is owned, and tell what is owned |
| `loomwork/git.py` | the only module that calls git — clone, update, read a remote |
| `loomwork/paths.py` | where things live — loom's own dirs, a project's `.agents/`, how a path is spelled or shown, and locking one |
| `loomwork/output.py` | what loom prints: `info` for steps, `warn` for what was skipped, `error` for what stopped the run |
| `loomwork/sources.py` | a rules repo on this machine: fetch it, give two spellings of it one identity, and read what a set of them defines (`Catalog`) |
| `loomwork/registry.py` | what this profile remembers — the sources added to it, its projects, what it owns where |
| `loomwork/declaration.py` | the committed `.agents.toml` and `loom.toml`, read and written |
| `loomwork/agents/` | one module per agent; each overrides only the surfaces its agent can consume |
| `tests/` | `python -m unittest discover` |

Adding an agent is one module in `loomwork/agents/` and one entry in the roster. Anything that names a directory or file format belonging to one agent belongs in that agent's module — `installation.py` stays agent-agnostic.

## Notes

- Loom's own folder is `~/.loom`, which holds the clones it fetches (`~/.loom/sources/<host>/<owner>/<repo>`) and nothing else. Those clones are shallow and hold no work of yours, so every update resets them to their remote — a rewritten history included. A checkout of your own, added by path, is only fast-forwarded. Everything else lands where an agent reads it: global rules and skills in each agent's own `rules/` and `skills/`, the rest in the project. Loom puts nothing in `~/.agents`, since none of its agents reads from there.
- The registry lives in the config dir it bridges — `~/.claude/.loomwork.json`, or `~/.claude-work/.loomwork.json` for a second account — so each profile keeps its own sources and projects. Loom reads no env var to find it: `--config-dir` says which, and without it the profile is `~/.claude`.
- **Loom distributes where it is told.** An agent that is not installed here is wired all the same, so a machine can be set up before the agent is; `init` marks those in the picker and warns once it is done. Presence is the command on `PATH`, never the config dir — loom creates those itself.
- `init` records the agents you picked, and every later `sync` wires those. A session hook adds its own agent to them, since an agent running in a project is one it uses.
- The hook updates the sources before it copies. Claude runs it in the background, so you can type at once and only the first answer waits for it.
- Skills a source defines are copied like rules — into the project's `.agents/skills/`, or for global ones into each agent's `skills/` — and the registry records which ones we put there. The skills CLI writes into the same directories, and its entries are never ours to replace. A skill from anywhere else stays its job: `npx skills add <source> --skill <name>`.
- `.agents.toml` is what a repo weaves in — the weft. `loom.toml` is what a source strings up for whoever uses it — the warp, `[global]` included. One role each, the way git keeps `.gitmodules` and `.gitattributes` apart.
- Project-specific instructions belong in the project's own `AGENTS.md`, which loom never writes — Claude reads it natively and OpenCode directly. Beware adding your own `CLAUDE.local.md`: its presence stops Claude reading `AGENTS.md` natively, unless it imports `@AGENTS.md` or **Project instructions** is set to `claude-md-and-agents-md`.

## Open

- **`remove` does not stick.** A project that still carries `.agents.toml` is wired again by the next session hook; deleting the file is the opt-out that holds.
- **Colliding names pass silently.** Two sources shipping one filename merge by the declared order, last one winning, and nothing says it happened. Skills have no scope to fall back on either: Claude discovers them one level deep (`skills/<name>/SKILL.md`), so a shared name is a shared folder.

## Development

```bash
git clone git@github.com:ProperlyDo/agents-loomwork.git && cd agents-loomwork
uv sync                        # creates .venv, installs click and questionary, and this package, editable
uv run python -m unittest discover
```

Run loom itself the same way, from whichever project you are testing against:

```bash
cd <project>
uv run --project <path-to-this-clone> loom init
```

Both forms run your working copy, so an edit takes effect on the next invocation — no install, no reinstall. `source .venv/bin/activate` in this repo is the alternative: it puts `loom` and `python` on PATH until you `deactivate`, after which `loom init` works from any directory without the `--project` flag.

Tests need nothing but the venv and never touch your home: every case builds its source, project and agent config dirs under a temp directory, through `SandboxTestCase` in `tests/fixtures.py`. They run no git either: `tests/__init__.py` makes any git call a test did not patch fail loudly, so a test that needs an answer from git patches the function that gives it.

To release, run **Open release PR** in GitHub Actions and pick `patch`, `minor` or `major`. It opens a PR that raises the version; merging it lets the **Release** workflow test, publish to PyPI, tag `v<version>` and create the GitHub release. A push to `main` that leaves the version alone releases nothing.
