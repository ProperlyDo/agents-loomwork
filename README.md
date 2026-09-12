# agents-config

Shared rules and skills for AI agents across our projects, organized by stack. This repo is the single source. Agents consume it in two ways:

- **Claude Code — mechanical.** A `SessionStart` hook links the right files into place, and Claude's rules engine loads them.
- **JetBrains AI Assistant (PyCharm, WebStorm, …) — mechanical, per project.** The same hook links our rules into `.aiassistant/rules/`, where the IDE picks them up.
- **Other agents (OpenCode, …) — instructional.** They read `AGENTS.md` natively, and the globally installed copy tells them what else to read.

A project opts in with one committed line: `stacks: [python, django]` in the frontmatter of its root `AGENTS.md`. Everything else is machinery around that line.

## Install — once per machine

```bash
# one line — clones with your git auth when needed, then installs (the repo is private; anonymous curl can't reach it)
[ -d ~/.agents-config ] || git clone git@github.com:<owner>/agents-config.git ~/.agents-config && ~/.agents-config/install.py install

# from an existing clone, wherever it lives; also updates the install
./install.py install [--namespace <name>]
```

`--namespace` defaults to the clone's origin owner, lowercased (`Acme/agents-config` → `acme`); the resolved value is baked into the hook line — the only place it persists. The shared agents dir is fixed at `~/.agents`: it is a standard location (OpenCode reads its `skills/` natively), so it is not a knob. The install touches three things: the `SessionStart` hook in `$CLAUDE_CONFIG_DIR/settings.json`, the shared agents dir, and the bridges described under Flow.

| Env var | Purpose | Default |
|---|---|---|
| `CLAUDE_CONFIG_DIR` | Claude's config dir | `~/.claude` |
| `OPENCODE_CONFIG_DIR` | OpenCode's config dir | `$XDG_CONFIG_HOME/opencode` |

The scripts read the same config-dir variables the agents themselves honor. Redirect an agent (e.g. with a per-account alias) and its links move with it.

Several accounts? Give each its own config dir (e.g. a shell alias setting `CLAUDE_CONFIG_DIR`) and run the installer once per account, inside that account's environment. Each config dir gets its own hook and links, so nothing mixes. Keep it to one config repo per account: two configs in the same account keep their rules and skills apart, but both want to be the agent's single entry file (`CLAUDE.md`, OpenCode's `AGENTS.md`) — whichever installed last wins it.

Uninstall with `./install.py uninstall`. It removes the hook, the bridges, and everything this repo owns in the shared agents dir — nothing else. Add a `<project-dir>` argument to unwire one project instead. The clone stays; delete it yourself.

## Layout

| In the repo | Purpose |
|---|---|
| `AGENTS.md` | the universal layer: rule routing, working style, naming, code comments. Loads in every session |
| `rules/<stack>.md` | one rule file per stack. Its `paths:` globs load it lazily; a file without `paths:` is stack-neutral and loads everywhere (`git.md`). A stack pair always loads together — see Adding rules and skills |
| `skills/<name>/` | task procedures (Agent Skills spec). Rules state constraints; skills own workflows |
| `install.py` + `installer/` | the whole lifecycle: `install` / `sync` / `link` / `uninstall`. `installation.py` is the linking machinery; `agents.py` holds one class per agent — each overrides only the surfaces its tool can consume — and the `AGENTS` roster |

How it lands on a machine — the shared agents dir links into the clone, and agent dirs hold only bridges into the shared dir:

```
~/.agents/                        # the shared agents dir — fixed location
├── AGENTS.md
├── rules/<namespace>/*.md        # all rules; the namespace keeps ours apart from hand-made files
└── skills/<name>                 # ours beside skills-CLI entries; OpenCode reads this natively
$CLAUDE_CONFIG_DIR/               # bridges only
├── CLAUDE.md      → ~/.agents/AGENTS.md
├── rules/<namespace>/            # the stack-neutral rules only
└── skills/<name>  → ~/.agents/skills/<name>
$OPENCODE_CONFIG_DIR/
└── AGENTS.md      → ~/.agents/AGENTS.md
<project>/
├── AGENTS.md                     # committed — the only per-project file
├── .agents/rules/<namespace>/    # machine-local: project.md + the declared stacks
├── .aiassistant/rules/*.md       # for JetBrains: universal layer + git + the declared stacks
└── .claude/rules  → ../.agents/rules
```

The namespace persists only in the registered hook line; every subcommand takes the same `--namespace` flag. Linking never destroys anything: a name occupied by a file we don't own is skipped with a warning.

## Flow

**Machine, once** — `install.py install`:
- registers `install.py sync` as Claude's `SessionStart` hook, fills the shared agents dir, and lays the bridges
- an agent gets bridged only if its config dir already exists; if a tool arrives later, rerun the install once
- stack rules never bridge globally. `.html` means Django templates in one repo and Angular templates in another — only the project knows which

**Project, once** — commit a root `AGENTS.md` with:
- the `stacks: [python, django]` frontmatter. This is the opt-in; remove it and the next session unwires the project
- one routing line: "coding rules for the declared stacks are linked under `.agents/rules/`". It serves agents that read only the project file, like IDE assistants
- genuinely project-specific content — and nothing else. No pointers to this repo; generated entry files (`CLAUDE.md`, `GEMINI.md`) stay gitignored

**Every session** — the hook runs `install.py sync`:
1. `git pull --ff-only` — safe offline; keep `main` always pullable
2. refresh the shared agents dir and every bridge
3. wire the project: each declared stack's rule plus `project.md` (a link back to the project's own `AGENTS.md`) is linked into `.agents/rules/<namespace>/`, and `.claude/rules` links that dir wholesale — the same shape the skills CLI uses. JetBrains gets flat links in `.aiassistant/rules/` instead; having no global channel, that set also carries the universal layer and the stack-neutral rules. Unknown stack names warn on stderr

