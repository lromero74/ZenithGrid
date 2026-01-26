# TODO: Show Min Profit Condition in GUI Indicator Logs

**Date**: 2026-01-26
**Priority**: Medium
**Status**: Backlog

## Issue
When selling/take profit, the "min profit" condition is evaluated but not shown in the GUI indicator logs.

## Details
- Min profit is a condition checked before allowing sells
- Currently logged to backend but not visible in AIBotLogs.tsx
- Users can't see why a sell was blocked due to insufficient profit

## Solution
Need to:
1. Ensure min_profit condition is included in `conditions_detail` array when logging
2. Update indicator_log_service.py to include min_profit in logged conditions
3. Verify AIBotLogs.tsx displays it correctly (should already work if in conditions_detail)

## Files to investigate
- `backend/app/strategies/indicator_based.py` - Where min_profit is checked
- `backend/app/services/indicator_log_service.py` - Logging service
- `frontend/src/components/AIBotLogs.tsx` - Display component

## Related
- Part of making debugging easier for users
- Fits with recent budget logging improvements
