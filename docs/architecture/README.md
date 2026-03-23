# Architecture Reference

This directory contains the ZenithGrid architecture documentation, split into three focused files.

## Files

| File | Contents | When to Update |
|------|----------|----------------|
| `index.json` | Version, stack, data flow, multi-user isolation notes | Version bumps, stack changes, new isolation hardening rounds |
| `backend.json` | Routers, sub-routers, models, services, trading engine, exchange clients, strategies, middleware, migrations | New routers, models, services, migrations |
| `frontend.json` | Pages, components, contexts, hooks, API layer, types, utilities | New pages, components, contexts, hooks |

## Version Field

The `version` field in `index.json` must match the latest git tag. It is updated as part of every tagged release commit. The `/shipit` command handles this via:

```bash
sed -i 's/"version": "vOLD"/"version": "vNEW"/' docs/architecture/index.json
```

## Structure

`backend.json` and `frontend.json` are standalone JSON objects (not wrapped in a key). Their root is the section content directly. This allows each file to be read independently without parsing the full combined document.

`index.json` includes a `split_files` field pointing to both sibling files for tooling that needs to discover them programmatically.