Every pass also reconciles: a link we own whose name is no longer wanted gets removed, so upstream renames leave no zombies; files we don't own are never touched. Claude loads unconditional files at launch and stack pairs on the first matching read. Other agents follow the routing in `AGENTS.md` instead: `rules/git.md` plus each declared stack's file.

**Without Claude Code on the machine**, the session hook never fires, so two things become manual:
- PyCharm's rule links: run `install.py link <project-dir>` once per project.
- Updates: nothing pulls this repo for you anymore — rerun `./install.py install` from time to time.

OpenCode needs no project links at all: `install` already bridged its global `AGENTS.md`, whose routing points at the rule files *inside the clone* ("next to this file's real location"). The project's own `AGENTS.md` only tells it which stacks to pick.

## Adding rules and skills

- Prove a convention in one project's `AGENTS.md` first, then promote it here. An always-on constraint becomes a rule; a task-shaped procedure becomes a skill.
- A rule's frontmatter decides its reach — there is no list to maintain. With `paths:` globs it is a **stack rule**: linked only into projects that declare that stack, loaded when a matching file is read. Without `paths:` it is **stack-neutral**: bridged globally and active in every project, declared or not (`git.md`). So the question to ask before omitting globs is: is this rule true in *every* repo on the machine, including ones that never opted in? Only then leave them off.
- Team skills enter a project with `npx skills add <source>` and the committed `skills-lock.json`. Personal skills skip the lock: symlink or drop the skill dir into `<project>/.agents/skills/` for one project (it's gitignored, and the CLI leaves unlisted entries alone), or into `~/.agents/skills/` — or `npx skills add -g` — for all projects.
- State a convention in one place only. When both `AGENTS.md` and a rule file carry it, which copy wins is anyone's guess.
- Rules cannot import each other. A pair stays bundled because the dependent file's `paths:` cover all of the base file's — so a glob added to a base file goes into its dependent too. The frontmatter comments mark this.
- Quote globs that start with `*` or `{` — unquoted, YAML eats them silently.

## Verifying

- **Watch for `Loaded …/rules/<stack>.md` lines** — the main signal. They appear under Claude's first Read of a matching file, so prompt some work on the code and look for them. No line means the globs didn't match. `/memory` won't show stack rules at all — it lists only what loaded at launch (universal layer, global rules, the project `AGENTS.md`); `/context` shows skills.
- **Brand-new files don't trigger rules.** Rules inject when Claude *reads* a matching file, not when it creates one. For greenfield work the routing instruction in `AGENTS.md` is what brings the stack rules in.
- **The very first session in a fresh project clone starts without `project.md`.** Claude scans rule folders at launch, and the hook that creates the links runs just after — one step too late for that single session. Stack rules are unaffected (they load later, at read time), and every following session is complete. To make even the first session complete, wire the project by hand right after cloning: `install.py link <project-dir>`.
- **A deleted project `.claude/` is not a problem.** The next session relays both links. Only the committed `settings.json` needs a `git restore`.
- **In PyCharm, our rules appear under `.aiassistant/rules`.** Open a rule file there — seeing our text means the IDE follows the links (a broken link is worth reporting). Then ask the AI chat *"what do the project rules say about git branch naming?"* — an answer naming `<type>/<short-kebab-desc>` proves the rules reach it. Rule type (Always / by patterns) is IDE-side metadata: check it under Settings → Tools → AI Assistant → Project Rules and set Always if needed. `.aiassistant/` stays gitignored — the links are machine-local.
