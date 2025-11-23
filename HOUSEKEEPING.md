# Repository Housekeeping - Refactoring Only

**Created**: 2025-11-23
**Branch**: HouseKeeping_1.0
**Status**: Planning Phase

---

## ⚠️ CRITICAL CONTEXT

This is a **live trading platform** - changes have real financial impact.
- We **CANNOT** run tests during refactoring (no mock trading environment)
- Must be **EXTREMELY** conservative and methodical
- Manual testing required in staging after each commit

---

## 🎯 OBJECTIVES

### File Organization & Size Management
- **Target file size**: 200-400 lines maximum per file
- **Hard limit**: No file should exceed 500 lines
- Files must be small enough for AI to read and understand entirely at once
- Split large files into smaller, focused modules by logical boundaries
- Organize code into logical directories following best practices
- Create clear, descriptive file and directory names
- For files >1000 lines: create detailed splitting plan before executing

### Import and Declaration Management
- Fix import order (standard library, third-party, local imports)
- Ensure all imports are at top of files
- Remove unused imports
- Verify all declarations are properly scoped
- Ensure dependencies are declared before use
- Update all import paths when files are moved or split

### Code Structure
- Group related functions/classes together
- Maintain proper separation of concerns
- Keep configuration separate from logic

---

## ✅ CRITICAL RULES

1. **Preserve 100% of existing functionality**
2. **Do NOT add any new features or capabilities**
3. **Do NOT remove any existing features or capabilities**
4. **Work in branch: HouseKeeping_1.0**

---

## 🚫 ABSOLUTELY PROHIBITED

### No Partial Work
- NEVER leave TODO comments, placeholders, or "finish this later" notes
- NEVER say "this is getting complex, let me simplify and come back to it"
- NEVER implement partial functionality with plans to complete it later
- NEVER skip any part of the refactoring because it seems difficult
- NEVER leave a file partially refactored

### If Step Becomes Too Complex
1. STOP immediately
2. Explain what makes it complex
3. Ask how to proceed
4. Wait for response before continuing

### Each Step Must Be 100% Complete
At the end of each step, explicitly state:
> "Step X is 100% complete. All functionality from [original file] has been preserved in [new location]."

---

## ❌ WHAT NOT TO DO

- Do not optimize algorithms or change logic
- Do not add error handling that doesn't exist
- Do not add logging, comments, or documentation unless moving existing ones
- Do not change variable names or function signatures
- Do not "improve" the code - just organize it
- Do not make multiple unrelated changes in one commit

---

## 📋 PROCESS

1. ✅ Create the HouseKeeping_1.0 branch first
2. ✅ Identify all files over 500 lines and prioritize splitting them first
3. ✅ Present detailed refactoring plan broken into small, discrete steps
4. ⏳ Make changes in very small, isolated commits (one file or module at a time)
5. ⏳ After each change, verify syntax and perform static analysis
6. ⏳ Document EVERY change: what was moved, from where, to where, and why
7. ⏳ Create testing checklist for manual verification after each commit

---

## 📊 CURRENT STATUS

**Phase**: Initial Analysis & Planning

**Next Steps**:
1. Analyze repository structure
2. Identify all files over 500 lines
3. Present detailed, step-by-step refactoring plan with risk assessment

---

## 🔍 REPOSITORY ANALYSIS

### Files Requiring Refactoring (>500 lines)
_(To be populated during analysis)_

### Refactoring Plan
_(To be created after analysis)_

### Risk Assessment
_(To be completed for each refactoring step)_

---

## 📝 REFACTORING LOG

### Branch Creation
- [ ] Create HouseKeeping_1.0 branch from main

### File Splits (Prioritized by Size)
_(To be populated with specific tasks)_

---

## ✅ TESTING CHECKLIST

After each commit, manually verify:
- [ ] Backend starts without errors
- [ ] Frontend starts without errors
- [ ] All API endpoints respond correctly
- [ ] Bot execution works (check logs)
- [ ] Position management works (open/close/edit)
- [ ] Database operations succeed
- [ ] WebSocket connections establish
- [ ] No console errors in browser
- [ ] No Python exceptions in logs

---

## 🎯 SUCCESS CRITERIA

- All files are ≤ 500 lines (target: 200-400 lines)
- All imports are properly ordered and scoped
- All functionality preserved 100%
- No runtime errors introduced
- Code is organized by logical boundaries
- Clear directory structure
- All changes committed in small, isolated commits
- Full documentation of what was moved and why

---

## 📌 IMPORTANT REMINDERS

- **Safety First**: When in doubt, don't change it
- **Conservative Approach**: Rather refactor 60% safely than risk breaking critical trading logic
- **No Feature Changes**: This is REFACTORING ONLY
- **100% Complete**: Each step must be fully complete before moving to next
- **Real Financial Impact**: This is a live trading platform

---

## 🔗 RELATED DOCUMENTS

- `CLAUDE.md` - Project-specific instructions
- `FEATURE_HANDOFF.md` - Recently completed feature work
- `.git/` - Version control history
