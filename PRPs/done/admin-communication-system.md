# PRP: Admin Communication System

**Feature**: Admin-to-user messaging with official admin identity, admin display names, and verified admin badges
**Created**: 2026-03-14
**One-Pass Confidence Score**: 7/10

> Medium-complexity feature touching auth models, chat system, admin UI, settings, and frontend rendering. The chat system is well-structured with clear extension points, but the breadth of changes (model, migration, 3 backend files, 5+ frontend files) warrants careful ordering.

---

## Context & Goal

### Problem
Admins have no way to officially communicate with users from the admin panel. They can only DM friends. There's no distinction between a personal message and an official admin communication. Users could also spoof admin identity by putting unicode badge characters in their display name.

### Solution
1. **Admin DM channels** — new channel type `"admin_dm"` for official admin-to-user communication
2. **Admin display name** — optional field on User model (e.g., "Louis" instead of "Louis Romero"), used in admin channels
3. **Admin badge** — server-provided `is_admin` boolean flag rendered as a verified shield icon; cannot be spoofed via display name text
4. **Two communication modes** from admin Users tab:
   - "Message as Friend" — opens/creates regular DM (only if friends)
   - "Message as Admin" — opens/creates admin_dm channel (any user, no friendship required)
5. **Settings page** — admin users can set their admin display name

### Who Benefits
- **Admins**: Can reach any user officially, with clear identity
- **Users**: Can distinguish official admin messages from personal ones
- **Security**: Admin badge is server-verified, not spoofable

### Scope
- **In**: admin_display_name column, admin_dm channel type, admin badge rendering, admin chat initiation from Users tab, Settings UI for admin display name
- **Out**: Admin broadcast to all users, admin-only channels visible to multiple admins, admin message templates

---

## Architecture

### Data Flow

```
Admin clicks chat icon on user row in Admin > Users tab
  ↓
Modal: "Message as Friend" (if friends) | "Message as Admin"
  ↓
POST /api/chat/channels { type: "admin_dm", friend_id: <user_id> }
  ↓
get_or_create_admin_dm() — no friendship check required
  ↓
Channel created with type "admin_dm"
  ↓
Messages in admin_dm use admin_display_name + " (Admin)" as sender_name
  ↓
Frontend renders admin badge (shield icon) from is_admin flag — NOT from text
```

### Database Changes

**User model** — add one column:
```python
admin_display_name = Column(String, nullable=True)  # Optional admin alias
```

**ChatChannel model** — extend `type` to support `"admin_dm"`:
- Existing types: `"dm"`, `"group"`, `"channel"`
- New type: `"admin_dm"` — behaves like DM but:
  - No friendship requirement
  - Sender name shows `admin_display_name (Admin)` for the admin user
  - Frontend renders with shield icon and distinct styling

**No new tables needed.** The existing ChatChannel + ChatChannelMember + ChatMessage models handle everything.

### API Changes

| Method | Path | Change |
|--------|------|--------|
| `POST` | `/api/chat/channels` | Accept `type: "admin_dm"` (admin permission required) |
| `PUT` | `/api/users/admin-display-name` | New — set admin display name (admin only) |
| `GET` | `/api/chat/channels` | Return `is_admin_channel` flag for admin_dm channels |
| `GET` | `/api/chat/channels/{id}/messages` | Include `is_admin` flag on each message sender |
| `GET` | `/api/chat/channels/{id}/members` | Include `is_admin` flag on each member |

---

## Existing Code Patterns (Reference)

### 1. Chat Channel Creation (`backend/app/services/chat_service.py` lines 204-261)

`get_or_create_dm()` is the template for `get_or_create_admin_dm()`:
```python
async def get_or_create_dm(db, user_id, friend_id):
    # 1. Validate friendship
    # 2. Check for existing DM via aliased joins
    # 3. Create new channel if not found, both users as "owner"
```

For admin_dm: skip friendship validation, use `type="admin_dm"` in query and creation. Admin gets "owner" role, user gets "member" role.

### 2. Sender Name Resolution (`backend/app/services/chat_service.py` lines 524-525)

Currently:
```python
sender = await db.get(User, user_id)
sender_name = sender.display_name if sender else f"User {user_id}"
```

For admin_dm channels: check if channel is admin_dm AND sender is the admin → use `admin_display_name (Admin)` format.

### 3. Channel Type Pattern in Frontend (`frontend/src/pages/games/hooks/useChat.ts` line 24)

```typescript
type: 'dm' | 'group' | 'channel'
```

Extend to: `'dm' | 'group' | 'channel' | 'admin_dm'`

### 4. Channel Icon Pattern (`frontend/src/pages/games/components/social/ChatPanel.tsx` line 51)

```typescript
const Icon = channel.type === 'dm' ? MessageSquare : channel.type === 'group' ? Users : Hash
```

Add: `channel.type === 'admin_dm' ? ShieldCheck : ...`

### 5. Display Name Router Pattern (`backend/app/routers/display_name_router.py`)

The existing `PUT /api/users/display-name` endpoint is the template:
- Pydantic schema with validation
- Case-insensitive uniqueness check
- Returns updated name

