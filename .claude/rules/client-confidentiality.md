# Client Confidentiality

This is a personal repository, kept apart from client work. Anyone who can see it can
read the code, the docs, the `CHANGELOG`, the PR descriptions, and `git log`.

**Never name a client, engagement, or work project anywhere in it.**

That means no company names, no repository names, no project codenames, no product names,
and no paths into another client's checkout. Not in code, comments, docstrings, design
notes, plans, commit messages, PR descriptions, test names or fixtures.

## Where this actually slips

Not in code. It slips in the places where you explain *why*:

- a design note with a "prior art" section
- a commit body giving the reasoning behind a choice
- a comment saying where a pattern came from
- a benchmark or a default justified by "on the other project this was…"
- a port plan or migration note pointing at the checkout it came from

Those are exactly the places worth writing — the rule is not to write less, it is to
write the same thing without the attribution.

## How to apply it

Describe the **shape** of the idea, not its origin. The technical content survives
untouched; only the provenance goes.

| Don't | Do |
|---|---|
| "Prior art: `<other-client-repo>`" | "A common pattern for this problem…" |
| "In the `<client>` project the manager earned its place because…" | "A manager earns its place when…" |
| "Copied from `<other-repo>`'s `logger.py`" | "Format is `key=value` with the pid, so concurrent stages stay readable" |
| "This is how `<client>` handled retries" | "Retries belong behind the repository, not in the stage" |

If the reason an idea is good depends on naming where it came from, it is not a good
enough reason to write down.

## A blocklist is not the fix

Do not add a list of client names to this repo for a hook or a lint rule to grep for.
A file enumerating clients, committed to this repository, is a worse leak
than the one it was meant to prevent.

The check is a habit, not a tool: before committing a design note, a plan, or a commit
body that explains a decision, reread it for names that do not belong to this project.
