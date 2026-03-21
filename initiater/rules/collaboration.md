---
dimension: collaboration
severity: info
---

# Collaboration — Contributing & Code Ownership

## Purpose
Clear contribution guidelines reduce friction for new contributors and maintain quality.

## Rules
- [ ] CONTRIBUTING.md or contributing section exists
- [ ] PR process is documented
- [ ] Branch naming convention is stated
- [ ] Code review expectations are set
- [ ] Issue/bug reporting process is documented
- [ ] License file exists and is referenced
- [ ] Development setup instructions work (poetry install, pytest)

## Verification
```bash
# Check for contributing docs
test -f CONTRIBUTING.md && echo "exists" || grep -l 'Contributing' README.md

# Check license
test -f LICENSE && echo "LICENSE exists"

# Verify dev setup
poetry install --with dev 2>&1 | tail -3
```

## References
- `README.md` (Contributing section)
- `LICENSE`
- `pyproject.toml`