For admin display name: similar pattern, but only admin users can set it, and the uniqueness constraint is optional (admin names don't need to be globally unique — there are few admins).

### 6. Admin Users Tab (`frontend/src/pages/admin/AdminUsers.tsx`)

The user list already shows online indicators. Add a chat icon button per user row (similar to the existing Session/Groups/Enable buttons at lines 253-280).

### 7. Admin Badge Anti-Spoofing

The `display_name` validation pattern (`^[a-zA-Z0-9_\-]{3,20}$` in display_name_router.py line 42) already blocks unicode. The admin badge must be rendered as a React component (shield icon) based on a server-provided boolean, never from text content.

### 8. Migration Pattern (`backend/migrations/add_session_limits.py`)

```python
MIGRATION_NAME = "add_admin_display_name"

async def run_migration(db):
    try:
        await db.execute(text(
            "ALTER TABLE users ADD COLUMN admin_display_name VARCHAR(50)"
        ))
    except Exception as e:
        if "already exists" not in str(e).lower() and "duplicate" not in str(e).lower():
            raise
```

---

## Implementation Tasks (in order)

### Backend

1. **Migration** — `backend/migrations/add_admin_display_name.py`
   - Add `admin_display_name VARCHAR(50)` to users table

2. **User model** — `backend/app/models/auth.py`
   - Add `admin_display_name = Column(String(50), nullable=True)` after `display_name`

3. **Admin display name endpoint** — `backend/app/routers/display_name_router.py`
   - Add `PUT /api/users/admin-display-name` (requires ADMIN_USERS permission)
   - Schema: `admin_display_name: str = Field(..., min_length=2, max_length=50)`
   - Less restrictive pattern than regular display names (allow spaces for real names like "Louis")

4. **Chat service** — `backend/app/services/chat_service.py`
   - Add `get_or_create_admin_dm(db, admin_id, user_id)`:
     - No friendship check
     - Query for existing admin_dm between the two users
     - Create with type="admin_dm", admin as "owner", user as "member"
   - Update `send_message()` sender name resolution:
     - If channel.type == "admin_dm" and sender is the admin (owner): use `f"{sender.admin_display_name or sender.display_name} (Admin)"`
   - Update `get_user_channels()` to handle admin_dm type:
     - Name shows as "Admin: <admin_display_name>" for the user's view
     - Name shows as "<user_display_name>" for the admin's view
   - Update `_build_message_dict()` or callers to include `is_admin: bool` flag
   - Update `get_channel_members()` to include `is_admin: bool` flag per member

5. **Chat router** — `backend/app/routers/chat_router.py`
   - Update `CreateChannelRequest` type pattern: `"^(dm|group|channel|admin_dm)$"`
   - In `create_channel()`: if type == "admin_dm", require ADMIN_USERS permission, call `get_or_create_admin_dm()`
   - DM validation for admin_dm: skip friendship check (admin can message anyone)

6. **Chat WS handler** — `backend/app/services/chat_ws_handler.py`
   - No changes needed — sender_name resolution happens in chat_service

7. **Admin users endpoint** — `backend/app/routers/admin_router.py`
   - Add `admin_display_name` to the user list response (already returns user fields)

### Frontend

8. **Chat types** — `frontend/src/pages/games/hooks/useChat.ts`
   - Extend ChatChannel type: `'dm' | 'group' | 'channel' | 'admin_dm'`
   - Add `is_admin?: boolean` to ChatMessage interface
   - Add `is_admin?: boolean` to ChatMember interface

9. **ChatPanel** — `frontend/src/pages/games/components/social/ChatPanel.tsx`
   - Add `ShieldCheck` icon for admin_dm channels
   - Style admin_dm channels with a subtle accent (e.g., amber/gold border)

10. **MessageBubble** — `frontend/src/pages/games/components/social/MessageBubble.tsx`
    - If `msg.is_admin`: render shield icon next to sender_name (line 109-110)
    - Use amber/gold color for admin sender names
    - Shield icon: `<ShieldCheck className="w-3 h-3 text-amber-400 inline" />`

11. **AdminUsers chat button** — `frontend/src/pages/admin/AdminUsers.tsx`
    - Add message icon button per user row
    - On click: if friends, show modal with two options ("As Friend" / "As Admin")
    - If not friends: directly open as admin
    - Both options create/navigate to the appropriate channel
    - Navigation: use React Router to navigate to `/social` with channel ID

12. **Settings page** — `frontend/src/pages/Settings.tsx`
    - For admin users: show "Admin Display Name" field below regular display name
    - Edit inline with save button
    - Hint: "This name appears when you message users as Admin"

13. **API types** — `frontend/src/services/api.ts`
    - Add `admin_display_name?: string | null` to AdminUser interface

14. **NewChatDialog** — `frontend/src/pages/games/components/social/NewChatDialog.tsx`
    - No changes needed — admin DMs are created from the admin panel, not from the chat panel

### Tests

15. **Backend tests** — `backend/tests/services/test_admin_chat.py`
    - `test_get_or_create_admin_dm_no_friendship_required`
    - `test_admin_dm_sender_name_uses_admin_display_name`
    - `test_admin_dm_channel_not_duplicated`
    - `test_non_admin_cannot_create_admin_dm`
    - `test_admin_badge_flag_on_messages`

---

## Admin Badge Rendering (Anti-Spoof)

**The admin badge MUST be rendered from a server-provided `is_admin` boolean, never from display name text.**

### Backend
Every message and member response includes:
```python
"is_admin": bool  # True if user has ADMIN_USERS permission
```

Checked via:
```python
# Simple: check is_superuser (fast, no joins)
# Or proper RBAC: check permission chain (slower but correct)
# Decision: use is_superuser for display purposes (all admins are superusers currently)
```

### Frontend
```tsx
// In MessageBubble — render badge AFTER sender name, as a separate element
<span className="text-xs font-medium text-amber-400">
  {msg.sender_name}
</span>
{msg.is_admin && (
  <ShieldCheck className="w-3 h-3 text-amber-400 inline ml-0.5" title="Admin" />
)}
```

This cannot be spoofed because:
1. `is_admin` comes from the server (User.is_superuser check)
2. The shield icon is a Lucide React component, not text
3. Display names are validated to block unicode (`^[a-zA-Z0-9_\-]{3,20}$`)
4. Even if someone named themselves "Admin", they wouldn't get the shield icon

---

## Channel Name Display Logic

| Viewer | Channel Type | Name Shown |
|--------|-------------|------------|
| Admin viewing their admin_dm | User's display_name | "JohnDoe" |
| User viewing admin_dm from admin | Admin's admin_display_name + " (Admin)" | "Louis (Admin)" |
| Admin in channel list | User's display_name | "JohnDoe" |
| User in channel list | "Admin: " + admin_display_name | "Admin: Louis" |

---

## PostgreSQL Migration

```sql
ALTER TABLE users ADD COLUMN admin_display_name VARCHAR(50);
```

Single column, nullable, no index needed (rarely queried directly).

---

## Validation Gates

```bash
# Python lint
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m flake8 --max-line-length=120 \
  app/models/auth.py \
  app/routers/display_name_router.py \
  app/routers/chat_router.py \
  app/routers/admin_router.py \
  app/services/chat_service.py

# TypeScript
cd /home/ec2-user/ZenithGrid/frontend && npx tsc --noEmit

# Tests
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m pytest tests/services/test_admin_chat.py -v

# Migration
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -c "
import asyncio
from app.database import async_session_maker
from migrations.add_admin_display_name import run_migration
async def main():
    async with async_session_maker() as db:
        await run_migration(db)
        await db.commit()
asyncio.run(main())
"
```

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Admin spoofing via display name | Badge is a React component from `is_admin` boolean, not text |
| Unicode badge characters in names | Display name regex already blocks unicode (`^[a-zA-Z0-9_\-]$`) |
| Admin DMs flooding users | Rate limit applies to admin messages too (10/5s per user) |
| Multiple admins messaging same user | Each admin gets their own admin_dm channel with the user |
| Admin display name not set | Falls back to regular display_name |
| Non-admin tries to create admin_dm | Router checks ADMIN_USERS permission, returns 403 |

---

## Key Files to Read/Modify

| File | Action | Lines |
|------|--------|-------|
| `backend/app/models/auth.py` | Add column | Line 65 area |
| `backend/app/models/__init__.py` | No change needed | — |
| `backend/app/services/chat_service.py` | Add get_or_create_admin_dm, modify sender resolution | Lines 204-261, 524-525 |
| `backend/app/routers/chat_router.py` | Extend type pattern, add admin_dm handling | Lines 29-33, 74-107 |
| `backend/app/routers/display_name_router.py` | Add admin display name endpoint | End of file |
| `backend/app/routers/admin_router.py` | Add admin_display_name to user list | Lines 88-103 |
| `backend/migrations/add_admin_display_name.py` | New migration | — |
| `frontend/src/pages/games/hooks/useChat.ts` | Extend types | Lines 22-29, 44-56 |
| `frontend/src/pages/games/components/social/ChatPanel.tsx` | Admin channel icon/style | Line 51 |
| `frontend/src/pages/games/components/social/MessageBubble.tsx` | Admin badge rendering | Lines 109-110 |
| `frontend/src/pages/admin/AdminUsers.tsx` | Chat button per user | Lines 253-280 |
| `frontend/src/pages/Settings.tsx` | Admin display name field | Lines 604-607 area |
| `frontend/src/services/api.ts` | AdminUser type update | Lines 869-881 |

---

## Quality Checklist

- [x] All necessary context included (chat models, service, router, WS handler, frontend types)
- [x] Validation gates are executable
- [x] References existing patterns (DM creation, sender name resolution, display name router)
- [x] Clear implementation path (15 ordered tasks)
- [x] Error handling documented (permissions, rate limiting, fallbacks)
- [x] Anti-spoofing strategy documented (server flag, not text)
- [x] PostgreSQL migration syntax
- [x] Test plan with key scenarios
