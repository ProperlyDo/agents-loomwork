# Example tickets

Accepted tickets from the reletting theme (September 2026), copied here so the tone survives even if the originals change. They are trimmed only where the original broke a rule of this skill. Read one or two before writing. The notes under each say what makes it a good example.

## Parent issue

**Title:** Reletting improvement

```markdown
Improve the landlord's reletting workflow: reviewing applicants, inviting them and managing viewings. Each sub-issue can be shipped on its own.
```

One sentence on the theme, nothing else. GitHub lists the sub-issues.

## Single ticket, design left open

**Title:** One applicant window with details and conversation

```markdown
**Goal**
One window per applicant, holding both the profile and the conversation, instead of two separate windows.

**Current Situation**
If you click an applicant a window opens. If you want to navigate to the messages with this applicant another window opens.

**Expected Situation**
- The same window opens from everywhere: the Applications page, the Viewings page, the "Messages" and "View Details" entries in the ⋯ menu at the end of each applicant row, and the email link (#166).
- It shows the applicant's profile, the conversation and the actions for their current status (#173).
- The landlord can switch between profile and conversation at any time. How is up to the developer.

**Acceptance Criteria**
- [ ] The separate detail window is gone, and every entry point opens the new one.
- [ ] Switching never loses a message being typed.
- [ ] All actions work from the window, wherever it was opened from.
```

Current Situation describes what exists today, from the landlord's side. UI elements are named by their English labels. Related tickets are linked by number. The layout is left to the developer.

## Single ticket with a proposal

**Title:** Applications page: show only the next relevant action per applicant

```markdown
**Goal**
Each applicant row shows only the next relevant action. Everything else is in the ⋯ menu.

**Current Situation**
Each row shows up to two action buttons in a fixed order (Approve, Invite, Reject), whatever the applicant's status. A new applicant is offered "Approve" before any viewing has happened. The labels only appear on hover, and the ⋯ menu repeats the visible buttons.

**Expected Situation**
- At most one labelled button per row, chosen by status. Proposal:
  - New → Invite
  - Accepted → Choose as tenant
  - all other statuses → no button
- The ⋯ menu holds the remaining actions and never repeats the visible button.
- The applicant window (#165) and the Viewings page follow the same logic.

**Acceptance Criteria**
- [ ] Each status shows the agreed button and menu entries, with no duplicates.
```

A concrete proposal is marked as one ("Proposal:"), so shaping can still change it. One acceptance criterion is enough when it covers the whole change.

## Follow-up that builds on another ticket

**Title:** Email link opens the right applicant conversation

```markdown
**Goal**
When an applicant responds on a message of the landlord, the link in the "applicant responded" email opens that applicant's conversation within the new window directly.

**Current Situation**
The link in the "applicant responded" email opens the Applications page for the listing. The landlord then has to find the applicant and open the messages themselves.

**Expected Situation**
- Clicking the link opens the Applications page with that applicant's window (#165) open on the conversation.
- It also works if a user still needs to log in first.

**Acceptance Criteria**
- [ ] The email link opens the right conversation, even when the applicant isn't on the first page of the list.
- [ ] Refreshing the page after closing the window doesn't reopen it.
```

The dependency on #165 is a link, not a restatement of #165. The acceptance criteria name the edge cases a tester would otherwise miss.

## Two alternatives

**Title:** Viewings: grouped by listing, with proposed times visible (alternative to #180)

```markdown
> **Alternative to #180.** Only one of the two should be implemented. Decide in shaping.

**Goal**
Landlords can see at a glance which viewings belong to which listing, and which viewings aren't confirmed yet.

**Current Situation**
The Viewings page is one flat list across all listings. When several times were proposed and the applicant hasn't picked one yet, the row shows only the earliest time, so it looks like a fixed appointment.

**Expected Situation**
- Viewings are grouped under a heading per listing.
- An unconfirmed viewing shows "Awaiting confirmation" and the proposed times, instead of looking like a fixed appointment.

**Acceptance Criteria**
- [ ] Viewings appear grouped by listing.
- [ ] Unconfirmed viewings are clearly marked and show their proposed times.
```

**Title:** Viewing schedule: landlord defines slots, applicants book one (alternative to #168)

```markdown
> **Alternative to #168.** Only one of the two should be implemented. Decide in shaping.

**Goal**
The landlord sets up the viewing schedule for a listing once, and applicants book a slot themselves.

**Current Situation**
For every applicant, the landlord proposes one or more viewing times in the invite window by hand. The applicant then picks one of these times. With many applicants, the landlord enters the same times again and again and has to keep track of who comes when, and the Viewings page fills up with separately proposed times (see #168).

**Expected Situation**
- Before inviting, the landlord defines the viewing schedule of the listing. For each day, they enter the date, one or more time windows, the slot duration and the maximum number of applicants per slot.
- The invitation doesn't contain individually proposed times. It contains the list of slots that still have free places, and the applicant books one of them.
- A full slot is no longer offered to other applicants.
- The landlord can see, per slot, who has booked.
- The landlord can add days or time windows later. Changing or deleting a slot that already has bookings informs the applicants concerned.
- The invite window (#167) lets the landlord choose "use viewing schedule" instead of entering times.

**Acceptance Criteria**
- [ ] The landlord can define days, time windows, slot duration and the maximum number of applicants per slot for a listing.
- [ ] Invited applicants see only slots with free places and can book one.
- [ ] A slot never gets more bookings than its maximum.
- [ ] The landlord sees the bookings per slot.
```

Both tickets carry the same alternative line and name each other in the title. A larger feature gets more bullets, but each one is still one thing the landlord sees or does.
