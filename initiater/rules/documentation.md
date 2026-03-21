---
dimension: documentation
severity: critical
---

# Documentation — Sync & Completeness

## Purpose
Users discover agents and features through README.md, Agents.md, and the router. If these diverge, users get confused or miss capabilities.

## Rules
- [ ] README.md "Included Agents" table lists all active agents
- [ ] Agents.md has a section for every active agent
- [ ] agent_router.yaml system prompt lists all specialist agents
- [ ] API endpoint documentation matches actual routes in code
- [ ] Environment variable table in README covers all vars used in code
- [ ] YAML configuration reference documents all supported fields
- [ ] Troubleshooting section is current (no references to removed features)
- [ ] Quick Start instructions work on a fresh clone

## Verification
```bash
# Compare agent YAMLs vs README mentions
diff <(ls agents/*.yaml | xargs -I{} basename {} .yaml | sort) \
     <(grep -oP '`[a-z_]+`' README.md | tr -d '`' | sort -u)

# Check all env vars in code are documented
grep -rhoP '\bos\.environ\[.([A-Z_]+).\]' code_agents/ | sort -u
grep -oP '[A-Z_]{3,}' README.md | sort -u
```

## References
- `README.md`
- `Agents.md`
- `agents/agent_router.yaml`
- `code_agents/config.py`
