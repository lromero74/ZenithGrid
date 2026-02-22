Prime context for working on ZenithGrid.

Read the following files to build a complete understanding of the project:

1. **CLAUDE.md** — Development rules and process (the bible)
2. **docs/architecture.json** — Complete architecture reference (models, routers, services, migrations)
3. **docs/ARCHITECTURE.md** — Architecture narrative
4. **docs/DOMAIN_KNOWLEDGE.md** — Trading domain: BTC budget calculation, AI allocation, signal flow
5. **CHANGELOG.md** — Recent version history (last 5 entries)
6. **COMMERCIALIZATION.md** — SaaS roadmap and multi-user considerations

Then check the current state:
```bash
git status
git log --oneline -10
git describe --tags --abbrev=0
./bot.sh status
```

Explain back to me:
- Current version and deployment mode (dev/prod)
- Recent changes (last 3-5 commits)
- Project architecture summary (backend stack, frontend stack, key services)
- Any uncommitted changes or active branches
- Current service health
