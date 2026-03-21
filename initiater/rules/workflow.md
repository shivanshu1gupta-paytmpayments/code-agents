---
dimension: workflow
severity: critical
---

# Workflow — Agent Creation & Cross-File Sync

## Purpose
Every time a new agent is added, multiple files must be updated in lockstep. Missing one creates confusion for users who discover agents in one place but not another. This checklist ensures nothing is missed.

## Rules
- [ ] Every agent in `agents/*.yaml` (excluding `.disabled`) is listed in `agent_router.yaml` system prompt
- [ ] Every agent is listed in README.md "Included Agents" table
- [ ] Every agent is listed in README.md "Option B" connections table
- [ ] Every agent is listed in README.md "Project Structure" tree
- [ ] Every agent is documented in Agents.md with its own section
- [ ] agent_router.yaml specialists list matches actual agent files
- [ ] Agents.md "Maintenance" section is up to date with the sync checklist
- [ ] New agent YAML follows the same field ordering as existing agents

## Verification
```bash
# List all active agent YAML files
ls agents/*.yaml | grep -v disabled

# Check agent_router.yaml mentions each agent name
grep -oP '(?<=\*\*)[a-z-]+(?=\*\*)' agents/agent_router.yaml

# Check README.md Included Agents table
grep '`code-' README.md

# Check Agents.md sections
grep '^## ' Agents.md
```

## References
- `agents/*.yaml`
- `agents/agent_router.yaml`
- `README.md` (Included Agents table, Option B table, Project Structure)
- `Agents.md`
