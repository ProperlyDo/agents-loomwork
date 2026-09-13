# agents-config

Shared rules and skills for AI agents across our projects. This repo is the single source for both, but they travel differently: **rules** are organized by stack and pushed to every machine by the installer here, while **skills** are a standalone catalog that projects pull from with the skills CLI — nothing in this repo installs them, and each project picks the ones it wants.

A project opts in with one committed line: `stacks: [python, django]` in the frontmatter of its root `AGENTS.md`. Everything else is machinery around that line.

## How it works

Rules:

1. **Once per machine** — `install.py install` registers Claude's `SessionStart` hook, fills `~/.agents/`, and lays the global bridges.
2. **Once per project** — commit a root `AGENTS.md` whose frontmatter declares the stacks, followed by whatever is specific to that project:

   ```markdown
   ---
   stacks: [python, django]
   ---
   ```

   One name per file in [`rules/`](rules/): `python` + `django` for Django backends, `typescript` + `angular` for Angular frontends — a pair is always declared together. `git` is stack-neutral, so it applies everywhere and is never declared.
3. **Every Claude Code session** — its hook pulls this repo, refreshes `~/.agents/`, and links the declared stack rules plus `project.md` into the project: `.agents/rules/<namespace>/` for Claude Code, flat into `.aiassistant/rules/` for JetBrains. It is the only agent that runs anything for us — see Supported agents for what the others need.

Skills:

4. **Add** — commit the skill to `skills/<name>/` here.
5. **Install** — each project takes what it wants: `npx skills add ProperlyDo/agents-config --skill <name>`, pinned in that project's `skills-lock.json` (`-g` installs it for every project instead).
6. **Update** — `npx skills update`; a skill does not travel with the session hook.

The rest of this file is the detail behind those six lines.

## Supported agents

| Agent | Reads | Reaches it |
|---|---|---|
| **Claude Code** | `~/.claude/CLAUDE.md`, the stack-neutral rules in `~/.claude/rules/<namespace>/`, and `<project>/.claude/rules` | mechanically, and it is our host: its `SessionStart` hook runs the sync that wires every agent below |
| **JetBrains AI Assistant** (PyCharm, WebStorm, …) | `<project>/.aiassistant/rules/*.md` — the universal layer, the stack-neutral rules, the declared stacks, and the project's own file | mechanically, but only when that hook runs. On a machine without Claude Code, run `install.py link <project-dir>` per project |
| **OpenCode** and other `AGENTS.md` readers | `$OPENCODE_CONFIG_DIR/AGENTS.md`, whose routing sends them to the rule files in the clone | by instruction, not by loader — one global link, laid at install, no per-project work |

Adding a fourth is one class in `installer/agents.py` overriding only the surfaces its tool can consume.

## Install — once per machine

```bash
# one line — clones with your git auth when needed, then installs (the repo is private; anonymous curl can't reach it)
[ -d ~/.agents-config ] || git clone git@github.com:ProperlyDo/agents-config.git ~/.agents-config && ~/.agents-config/install.py install

# from an existing clone, wherever it lives; also updates the install
./install.py install [--namespace <name>]
```

It touches three things and nothing else: the `SessionStart` hook in `$CLAUDE_CONFIG_DIR/settings.json`, the shared agents dir, and the bridges each present agent gets. Skills are not among them — those are the skills CLI's.

- **`--namespace`** defaults to the clone's origin owner, lowercased (`Acme/agents-config` → `acme`). It names our rules dir, keeping them apart from hand-made files, and lives only in the hook line.
- **`~/.agents`** is fixed, not a knob — the skills CLI and OpenCode both look for that exact path.
- **Rerun it** after a new agent's first launch: a tool is bridged only if its config dir already exists.

| Env var | Purpose | Default |
|---|---|---|
| `CLAUDE_CONFIG_DIR` | Claude's config dir | `~/.claude` |
| `OPENCODE_CONFIG_DIR` | OpenCode's config dir | `$XDG_CONFIG_HOME/opencode` |

