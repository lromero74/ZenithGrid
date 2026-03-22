# PRP: Donation Support System

**Feature**: Monthly donation goal meter, confirmed donation tracking, and user-facing donation popup
**Created**: 2026-03-14
**One-Pass Confidence Score**: 8/10

> Straightforward CRUD + modal feature. Follows established patterns for models, routers, admin tabs, and modals. The only nuance is the monthly meter reset logic and the self-report → admin confirm workflow.

---

## Context & Goal

### Problem
The project is free and subscription-free, but hosting, API keys, and development cost money. The README has donation addresses (BTC, PayPal, USDC) but there's no in-app visibility. Users who get value may not know they can contribute.

### Solution
1. **Donation modal** — polite popup for logged-in users showing donation addresses and the monthly progress meter
2. **Monthly meter** — visual progress bar showing how much has been donated toward the monthly goal, resets each month
3. **Donation tracking** — database table recording confirmed donations (amount, donor, method, date, notes)
4. **Self-report flow** — users can report donations; admin confirms them (only confirmed donations count toward the meter)
5. **Admin tab** — manage donations (confirm/reject self-reports, manually add, set monthly goal)

### Who Benefits
- **Users**: See that their contributions matter and the project needs support
- **Admin**: Track donations, set goals, manage the meter

### Scope
- **In**: Donation model, migration, router, admin tab, user-facing modal with meter, self-report endpoint, Settings-based goal config
- **Out**: Payment gateway integration, automatic BTC/USDC detection, email receipts, recurring donation pledges

---

## Architecture

### Data Flow

```
User sees modal → clicks "I donated" → self-report form (amount, method, tx ref)
                                         ↓
                              POST /api/donations/report
                                         ↓
                              Donation row (status=pending)
                                         ↓
                      Admin → Donations tab → Confirm/Reject
                                         ↓
                              Donation row (status=confirmed)
                                         ↓
                      GET /api/donations/goal → { target, current, percentage, month }
                                         ↓
                              Modal meter updates for all users
```

### Database Model

**New file**: `backend/app/models/donations.py`

```python
class Donation(Base):
    __tablename__ = "donations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # null = admin-added
    amount = Column(Float, nullable=False)  # USD equivalent
    currency = Column(String(10), nullable=False)  # "USD", "BTC", "USDC"
    payment_method = Column(String(50), nullable=False)  # "btc", "usdc", "paypal", "venmo", "cashapp"
    tx_reference = Column(String(255), nullable=True)  # Transaction ID/PayPal ref
    donor_name = Column(String(100), nullable=True)  # Display name (optional for privacy)
    notes = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="pending")  # pending, confirmed, rejected
    confirmed_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # Admin who confirmed
    donation_date = Column(DateTime, nullable=False)  # When donation was made
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
```

### Settings Keys (existing Settings table)

Use the existing `Settings` model for goal configuration:
- `donation_goal_monthly` — target amount in USD (e.g., "100")
- Managed via existing `PUT /api/settings/{key}` endpoint or new admin UI

### API Endpoints

**New router**: `backend/app/routers/donations_router.py` with prefix `/api/donations`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/donations/goal` | Authenticated | Monthly goal progress (target, current, %, month) |
| `POST` | `/api/donations/report` | Authenticated | User self-reports a donation |
| `GET` | `/api/donations` | Admin | List all donations (filterable by status, month) |
| `PUT` | `/api/donations/{id}/confirm` | Admin | Confirm a pending donation |
| `PUT` | `/api/donations/{id}/reject` | Admin | Reject a pending donation |
| `POST` | `/api/donations` | Admin | Manually add a confirmed donation |
| `PUT` | `/api/donations/goal` | Admin | Update the monthly goal target |

The `GET /goal` endpoint calculates current month total from confirmed donations:
```sql
SELECT COALESCE(SUM(amount), 0)
FROM donations
WHERE status = 'confirmed'
  AND EXTRACT(MONTH FROM donation_date) = current_month
  AND EXTRACT(YEAR FROM donation_date) = current_year
```

For PostgreSQL use `EXTRACT()`. The ORM handles this via `func.extract`.

---

## Existing Code Patterns (Reference)

### 1. Model Registration (`backend/app/models/__init__.py`)

Add import and `__all__` entry:
```python
from app.models.donations import Donation

# In __all__:
"Donation",
```

### 2. Migration Pattern (`backend/migrations/add_session_limits.py`)

New migrations use async `run_migration(db)` with `text()`:
```python
MIGRATION_NAME = "add_donations_table"

