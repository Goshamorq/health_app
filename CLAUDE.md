# health_app

Local web-based helper app for a single user (the project owner), running on macOS. No scaling, no production deploy, no multi-user logic, no sharing.

## Principles

- Simple solution beats "proper enterprise". Three similar lines are better than a premature abstraction.
- Tests when they pay off, not by obligation. TDD is not dogma here.
- Do not add observability, hardening against external threats, migration strategies, ADRs, or performance optimization without a concrete reason.
- Runs locally on this Mac. Single user. Trusted environment.

## Structure

```
.claude/skills/   → symlinks to agent-skills/skills/<name> (active skills)
agent-skills/     → clone of https://github.com/addyosmani/agent-skills (source of skills)
```

## Active skills

Stored in `.claude/skills/` as symlinks pointing to `agent-skills/skills/<name>`.

**Define:** `idea-refine`, `spec-driven-development`
**Plan:** `planning-and-task-breakdown`
**Build:** `incremental-implementation`, `source-driven-development`, `frontend-ui-engineering`
**Verify:** `debugging-and-error-recovery`, `browser-testing-with-devtools`
**Review:** `code-simplification`
**Ship:** `git-workflow-and-versioning`
**Meta:** `using-agent-skills`

Deliberately **not enabled** as overkill for a solo local app:
`interview-me`, `test-driven-development`, `context-engineering`, `doubt-driven-development`, `api-and-interface-design`, `code-review-and-quality`, `security-and-hardening`, `performance-optimization`, `ci-cd-and-automation`, `deprecation-and-migration`, `documentation-and-adrs`, `shipping-and-launch`.

To enable a skill later:
```bash
cd .claude/skills && ln -sf ../../agent-skills/skills/<name> <name>
```

## agent-skills slash commands

Commands in `agent-skills/.claude/commands/` (`/spec`, `/plan`, `/build`, `/test`, `/review`, `/code-simplify`, `/ship`) assume the full skill set and may invoke skills that are not enabled here. Use with awareness, or invoke skills directly.

## Boundaries

- Always: keep solutions minimal; add a new dependency only if its absence is genuinely painful.
- Never: add CI, tests-for-the-sake-of-tests, feature flags, backup strategies, or similar infrastructure without an explicit request.
- Never: complicate auth or security — the app listens on localhost for a single user.