The scripts read the same config-dir variables the agents themselves honor. Redirect an agent (e.g. with a per-account alias) and its links move with it.

**Several accounts?** Give each its own config dir, then run the installer once per account inside that account's environment — each gets its own hook and links, so nothing mixes.

**Several config repos in one account?** Their rules stay apart (namespace per dir, and a link belongs to the clone it resolves into), but both want the agent's single entry file — `CLAUDE.md`, OpenCode's `AGENTS.md`. The first one there keeps it; the second warns instead of stealing it. Prefer one repo per account.

Uninstall with `./install.py uninstall`. It removes the hook, the bridges, and everything this repo owns in the shared agents dir — nothing else. Add a `<project-dir>` argument to unwire one project instead. The clone stays; delete it yourself.

## Layout

| In the repo | Purpose |
|---|---|
| `AGENTS.md` | the universal layer: rule routing, working style, naming, code comments. Loads in every session |
| `rules/<stack>.md` | one rule file per stack, linked into the projects that declare it and loaded there in full. `reach: global` in the frontmatter makes a rule stack-neutral instead: linked everywhere, declared or not (`git.md`) |
| `skills/<name>/` | task procedures (Agent Skills spec) — a standalone catalog. Rules state constraints; skills own workflows. Each one is installed on demand by the skills CLI, which treats this repo like any other source |
| `install.py` + `installer/` | the whole lifecycle: `install` / `sync` / `link` / `uninstall`. `installation.py` is the linking machinery; `agents.py` holds one class per agent — each overrides only the surfaces its tool can consume — and the `AGENTS` roster |
| `tests/` | `python3 -m unittest discover` — no dependencies, so it runs wherever `install.py` does. Ownership, reconcile/prune and the wiring round trip: the parts that delete files |

How it lands on a machine — the shared agents dir links into the clone, and agent dirs hold only bridges into the shared dir:

```
~/.agents/                        # the shared agents dir — fixed location
├── AGENTS.md
├── rules/<namespace>/*.md        # all rules; the namespace keeps ours apart from hand-made files
└── skills/<name>                 # the skills CLI's, not ours — we neither create nor prune these
$CLAUDE_CONFIG_DIR/               # bridges only
├── CLAUDE.md      → ~/.agents/AGENTS.md
└── rules/<namespace>/            # the stack-neutral rules only
$OPENCODE_CONFIG_DIR/
└── AGENTS.md      → ~/.agents/AGENTS.md
<project>/
├── AGENTS.md                     # committed — the only per-project file
├── .agents/rules/<namespace>/    # machine-local: project.md + the declared stacks
├── .aiassistant/rules/*.md       # for JetBrains: universal layer + git + declared stacks + project.md
└── .claude/rules  → ../.agents/rules
```

The namespace persists only in the registered hook line; every subcommand takes the same `--namespace` flag. Linking never destroys anything: a name occupied by a file we don't own is skipped with a warning.

## Flow — the three rule steps in detail

### What the project's `AGENTS.md` should hold

- the `stacks:` frontmatter — the opt-in. Remove it and the next session unwires the project
- one routing line: "coding rules for the declared stacks are linked under `.agents/rules/`", for agents that read only the project file
- genuinely project-specific content, and nothing else. No pointers to this repo; generated entry files (`CLAUDE.md`, `GEMINI.md`) stay gitignored

### What a session does

`install.py sync` runs in three steps:

1. `git pull --ff-only` — silent, safe offline; keep `main` always pullable
2. refresh the shared agents dir and every bridge
3. wire the project:
   - **Claude Code** — each declared stack's rule plus `project.md` (a link back to the project's own `AGENTS.md`) lands in `.agents/rules/<namespace>/`, and `.claude/rules` links that dir wholesale, the same shape the skills CLI uses
   - **JetBrains** — flat links in `.aiassistant/rules/` instead; with no global channel, that set carries the universal layer and the stack-neutral rules too
   - **warnings on stderr** for an unknown stack name, and for frontmatter whose `stacks:` line failed to parse — that unwires the project, and a typo should not do so quietly

