# Pull Request Creation

## How to Create a PR

1. Read `.github/PULL_REQUEST_TEMPLATE.md` to get the full template
2. Fill in **Summary** with: what changed, why
3. Fill in **Test Plan** with: what commands were run, what was verified
4. Go through every **Checklist** item — mark `[x]` if satisfied, `[ ]` if needs review
5. ALWAYS include the **AI-Assisted Code** section when AI generated code
6. Create the PR as a draft using `gh pr create --draft`

Use HEREDOC for the body:

```bash
gh pr create --draft --title "type(scope): description" --body "$(cat <<'EOF'
## Summary
[Description of what changed and why]

## Test Plan
- Ran `just test` — all tests pass
- Ran `just check` — no lint errors

---

## Checklist
- [ ] Tests added/updated
- [ ] Documentation updated (if applicable)
- [ ] `docs/glossary.md` updated for every term this PR creates, renames or redefines

---

## AI-Assisted Code
- [x] Verified imports/methods actually exist
- [x] Tested actual behavior (not just "looks right")
- [ ] Business logic reviewed by domain expert
EOF
)"
```

## Pre-PR Quality Gates (Mandatory)

Before creating a PR:

1. **Run tests**: `just test`
2. **Run quality checks**: `just check`
3. Do NOT create a PR if tests fail

## PR Title Format

`type(scope): description` — e.g., `feat(pipeline): add customer dimension model`

Types: `feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, `test:`
