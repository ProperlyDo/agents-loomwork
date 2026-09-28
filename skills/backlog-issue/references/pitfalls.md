# Pitfalls

Drafts that break a rule, each with what to write instead. The first two were rejected in a real review (onboarding ticket, September 2026).

## Describing what is missing

Rejected, in Current Situation:

> Onboarding is a four-step form where every building and flat is typed in by hand. The assistant is not part of onboarding, and there is no introduction to the menu or the portfolio pages.

The second sentence tells the developer nothing the Expected Situation doesn't already say. Current Situation describes what exists. When a missing piece belongs to another ticket, link it by number instead.

Accepted:

> Onboarding is a four-step form (Welcome, Your profile, Your portfolio, All set). "Your portfolio" and "All set" list only what was added in this browser.

## Writing up the whole branch instead of the difference

A ticket drafted from a branch listed everything the branch does, including behaviour `main` already had: the assistant could already read a rental contract and add a flat after confirmation, and the Features page already switched the AI features on. Those points were dropped, and Current Situation names the existing behaviour the change builds on:

> In the app, Properly can read one rental contract at a time and add a flat or a house after confirmation, and each flat it adds gets its own new building.

Go through the branch's changes one by one and check each against `main` before it goes into Expected Situation or Acceptance Criteria.

## Building instructions

Rejected:

> The `approve` endpoint no longer creates the tenant; a new `confirm-contract` action does.

Accepted:

> "Select applicant" no longer invites anyone. "Confirm contract" asks the landlord to confirm the rental contract is concluded before the tenant is invited.

## German labels

Rejected: "Klick auf ‚Kontakt' in den Listings".

Accepted: "Click "Messages" on the Applications page". Look up the English source text in `src/locale/messages.de.xlf` of property-webapp when you only know the German label.
