---
dimension: cross-platform
severity: warning
---

# Cross-Platform — OS Compatibility & Docker

## Purpose
The project should work on macOS, Linux, and in Docker without OS-specific workarounds.

## Rules
- [ ] Dockerfile exists and builds successfully
- [ ] Docker image runs and serves the API
- [ ] File paths use os.path or pathlib (no hardcoded / or \\)
- [ ] Shell scripts have correct shebangs (#!/usr/bin/env bash)
- [ ] Shell scripts work on both macOS and Linux (no GNU-only flags)
- [ ] .dockerignore excludes unnecessary files
- [ ] Python version requirement is documented and enforced

## Verification
```bash
# Check Dockerfile
test -f Dockerfile && echo "exists"

# Check shebangs
head -1 scripts/*.sh

# Check for hardcoded paths
grep -rn "'/Users/\|C:\\\\" code_agents/

# Build Docker image
docker build -t code-agents-test . 2>&1 | tail -5
```

## References
- `Dockerfile`
- `.dockerignore`
- `scripts/*.sh`
- `pyproject.toml` (python version)
