---
description: Internal release/PR checklist for strata-buy-plugin. Use before committing a change, opening a PR, or cutting a version in THIS repo — it enforces version/changelog coherence, the verification drill, and consistent commit/PR shape. Not shipped to plugin users.
---

# PR / release pass for strata-buy-plugin

Run this before any commit or PR in this repo. It exists so every change
lands the same way: verified, versioned, and evidenced.

## 1. Pre-commit checklist

Work through all of these; fix, don't waive:

- [ ] **Verification drill ran** (see CLAUDE.md "Verifying changes"):
      real-file regression + synthetic attack variants for the failure
      mode touched. Exit codes checked directly, not through a pipe.
- [ ] **Version coherence**: if the change is user-facing (scripts,
      skills, template, reference docs), `.claude-plugin/plugin.json`
      version is bumped and the CHANGELOG's top entry matches that
      version and today's date. Internal-only changes (CLAUDE.md, this
      skill, CI) need no bump.
- [ ] **CHANGELOG entry is evidence-based**: measured numbers ("180s →
      2.9s at −0.05% points"), confirmed-vs-inferred labels on any Strata
      behavior claim, and the *why* when behavior changed. No adjectives
      doing the work of data.
- [ ] **No client data in the diff**: `git diff --staged --stat` shows no
      avails/buy XML, no real rates or budgets in fixtures or docs. The
      only sanctioned fixture is `reference/examples/sample-avails.xml`.
- [ ] **Skill/doc paths**: skills reference `${CLAUDE_PLUGIN_ROOT}`, never
      absolute or cache paths. Install lines say `python3 -m pip`.
- [ ] **Cache note**: if scripts/skills changed, remember the installed
      plugin runs from the marketplace cache — state in the PR whether the
      cache was synced for testing or the change is untested-via-skills.

## 2. Commit message shape

```
<Component summary line, imperative, ≤72 chars> (<version if bumped>)

- What changed and why, with measured evidence where it exists
- One bullet per logical change; name confirmed vs inferred for any
  Strata-behavior claim

Co-Authored-By: Claude <model name> <noreply@anthropic.com>
```

Match the existing log (`git log --oneline`) for tone: component-first,
evidence in the body, no filler.

## 3. PR body template

```markdown
## Summary
<2–4 sentences: what changed, why, and the user-visible effect>

## Evidence
| Check | Before | After |
|---|---|---|
| <regression / attack case> | <result> | <result> |

## Verification
<the exact commands run and their pass/fail, including exit-code checks>

## Changelog
<version> — <top CHANGELOG bullet(s) for this change>
```

## 4. Cutting a release

1. CHANGELOG top entry finalized (version, date, evidence).
2. `plugin.json` version matches.
3. Full pipeline smoke test on a real avails file: parse → optimize →
   inject → validate → simulate, both gates PASS.
4. Tag after merge: `git tag v<version>` on the merge commit.