Every pass reconciles: a link of ours whose name is no longer wanted gets removed, so upstream renames leave no zombies; anything we don't own is never touched. Stack rules never bridge globally — the declaration is what admits them, so Django conventions never reach the Angular repo.

### When rules actually load

Claude loads every linked rule at launch, so the whole declared set is in context before the first tool call. Nothing is gated on reading a matching file: a session that works through the shell, or writes a file it never read, would fire no such trigger. OpenCode and friends follow the routing in `AGENTS.md` instead: `rules/git.md` plus each declared stack's file, read from the clone — which is why they need no project links at all.

### Without Claude Code on the machine

The session hook never fires, so two things become manual:

- JetBrains rule links: `install.py link <project-dir>`, once per project
- updates: nothing pulls this repo for you — rerun `./install.py install` from time to time

## Adding rules and skills

- Prove a convention in one project's `AGENTS.md` first, then promote it here. An always-on constraint becomes a rule; a task-shaped procedure becomes a skill.
- A rule's frontmatter decides its reach — there is no list to maintain. Bare, it is a **stack rule**: linked only into the projects that declare that stack. With `reach: global` it is **stack-neutral**: bridged globally and active in every project, declared or not (`git.md`). So the question to ask before adding the marker is: is this rule true in *every* repo on the machine, including ones that never opted in? Only then mark it.
- Skills ship through the skills CLI, ours included — this repo is just another source: `npx skills add -g ProperlyDo/agents-config --skill <name>` for every project, or without `-g` inside one project, which pins it in that project's `skills-lock.json`. The installer never touches `~/.agents/skills/`, so a skill edited here reaches machines on `npx skills update`, not on the next session.
- Editing a skill often? On your own machine, swap the installed copy for a link at the clone — `npx skills remove -g <name>`, then `ln -s <clone>/skills/<name> ~/.agents/skills/<name>`. Edits go live, the CLI leaves entries it doesn't track alone, and everyone else still gets the pinned copy. It is a local override, not a setup step: nothing in this repo creates it.
- State a convention in one place only. When both `AGENTS.md` and a rule file carry it, which copy wins is anyone's guess.
- Rules cannot import each other. A pair stays bundled by the declaration alone — `stacks: [python, django]` links both files, and each one names the other as applying throughout.
- A rule is always in context wherever it is linked, so its cost is paid every session in that project. Keep a stack file to what is true across that stack; anything narrower belongs in the project's own `AGENTS.md`.

## Verifying

- **`/memory` is the signal** — it lists what loaded at launch, which is the whole set: universal layer, global rules, the project's `AGENTS.md`, and every declared stack. A stack missing there means the project isn't wired, not that a trigger failed to fire; `/context` shows skills.
- **The very first session in a fresh project clone starts without its rules.** Claude scans rule folders at launch, and the hook that creates the links runs just after — one step too late for that single session. `sync` says so whenever it lays links that weren't there (*rules newly linked — restart the session to load them*); a restart is the whole fix, and every later session is complete. To skip it entirely, wire the project by hand right after cloning: `install.py link <project-dir>`.
- **A deleted project `.claude/` is nearly self-healing.** The next session relays `rules`, and `git restore` brings back the committed `settings.json`. The `skills` link is the project's own hook, which only lays it when `.agents/skills` is missing — so recreate it by hand: `ln -s ../.agents/skills .claude/skills`.
- **In PyCharm, our rules appear under `.aiassistant/rules`.** Open a rule file there — seeing our text means the IDE follows the links (a broken link is worth reporting). Then ask the AI chat *"what do the project rules say about git branch naming?"* — an answer naming `<type>/<short-kebab-desc>` proves the rules reach it. Rule type (Always / by patterns) is IDE-side metadata: check it under Settings → Tools → AI Assistant → Project Rules and set Always if needed. `.aiassistant/` stays gitignored — the links are machine-local.