async def run_migration(db):
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS donations (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            amount DOUBLE PRECISION NOT NULL,
            ...
        )
    """))
```

**IMPORTANT**: Use `SERIAL PRIMARY KEY` for PostgreSQL (not `INTEGER PRIMARY KEY AUTOINCREMENT` which is SQLite). Since production is PostgreSQL, write the migration for PostgreSQL. Use `DOUBLE PRECISION` for floats, `TIMESTAMP` for datetimes.

### 3. Router Pattern (`backend/app/routers/admin_router.py`)

```python
router = APIRouter(prefix="/api/donations", tags=["donations"])

# Admin endpoints use:
current_user: User = Depends(require_permission(Perm.ADMIN_USERS))

# Regular user endpoints use:
current_user: User = Depends(require_permission(Perm.SOCIAL_CHAT))
```

Register in `main.py` (around line 178):
```python
from app.routers import donations_router
app.include_router(donations_router.router)
```

### 4. Admin Page Tab Pattern (`frontend/src/pages/Admin.tsx`)

Add a new tab:
```typescript
type AdminTab = 'users' | 'groups' | 'roles' | 'donations'

const TABS = [
  // ... existing tabs
  { id: 'donations', label: 'Donations', icon: Heart },
]

// Render:
{activeTab === 'donations' && <AdminDonations />}
```

Import: `import { AdminDonations } from './admin/AdminDonations'`

### 5. Modal Pattern (`frontend/src/components/AboutModal.tsx`)

```typescript
interface DonationModalProps {
  isOpen: boolean
  onClose: () => void
}

export function DonationModal({ isOpen, onClose }: DonationModalProps) {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-2 sm:p-4">
      <div className="bg-slate-800 rounded-lg w-full max-w-lg max-h-[95vh] flex flex-col">
        {/* Header, Content, Footer */}
      </div>
    </div>
  )
}
```

### 6. API Service Pattern (`frontend/src/services/api.ts`)

```typescript
export interface DonationGoal {
  target: number
  current: number
  percentage: number
  month: string  // "2026-03"
  donation_count: number
}

export const donationsApi = {
  getGoal: () =>
    api.get<DonationGoal>('/donations/goal').then(r => r.data),
  reportDonation: (data: {
    amount: number; currency: string;
    payment_method: 'btc' | 'usdc' | 'paypal' | 'venmo' | 'cashapp';
    tx_reference?: string
  }) => api.post('/donations/report', data).then(r => r.data),
  // Admin methods...
}
```

### 7. Show-Once Modal Pattern (`frontend/src/components/MFAEncouragement.tsx`)

Use localStorage to limit popup frequency:
```typescript
const DONATION_DISMISSED_KEY = 'donation_modal_dismissed'
const DONATION_DISMISSED_MONTH_KEY = 'donation_modal_dismissed_month'

// Show if: not dismissed this month
const currentMonth = new Date().toISOString().slice(0, 7)  // "2026-03"
const dismissedMonth = localStorage.getItem(DONATION_DISMISSED_MONTH_KEY)
const showModal = dismissedMonth !== currentMonth
```

---

## Frontend Components

### 1. DonationModal.tsx

**Location**: `frontend/src/components/DonationModal.tsx`

**Sections**:
1. **Header**: "Support the Project" with heart icon
2. **Monthly meter**: Progress bar with `${current}/${target} USD` label, percentage
3. **Message**: Polite copy about keeping the project free and servers running
4. **Donation addresses**: BTC address (with copy button), PayPal link, USDC address (with copy button)
5. **Self-report button**: "I already donated" → expands form (amount, method, optional tx ref)
6. **Footer**: "Maybe later" dismiss button, "Don't show again this month" checkbox

**Trigger**: Rendered in the main layout (e.g., App.tsx or Dashboard). Shows automatically once per month for logged-in users, after a brief delay (5 seconds after page load). Can also be triggered manually from Settings or footer.

### 2. AdminDonations.tsx

**Location**: `frontend/src/pages/admin/AdminDonations.tsx`

**Sections**:
1. **Goal setting**: Current monthly goal with edit button
2. **Stats bar**: This month's total, donation count, percentage to goal
3. **Pending donations**: Table of self-reported donations awaiting confirmation (Confirm/Reject buttons)
4. **All donations**: Table with month filter, showing confirmed/rejected/pending with donor, amount, method, date
5. **Add donation button**: Manual entry form for admin-recorded donations

---

## Implementation Tasks (in order)

### Backend

1. **Create `backend/app/models/donations.py`** — Donation model
2. **Update `backend/app/models/__init__.py`** — register Donation
3. **Create `backend/migrations/add_donations_table.py`** — PostgreSQL migration
4. **Create `backend/app/routers/donations_router.py`** — all endpoints
5. **Register router in `backend/app/main.py`**
6. **Seed default setting** — `donation_goal_monthly = 100` in migration

### Frontend

7. **Install `qrcode.react`** — `cd frontend && npm install qrcode.react`
8. **Add types and API methods to `frontend/src/services/api.ts`**
8. **Create `frontend/src/components/DonationModal.tsx`** — modal with meter, addresses, self-report
9. **Create `frontend/src/pages/admin/AdminDonations.tsx`** — admin management tab
10. **Update `frontend/src/pages/Admin.tsx`** — add Donations tab
11. **Integrate modal trigger** — add to App.tsx or layout, with localStorage show-once logic

### Tests

12. **Create `backend/tests/routers/test_donations_router.py`** — endpoint tests
13. **Run migration on EC2** — `backend/venv/bin/python3 update.py --yes`

### Validation

14. **Lint**: `flake8 --max-line-length=120` on all Python files
15. **TypeScript**: `npx tsc --noEmit` clean
16. **Tests pass**: `pytest tests/routers/test_donations_router.py -v`

---

## Test Plan

### Backend Tests (`tests/routers/test_donations_router.py`)

**Happy path:**
- `test_get_goal_returns_current_month_progress` — creates confirmed donations, checks totals
- `test_report_donation_creates_pending` — user self-reports, status is "pending"
- `test_admin_confirm_donation_updates_status` — admin confirms, status changes to "confirmed"
- `test_admin_add_donation_directly` — admin creates confirmed donation
- `test_goal_only_counts_confirmed` — pending/rejected donations excluded from meter

**Edge cases:**
- `test_goal_resets_each_month` — donations from prior month not counted
- `test_report_requires_auth` — unauthenticated request rejected
- `test_confirm_requires_admin` — non-admin can't confirm

**Failure cases:**
- `test_report_invalid_amount` — zero or negative amount rejected
- `test_confirm_nonexistent_donation` — 404 for bad ID
- `test_reject_already_confirmed` — can't reject a confirmed donation

---

## Donation Methods & Addresses

These are hardcoded in the frontend modal (not in the database):

### Crypto (with QR codes)
- **Bitcoin (BTC):** `3LehBoma3aeDwdgMYK3hyr2TGfxkJs55MV`
- **USDC (ERC-20):** `0x8B7Ff39C772c90AB58A3d74dCd17F1425b4001c0`

Crypto addresses should render QR codes using the `qrcode.react` package. Install it:
```bash
cd /home/ec2-user/ZenithGrid/frontend && npm install qrcode.react
```

Usage:
```tsx
import { QRCodeSVG } from 'qrcode.react'

<QRCodeSVG value="bitcoin:3LehBoma3aeDwdgMYK3hyr2TGfxkJs55MV" size={120}
  bgColor="transparent" fgColor="#94a3b8" level="M" />
```

For BTC use `bitcoin:` URI prefix. For USDC use the raw address (no standard URI).
Show QR codes inline next to the address, with a toggle or expandable section so the modal doesn't get too tall.

### Payment Apps
- **PayPal:** `@farolito74` — link to `https://paypal.me/farolito74`
- **Venmo:** `@Louis-Romero-5` — link to `https://venmo.com/Louis-Romero-5`
- **CashApp:** `$Farolito74` — link to `https://cash.app/$Farolito74`

### Modal Layout
Group methods into two sections:
1. **Crypto** — BTC and USDC with copy buttons + QR codes (collapsible)
2. **Payment Apps** — PayPal, Venmo, CashApp as clickable links that open in new tab

---

## UX Copy (suggested)

**Modal header**: "Help Keep This Free"

**Body text**:
> This platform is free to use — no subscriptions, no ads, no hidden fees.
> But servers, APIs, and development take time and money.
>
> If you're getting value from this tool, consider making a donation of any amount.
> Every contribution helps keep the lights on and new features coming.

**Meter label**: "$X of $Y goal this month" with percentage bar

**Dismiss options**:
- "Maybe Later" — closes for this session
- "Don't remind me this month" — sets localStorage, hides for rest of month

---

## Validation Gates

```bash
# Python lint
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m flake8 --max-line-length=120 \
  app/models/donations.py \
  app/routers/donations_router.py

# TypeScript
cd /home/ec2-user/ZenithGrid/frontend && npx tsc --noEmit

# Tests
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m pytest tests/routers/test_donations_router.py -v

# Migration (on EC2)
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 update.py --yes
```

---

## PostgreSQL Migration Notes

The migration MUST use PostgreSQL syntax since production runs PostgreSQL:

```sql
CREATE TABLE IF NOT EXISTS donations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    amount DOUBLE PRECISION NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'USD',
    payment_method VARCHAR(50) NOT NULL,
    tx_reference VARCHAR(255),
    donor_name VARCHAR(100),
    notes TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    confirmed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    donation_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_donations_user_id ON donations(user_id);
CREATE INDEX IF NOT EXISTS ix_donations_status ON donations(status);
CREATE INDEX IF NOT EXISTS ix_donations_donation_date ON donations(donation_date);
```

Also seed the monthly goal setting:
```sql
INSERT INTO settings (key, value, value_type, description)
VALUES ('donation_goal_monthly', '100', 'float', 'Monthly donation goal in USD')
ON CONFLICT (key) DO NOTHING;
```

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Users might spam self-reports | Rate limit: max 5 reports per day per user |
| Goal amount visible = potential embarrassment if low | Start modest ($100), celebrate hitting it rather than shaming shortfall |
| Copy button needs clipboard API | Use `navigator.clipboard.writeText()` with fallback toast on failure |
| Monthly reset timing | Use UTC month boundaries consistently (server + client) |

---

## Quality Checklist

- [x] All necessary context included
- [x] Validation gates are executable
- [x] References existing patterns (models, routers, modals, admin tabs, migrations)
- [x] Clear implementation path (14 ordered tasks)
- [x] Error handling documented (rate limiting, auth checks, edge cases)
- [x] PostgreSQL-specific migration syntax
- [x] Test plan with happy/edge/failure cases
