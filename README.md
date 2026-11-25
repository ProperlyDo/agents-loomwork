# loomwork

> **Draft.**\
> Still shaping: commands, the declaration's keys and where files land can change between releases.

Weaves shared agent rules through your target dirs — any directory you point it at, usually a project. One repo holds the rules; `loom` puts the right ones into each target dir, in the place every agent reads them.

This repo is loom alone — the rules live in a repo of their own, which loom calls a source.

## How it works

1. **A target dir declares what it wants**, in a committed `.agents.toml` — `loom init` writes it from your answers:

   ```toml
   [[source]]
   source = "git.example.com/your-team/agent-rules"
   rules = ["python", "django"]
   skills = ["i18n-translate"]
   ```

   A second `[[source]]` block adds a second rules repo — copies land in one flat directory, and a later source wins a filename it shares with an earlier one.

2. **`loom` copies in what it names**: rules into `.agents/rules/`, skills into `.agents/skills/`. Each wired agent is then pointed at them, beside whatever the target dir keeps for that agent: `.claude/rules/loom` and one `.claude/skills/<name>` link per skill for Claude Code. OpenCode gets no pointer to rules or skills in the target dir: the global rules land in `rules/` in its config dir (`~/.config/opencode`, or [another one](#keeping-setups-apart)), and the source's `AGENTS.md`, copied beside them, sends it to `.agents/rules/` itself. What it does get is one `.opencode/commands/<name>.md` per manual skill — see [Skills as OpenCode commands](#skills-as-opencode-commands).

3. **Sessions keep themselves fresh.** `loom init` registers a `SessionStart` hook in Claude's settings; it runs `loom sync` only where a `.agents.toml` exists, so a target dir that never opted in costs nothing. Each target dir is wired for the agents it was set up for.

### The two files

**`.agents.toml`** sits in a target dir and is committed: what the target dir takes. One `[[source]]` block per source, each with:

- `source` — where the rules repo is: a clone url, a bare `<host>/<owner>/<repo>` with an optional folder after it when the rules sit in a subdirectory, or a path on this machine. A relative path counts from the target dir.
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

# what every target dir gets, declared or not
[global]
rules = ["git"]
skills = []
```

A `[[source]]` here takes the same forms as in `.agents.toml`, with a relative path counting from this source. A name under `[global]` that the source does not ship is skipped. The source's `AGENTS.md` is its universal layer, copied to each agent's user-level file — only when the source has a `loom.toml`, so a third-party repo keeps its contributor `AGENTS.md` to itself.

A source is any directory with a `rules/` or a `skills/` directory. Two ways of naming one repo — a clone url, a bare `<host>/<owner>/<repo>`, a checkout on this machine — resolve to the same source, so a target dir declaring the url and a machine reading the checkout are using the same rules.

## Install

macOS and Linux. On Windows, run loom, the agent and the target dir inside WSL — on Windows itself, loom's locks, links and hook do not work.

```bash
uv tool install loomwork          # provides `loom`
cd <target_dir> && loom init      # declares, wires, registers the hook
```

To run the latest `main` instead of a release: `uv tool install git+https://github.com/ProperlyDo/agents-loomwork`.

`init` is the only command a new machine needs. It asks which agents to wire, showing the config dir each would be wired from. When the target dir carries no `.agents.toml` yet, it also asks which source it uses, what it takes from it, and whether to add loom's folders to `.gitignore`. A flag, a committed declaration or what loom already recorded skips the matching question, and nothing is written into the target dir or a config dir until every answer is in.

The hook calls loom by the full path `init` was started from, so a checkout run with `uv run` works as well as an install. Rerun `init` after moving either. Avoid `uvx` for `init`: its path is a cache entry that can be cleared.

From then on, opening any target dir that carries a `.agents.toml` wires it: the hook reads the declaration, fetches the source if this machine lacks it, and copies the rules in. Target dirs without one are untouched — the hook checks for the file before calling loom at all.

**Not using Claude?** `loom init` in a target dir does the same work by hand, and `loom sync` refreshes afterwards.

**Developing the rules themselves?** `loom init --source <rules-checkout>` points the machine at that working copy instead of a fetched clone, so edits take effect without pushing.

### Keeping setups apart

Each agent reads one config dir: `~/.claude` and `~/.config/opencode` unless it is launched with `CLAUDE_CONFIG_DIR` or `OPENCODE_CONFIG_DIR`. Loom writes into the same dir the agent reads. It takes the dir from `--claude-config-dir` or `--opencode-config-dir` when given, else from the agent's own variable, else the agent's standard one. A second set of dirs keeps, say, a client's rules away from your own:

```bash
alias claude-client='CLAUDE_CONFIG_DIR=~/.claude-client claude'
alias opencode-client='OPENCODE_CONFIG_DIR=~/.config/opencode-client opencode --standalone'
CLAUDE_CONFIG_DIR=~/.claude-client OPENCODE_CONFIG_DIR=~/.config/opencode-client loom init
```

`init` records which dir each agent was wired from, in `~/.loom/loomwork.json`. From then on `loom sync` needs neither flags nor variables: it looks the target dir up and writes into the dirs recorded for it.

- **One config dir per agent per target dir.** A target dir's `.agents/` is shared by every config dir that wires it. When it is already wired for an agent from another config dir, `init` asks whether to move it; a no, or no terminal to ask in, stops `init` with nothing changed. `sync` never moves one. Wired from two config dirs of one agent, it skips that agent and says which ones.
- **A session of another setup leaves the target dir where it is wired.** Its hook still syncs the target dir into the recorded config dirs, and says which one to launch with for that target dir's global rules. The target dir's own rules reach the session whichever config dir it reads.
- **A config dir's global rules come from its target dirs.** Every config dir gets what the sources its target dirs declare hand every target dir, plus any source pinned to it with `init --source`. So a source one setup's target dir declares never reaches the other setup's config dirs.
- **Why `--standalone`.** Plain `opencode` joins one background service per user, and that service keeps the config dir of the session that started it — a later session's `OPENCODE_CONFIG_DIR` is ignored. `--standalone` gives the session a server of its own. Without it, run `opencode service stop` before starting OpenCode from another config dir.
- **Skills in `~/.claude/skills` reach every OpenCode session.** OpenCode reads that dir whatever its config dir, so the standard Claude dir's skills show up in every OpenCode session. Rules, `AGENTS.md` and commands do not cross.

### Upgrading from 0.1

Loom 0.1 kept a registry in each Claude config dir; this version keeps one in `~/.loom` and carries nothing over. Clean up with the old loom before installing the new one, or the copies it made stay behind as files loom no longer owns:

1. With 0.1 still installed, run `loom uninstall` for `~/.claude`, and `loom --config-dir <dir> uninstall` for every other Claude config dir you used. That removes its copies, links and session hooks.
2. Install the new version.
3. Run `loom init` in each target dir, launched the way you start the agent there — e.g. `CLAUDE_CONFIG_DIR=~/.claude-rh loom init`.
4. Delete the old `~/.claude*/.loomwork.json` files.

### What to ignore

`loom` writes machine-local files into a target dir, and `init` offers to add them to its `.gitignore` when it writes the declaration. `.agents.toml` is the only file to commit:

```gitignore
.agents/
.claude/
.opencode/
```

Keep `.claude/settings.json` if the target dir commits shared Claude settings — ignore `.claude/*` with an exception for it instead. The same goes for `.opencode/` when the target dir commits commands or config of its own there.

## Commands

| | |
|---|---|
| `init [target_dir]` | set up the target dir and each chosen agent's config dir: declaration, agents, wiring, and the session hook. `--agents claude,opencode` skips the question; `--source` names where the rules come from |
| `remove [target_dir]` | unwire it and forget it |
| `sync [target_dir]` | update its sources and rewire the target dir into the config dirs it is wired from, defaulting to the current one; `--all` walks every wired target dir |
| `status` | each config dir loom writes into: its sources, what they hand every target dir, and the target dirs wired from it |
| `uninstall` | undo everything loom installed, in every config dir |

`--claude-config-dir` and `--opencode-config-dir` go before the command; you need them only for `init`, since the session hook passes its own — see [Keeping setups apart](#keeping-setups-apart). A refusal prints one `ERROR` line and exits 1.

## Why copies, not links

Claude treats a symlinked project rule whose target sits outside the project as an external import, and those stay unloaded until an approval that only an `@path` import can raise — so a linked rule is silently ignored. Everything loom writes is therefore a copy, and what makes one ours to replace or delete is a trailing `<!-- written by loomwork -->` marker on a rule file, or the registry's record for a skill folder, which cannot carry one. Copying the global files also survives Cowork sessions, which skip a symlinked `~/.claude/CLAUDE.md`.

Links are used only where the target resolves inside the target dir: `.claude/rules/loom` and each `.claude/skills/<name>` onto `.agents/`. That saves writing every rule twice — once where the `.agents` standard expects it, once where the agent looks.

## Skills as OpenCode commands

A skill whose frontmatter says `disable-model-invocation: true` is manual: Claude lists it under `/<name>` and never starts it by itself. OpenCode honours the flag too, but lists such a skill under `@<name>` only — its `/` menu is fed from `commands/`.

So for each such skill loom also writes a command: `.opencode/commands/<name>.md` in a target dir, `commands/<name>.md` in OpenCode's config dir for a global one. The command is an entry to the skill and nothing more — it carries the skill's description, tells OpenCode to load the skill, and passes on what was typed after the command. The skill stays the one definition, supporting files included.

- **Arguments arrive as text.** A `$ARGUMENTS` inside the skill is not filled in by OpenCode — the command states the arguments and the model matches them up.
- **Only the description carries over.** `allowed-tools`, `argument-hint` and `context` are Claude's and stay in the skill.
- **Every manual skill in `.agents/skills/` gets one.** That includes a skill the skills CLI put there, and its command is ours to replace and remove.
- **Older OpenCode ignores the flag.** Builds from before October 2026 offer a manual skill to the model like any other; the command works there all the same.
- **A command of the target dir's own wins.** A file already at that name is left alone, with a warning.
- **A command replaces a built-in of its name.** A manual skill called `review`, `init` or `goal` takes over OpenCode's own `/review`, `/init` or `/goal`.
- **The prompt ends with loom's marker.** The `<!-- written by loomwork -->` line is what makes the file ours to replace, so the model sees it too.

## Notes

- Loom's own folder is `~/.loom`, which holds its registry (`~/.loom/loomwork.json`) and the clones it fetches (`~/.loom/sources/<host>/<owner>/<repo>`). Those clones are shallow and hold no work of yours, so every update resets them to their remote — a rewritten history included. A checkout of your own, added by path, is only fast-forwarded. Everything else lands where an agent reads it: global rules and skills in each agent's own `rules/` and `skills/`, the rest in the target dir. Loom puts nothing in `~/.agents`, since none of its agents reads from there.
- The registry is keyed by config dir: each holds the sources pinned to it with `init --source` and the target dirs wired from it, with the sources each target dir declares. One file for every dir is what lets `init` see that a target dir is wired from another one.
- **Loom distributes where it is told.** An agent that is not installed here is wired all the same, so a machine can be set up before the agent is; `init` marks those in the picker and warns once it is done. Presence is the command on `PATH`, never the config dir — loom creates those itself.
- `init` records the agents you picked, each under its dir, and every later `sync` wires those. A session hook adds its own agent from the dir it reads, since an agent running in a target dir is one it uses — unless the target dir is wired for that agent from another dir.
- The hook updates the sources before it copies. Claude runs it in the background, so you can type at once and only the first answer waits for it.
- Skills a source defines are copied like rules — into the target dir's `.agents/skills/`, or for global ones into each agent's `skills/` — and the registry records which ones we put there. The skills CLI writes into the same directories, and its entries are never ours to replace. A skill from anywhere else stays its job: `npx skills add <source> --skill <name>`.
- `.agents.toml` is what a repo weaves in — the weft. `loom.toml` is what a source strings up for whoever uses it — the warp, `[global]` included. One role each, the way git keeps `.gitmodules` and `.gitattributes` apart.
- Instructions for one target dir belong in its own `AGENTS.md`, which loom never writes — Claude reads it natively and OpenCode directly. Beware adding your own `CLAUDE.local.md`: its presence stops Claude reading `AGENTS.md` natively, unless it imports `@AGENTS.md` or **Project instructions** is set to `claude-md-and-agents-md`.

## Open

- **`remove` does not stick.** A target dir that still carries `.agents.toml` is wired again by the next session hook; deleting the file is the opt-out that holds.
- **Colliding names pass silently.** Two sources shipping one filename merge by the declared order, last one winning, and nothing says it happened. Skills have no scope to fall back on either: Claude discovers them one level deep (`skills/<name>/SKILL.md`), so a shared name is a shared folder.

## Development

```bash
git clone git@github.com:ProperlyDo/agents-loomwork.git && cd agents-loomwork
uv sync                        # creates .venv, installs the dependencies and this package, editable
uv run python -m unittest discover
```

Run loom itself the same way, from whichever target dir you are testing against:

```bash
cd <target_dir>
uv run --project <path-to-this-clone> loom init
```

Both forms run your working copy, so an edit takes effect on the next invocation — no install, no reinstall. `source .venv/bin/activate` in this repo is the alternative: it puts `loom` and `python` on PATH until you `deactivate`, after which `loom init` works from any directory without the `--project` flag.

Tests need nothing but the venv and never touch your home: every case builds its source, target dir and agent config dirs under a temp directory, through `SandboxTestCase` in `tests/fixtures.py`. They run no git either: `tests/__init__.py` makes any git call a test did not patch fail loudly, so a test that needs an answer from git patches the function that gives it.

Adding an agent is one module in `loomwork/agents/` and one entry in `SUPPORTED_AGENTS`. Anything that names a directory or file format belonging to one agent belongs in that agent's module — `installation.py` stays agent-agnostic.

To release, run **Open release PR** in GitHub Actions and pick `patch`, `minor` or `major`. It opens a PR that raises the version; merging it lets the **Release** workflow test, publish to PyPI, tag `v<version>` and create the GitHub release. A push to `main` that leaves the version alone releases nothing.
