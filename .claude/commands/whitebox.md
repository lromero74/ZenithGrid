Perform a whitebox audit of: $ARGUMENTS

## Audit Scope & Assumptions

You are auditing this area of the ZenithGrid application with the following standing assumptions:

### Architecture Context
- **Multi-user environment**: Multiple users with separate accounts, API keys encrypted per-user, role-based access
- **Security model**: JWT auth + MFA/TOTP, encrypted credentials at rest (Fernet), rate limiting, HTTPS via nginx/Let's Encrypt
- **Infrastructure**: t2.micro EC2 (1 vCPU, 1GB RAM), SQLite, FastAPI async backend, React+Vite frontend
- Consult `docs/architecture.json` for the full architecture reference

### What to Audit

1. **Security**: Auth enforcement, input validation, injection risks (SQL/XSS/command), path traversal, secrets exposure, CSRF, privilege escalation. Check every endpoint touched by this flow.

2. **Performance — Server Side**: Memory usage (especially on 1GB RAM), CPU waste (duplicate work, unnecessary computation), database query efficiency (N+1, missing indexes), response payload size, caching opportunities.

3. **Performance — Client Side**: Memory leaks (stale refs, uncleaned listeners, growing data structures), unnecessary re-renders, bundle size impact, DOM complexity (too many event handlers, excessive nodes).

4. **Responsiveness**: Loading states, perceived latency, prefetch/preload opportunities, streaming vs blocking, debounce/throttle where needed.

5. **Code Quality**: Redundant imports, dead code, error handling gaps, type safety, missing cleanup in useEffect/async operations. Fix pre-existing bugs and lint issues you encounter — don't leave them behind.

6. **Multi-user correctness**: Data isolation between users, race conditions on shared resources, concurrent access safety.

7. **Player awareness**: If the audited area interacts with TTS or media playback, consider both the mini player and full/expanded player modes.

### Rules

- **Don't assume — verify.** Read the actual code. Check actual DB queries. Trace actual data flow.
- **Clean up dead code**: Remove unused imports, unreachable code, commented-out blocks, and orphaned functions/variables you encounter in the audited area. Don't leave debris behind.
- **Modularize as you go**: If any file you touch is approaching or beyond ~1200 lines, split it into logical modules as part of your changes.
- **Watch for circular imports**: When refactoring or splitting files, verify import graphs don't create cycles. Test with `python -c "from app.routers.X import router"` after changes.
- **Lint everything**: `flake8 --max-line-length=120` for Python, `tsc --noEmit` for TypeScript. All code you touch or create must pass.
- **No regressions**: Your fixes must not break existing functionality. If unsure, state what you'd need to test. Always `git diff` against previous before staging — verify you are not losing functionality you did not explicitly intend to remove.
- **Do the right thing, not the lazy thing**: Don't use re-export shims, backwards-compat wrappers, or proxy modules as permanent solutions. When moving code, actually move it — update all consumers to point at the new canonical location and delete the old one. A little extra work now gives us a solid, clean pattern. Fix pre-existing bugs and lint errors you encounter — you are the only coder on this project, so there is no "someone else's problem". If you touch a file and see broken code, fix it.

### Output Format

Present findings as a table:

| ID | Severity | Type | Location | Issue | Fix |
|----|----------|------|----------|-------|-----|

Severity: Critical / High / Medium / Low
Type: Security / Memory / CPU / Responsiveness / Code Quality / Multi-user

Then propose an implementation plan grouped into phases, with files to modify listed.

After presenting findings, wait for user approval before implementing.
