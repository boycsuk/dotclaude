# User stories

> **What this file is.** The behavioral contract of the product: everything
> the user must be able to DO, written as user stories — independent of which
> screen or platform implements it. It is the single source of truth for
> "what can this product do for its user?". A reader of this file alone should
> be able to list every capability without opening the source or the other
> docs.
>
> **What this file is NOT.** Not the API (`backend.md` lists endpoints), not
> the visual map (`ui.md` lists screens and tokens), not implementation. A
> story says *what the user achieves and why*, never *how it is built*.
>
> **Platform model: parity by default, exceptions only.** Assume every story
> works the same on every client (web, iOS, Android, desktop). Write each
> story once. Only when a capability genuinely differs on a platform do you
> add a short exception line under it — do not tag every story with a platform
> matrix when almost all of them are identical. If a whole story is
> platform-specific, say so in its own line.
>
> **How to keep it true (no tooling required).** Plain Markdown — maintain it
> by hand in any editor (Xcode, a sandboxed editor, a teammate without Claude
> Code). With Claude Code, `/update-docs` can update it from the diff. Update
> it whenever a user-facing capability is added, removed, or changes what the
> user can achieve. **Coverage over depth:** every capability must appear,
> even as a one-liner; the *what* must be exhaustive, the *how* can stay out.
> A new capability with no story here is a contract that does not exist for
> anyone reading only `docs/`.

## Format

Group stories by area (epic). Within each, one bullet per capability:

> As a **\<role\>**, I can **\<do something\>** so that **\<benefit\>**.

Add nested lines only when they carry contract-level information:
- **Acceptance:** the observable condition that proves it works (optional but
  recommended for non-obvious stories).
- **Platform exception:** only if a platform differs. e.g.
  *"iOS only — uses the native share sheet"* or *"Not on web — requires the
  camera"*.

Keep stories outcome-focused. "I can reset my password" is a story; "the
reset button is blue" is not (that is `ui.md`), and "calls `POST /auth/reset`"
is not (that is `backend.md`).

## Roles

<!-- List the kinds of user the product serves, one line each. Example:
- **Visitor** — not signed in.
- **Member** — signed-in end user.
- **Admin** — manages users and content.
Remove this placeholder once real roles exist. -->

## Stories

<!-- One `### Epic` per area, bullets underneath. Remove this placeholder
block once real stories exist.

### Account

- As a **visitor**, I can sign up with email and password so that I get my own
  account.
- As a **member**, I can sign in and stay signed in across restarts so that I
  do not re-authenticate every time.
- As a **member**, I can reset a forgotten password so that I regain access.
  - Acceptance: a reset link sent to the registered email lets me set a new
    password; the old one stops working.
- As a **member**, I can sign out so that my session ends on this device.

### Activity

- As a **member**, I can see my most recent activity on the home screen so
  that I know what happened last.
- As a **member**, I can browse my full history filtered by date range so
  that I can find an old item.
- As a **member**, I can export my history so that I can keep an offline copy.
  - Platform exception: web exports a CSV download; iOS/Android open the
    native share sheet. Not available on the desktop client yet.

### Administration

- As an **admin**, I can deactivate a member so that they lose access.
  - Platform exception: web only — there is no admin UI on the mobile clients.
-->
