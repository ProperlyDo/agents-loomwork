---
name: backlog-issue
description: Write and create ProperlyDo GitHub issues (a parent with sub-issues, or a single ticket) in the house format (Goal, Current Situation, Expected Situation, Acceptance Criteria) and put them in the Backlog column of the ProperlyDo project board. Use when the user asks to create tickets, issues, stories or sub-issues, to turn findings, PRs or branches into tickets, or to rewrite existing tickets into this format.
---

# backlog-issue

Everything this skill needs travels with it:

- `references/examples.md`: accepted tickets to match in tone and length. Read it before writing.
- `references/pitfalls.md`: drafts that were rejected, and what replaced them. Read it before showing a draft.
- `assets/ticket.md` and `assets/parent.md`: the empty formats.
- `scripts/`: create, link and file the issues.

## Steps

1. **Check the current situation first.** Look at today's `main` (code, and the app if it is running) before describing how things work now. Never describe it from a PR description or from memory. When the ticket comes from a branch or PR, go through its changes point by point and drop every one that `main` already has.
2. **Group before you write.** One ticket per user-facing outcome, not one per finding. Put related small points into one ticket. Several tickets on one theme get a short parent issue.
3. **Pick the repo** by where the user sees the change: screens and the web app go to `ProperlyDo/property-webapp`, and emails and other server behaviour go to `ProperlyDo/property`. Sub-issues can live in the other repo than their parent.
4. **Write the tickets** from the templates in `assets/` and show the user the titles, a one-line summary and the full text of each before creating anything.
5. **Create, link and file them** with the scripts below.
6. **Report back** with one link per ticket and anything that could not be done (e.g. a missing permission).

## Format

A sub-issue or single ticket has exactly the four headings of `assets/ticket.md`, in that order: Goal, Current Situation, Expected Situation, Acceptance Criteria.

A parent issue (`assets/parent.md`) is only one or two sentences saying what the theme improves, plus a link to any related parent. GitHub lists the sub-issues itself, so don't repeat them.

## Writing rules

- **Only the change.** Check every point against today's `main` and write only what differs: behaviour that already exists stays out of Expected Situation and Acceptance Criteria, and Current Situation mentions only what the change builds on.
- **No sentences about what is missing.** Current Situation describes what exists, never "there is no X" or "X is not part of Y". If another ticket covers the missing piece, link it by number instead.
- **User perspective only.** Describe what people see and do, never how to build it. No file names, components, endpoints, fields or libraries.
- **Short.** Every sentence must tell the developer something. No sample texts, no restating the same point in a different way, no "Watch out" lists, no prototype history, no screenshots unless the user supplies them.
- **Name UI elements by their English label** exactly as the app's source text has it ("Messages", "View Details", "+ Listing"). Look up a label you only know in German in `src/locale/messages.de.xlf` of property-webapp (source → target). New wording is given in English only, since German comes through the translation files.
- **Leave design open where the user wants it open.** State the requirement ("the landlord can switch between profile and conversation at any time") and write "How is up to the developer" instead of prescribing a layout.
- **Reference related tickets by number** (#165) instead of vague phrases like "the other sub-issue".
- **Alternatives** start with the line `> **Alternative to #N.** Only one of the two should be implemented. Decide in shaping.`, which also goes on the other ticket, and the title ends with `(alternative to #N)`.
- **Titles:** `Area: what changes`, in plain words (e.g. "Applications page: show only the next relevant action per applicant").
- **No spaced em dashes (" — ")** anywhere. Use a comma, period, colon or parentheses. En dashes in ranges ("9:00–10:00") are fine.
- **Keep the user's wording.** When a ticket has been edited by hand, only restructure it or add what is missing, never rephrase their text.

## Scripts

Run them from this skill's directory; they need an authenticated `gh`.

- `scripts/create-issue.sh <repo> <title> <body-file>` creates the issue in `ProperlyDo/<repo>` and prints its URL. It refuses a title or body with a spaced em dash.
- `scripts/link-sub-issue.sh <parent-repo> <parent-number> <child-repo> <child-number>` makes the child a sub-issue, also across the two repos.
- `scripts/add-to-backlog.sh <issue-url>...` puts every new issue, parents and sub-issues alike, into the Backlog column of project 3 (https://github.com/orgs/ProperlyDo/projects/3).

`add-to-backlog.sh` exits with 3 when the gh token lacks the `project` scope. Create and link the issues anyway, then ask the user to run `gh auth refresh -s project` (it opens a browser, so you can't run it for them) and file the board items afterwards. It exits with 4 when the Status field has no "Backlog" option and lists the existing options; ask the user which one to use.
