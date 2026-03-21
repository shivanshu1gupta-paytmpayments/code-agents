---
dimension: handoff
severity: info
---

# Handoff — Onboarding & Context Transfer

## Purpose
New contributors or operators should be able to get productive quickly. Session and context management should be clear.

## Rules
- [ ] Onboarding steps are documented (clone, install, configure, run)
- [ ] Quick Start section covers the happy path end-to-end
- [ ] Session management is explained with examples
- [ ] Multi-turn conversation flow is documented
- [ ] Agent selection guidance exists (router or direct)
- [ ] Common first-time issues are in Troubleshooting

## Verification
```bash
# Check Quick Start completeness
grep -c '```' README.md  # code blocks in README

# Check session docs
grep -i 'session' README.md Agents.md
```

## References
- `README.md` (Quick Start, Session Management, Troubleshooting)
- `Agents.md` (Multi-Turn Sessions, Typical Workflow)
