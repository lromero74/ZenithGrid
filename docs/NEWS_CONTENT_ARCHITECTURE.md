# News Content Architecture Specification

> **Purpose:** This document defines the authoritative behavior for news articles, video
> content, sources, TTS generation, user subscriptions, and content retention across
> ZenithGrid. All development on news-related features must comply with these rules.

---

## 1. System-Level Content (Articles, Videos, Images)

All default news categories and sources are **system-wide**. A background system job
(not any individual user) is responsible for:

- Fetching articles and videos from all enabled system sources on a schedule
- Downloading and caching article thumbnail images
- Storing all fetched content in the database as system-owned records

Users do **not** trigger content fetches for system sources. They simply subscribe to
see what the system has already collected.

### 1.1 System Source Retention

System sources retain whichever is greater:

- The last **two weeks** of content per source, OR
- The most recent **5 articles and 5 videos** per source

This ensures every source always has meaningful content even if it publishes
infrequently. The cleanup job must evaluate both thresholds per source and keep the
larger set.

---

## 2. User Subscriptions to Sources

Users "subscribe" to sources to control what appears in their News feed. Subscription
governs **visibility only** -- it does not affect what the system fetches or stores.

- By default, users are subscribed to all system sources (opt-out model).
- Users can **unsubscribe** from any system source to hide its content from their feed.
- Users **cannot modify or delete** system sources -- only subscribe/unsubscribe.
- A user's News feed shows content from all their subscribed sources (system + their
  own custom sources), sorted **most recent first** regardless of source.

---

## 3. User-Added Custom Sources

Users may add their own additional content sources subject to these constraints:

### 3.1 Limits

- Maximum **10 custom sources per user**.
- Users **cannot** add a source whose URL or source key conflicts with an existing
  system source. The system must reject such attempts with a clear error.

### 3.2 Categorization

- Each custom source **must** be assigned a category from the existing system category
  list. Users **cannot** create their own categories.
- **Different users may categorize the same source differently.** The category
  assignment is per-user, not per-source. Each user sees their own categorization
  without any visible conflict.
- Implementation: The category for user-added sources lives on the user's subscription
  or a per-user-source join record, not on the source record itself, so that different
  users' categorizations don't collide.

### 3.3 Content Fetching for Custom Sources

A **system-level background job** fetches content for user-added sources (not the user
themselves). This means:

- The content refresh service discovers all enabled custom sources and fetches their
  content on the same schedule as system sources.
- Fetched articles and videos from custom sources are stored as regular database
  records but are **not system-owned** -- they are associated with the source, which
  has a `user_id`.

### 3.4 Visibility Rules for Custom Source Content

Content from a user-added custom source follows these visibility rules:

1. **Single user added the source:** Content is visible **only** to that user.
2. **Multiple users added the same source:** Content is visible to **all users** who
   have added that source. The system must not duplicate content -- if User A added
   source X and its articles already exist, User B adding source X should see the
   same articles without re-fetching.
3. **Content is not "owned" by the adding user.** The source record tracks who added
   it, but the fetched content (articles, videos, images) belongs to the system. If
   the original user deletes their custom source, the content should persist if
   another user still has the same source. Content is only cleaned up when **no user**
   references the source.

### 3.5 Source Management

- Users can **modify or delete only their own** custom sources.
- Users **cannot** modify or delete system sources.
- Deleting a custom source removes the user's reference to it. If other users also
  reference the same source, the source and its content remain.

### 3.6 Source Deduplication

When a user attempts to add a custom source, the system should check:

1. Does a system source with this URL/key already exist? -> **Reject** (tell user to
   subscribe to the system source instead).
2. Does another user's custom source with this URL already exist? -> **Link** the
   current user to the existing source rather than creating a duplicate. The user gets
   their own subscription record (with their own category assignment) pointing to the
   shared source.

---

## 4. User-Specific Retention Settings

### 4.1 How Retention Works

The system always retains content according to the **system default retention** policy
(Section 1.1). User retention settings are a **filter**, not a deletion trigger.

- Users may configure a retention preference for **any source they subscribe to** --
  both their own custom sources and system sources.
- This setting controls how far back they see content from that source in their feed.
- The actual database content is **never deleted** based on a user's retention setting.
- A user's retention setting **cannot exceed** the system default retention (2 weeks /
  5 items).

### 4.2 Why Retention Is Filter-Based

If User A sets retention to 3 days on source X, and User B later adds the same
source X with a 14-day retention, User B should still see the full two weeks of
content. User A's shorter preference must not cause older articles to be deleted
from the database. Each user simply filters content by their own retention window
at query time.

### 4.3 Retention Defaults

- If a user does not set a retention preference for any source (system or custom),
  the system default applies (2 weeks / 5 items, whichever yields more content).
- Users **can** set a retention override on system sources they subscribe to. This
  controls how far back they personally see content -- it does not affect the system's
  actual data retention or what other users see.

---

## 5. Text-to-Speech (TTS)

### 5.1 TTS Is User-Initiated

TTS generation is triggered by individual users, not by the system. When a user
requests TTS for an article, the system generates it on demand using their selected
voice.

### 5.2 Voice Subscriptions

Users should have the option in their **user-specific settings** to subscribe to
(select/enable) specific TTS voices. This allows the system to know which voices a
user prefers, which is relevant for:

- Default voice selection when playing an article
- Auto-selecting a pre-generated TTS if one exists in a voice the user subscribes to

### 5.3 TTS Caching and Sharing

Generated TTS audio is **shared across all users**:

- When a user generates TTS for an article with a specific voice, the resulting audio
  is stored and associated with that (article, voice) pair.
- If another user later requests TTS for the same article and the same voice, the
  cached version is served -- no regeneration needed.
- An article may have **multiple TTS recordings** (one per voice that any user has
  generated).
- TTS records are system-wide resources, not owned by any single user.

### 5.4 Voice Selection UI

When a user selects a voice for an article, the UI must:

- Show all available voices the user has subscribed to.
- Mark with an **asterisk (\*)** (or similar indicator) any voice for which a TTS has
  **already been generated** for that specific article.
- This helps users pick a voice with instant playback (no generation wait).

### 5.5 Replay Behavior

When a user replays an article they have previously listened to:

- The system uses the **voice they last used** for that article.
- This requires tracking per-user, per-article voice history (last-used voice).

### 5.6 TTS Data Model Requirements

To support the above, the system needs:

| Record | Scope | Purpose |
|--------|-------|---------|
| `ArticleTTS` | System-wide | Maps (article_id, voice_id) -> audio data/path |
| `UserVoiceSubscription` | Per-user | Which voices a user has enabled |
| `UserArticleTTSHistory` | Per-user | Last voice used per article per user |

---

## 6. Categories

- Categories are **system-defined only**. Users cannot create custom categories.
- The current category list (CryptoCurrency, AI, Finance, World, Nation, Business,
  Technology, Entertainment, Sports, Science, Health) is the authoritative set.
- System sources have a fixed category.
- User-added sources must be assigned a category from this list.
- Per-user categorization of user-added sources is stored separately so different
  users' choices don't conflict (see Section 3.2).

---

## 7. News Feed Behavior

A user's News feed aggregates content from:

1. All **system sources** the user is subscribed to.
2. All **custom sources** the user has added.

Sorting: **Most recent first** (by `published_at`), regardless of source or category.

Filtering: The frontend may offer category and source filters, but the default view
is a unified chronological feed.

Content from custom sources that a user has NOT added (and that are not system
sources) is **invisible** to that user.

---

## 8. Summary of Access Control Rules

| Action | System Sources | Own Custom Sources | Other Users' Custom Sources |
|--------|---------------|-------------------|---------------------------|
| View content | If subscribed | Always (respecting retention filter) | Only if user also added same source |
| Subscribe/Unsubscribe | Yes | N/A (always subscribed) | N/A |
| Add | No (system-managed) | Yes (max 10) | N/A |
| Edit | No | Yes | No |
| Delete | No | Yes (content persists if others reference it) | No |
| Set retention filter | Yes (up to system max) | Yes (up to system max) | N/A |
| Categorize | No (fixed) | Yes (per-user) | Own categorization only |

---

## 9. Implementation Notes

### 9.1 Source Deduplication Strategy

When checking for duplicate custom sources across users, match on the **canonical
feed URL** (normalized: lowercase, trailing slash stripped, query params sorted). This
prevents users from accidentally creating duplicates of the same feed with minor URL
variations.

### 9.2 Content Cleanup Job

The cleanup job must:

1. Evaluate system retention per source (2 weeks or 5 items, whichever keeps more).
2. Never delete content based on any individual user's retention preference.
3. When a custom source has zero remaining user references, mark it for cleanup. Its
   content can be deleted after a grace period (e.g., 7 days) in case a user re-adds
   the source.
4. TTS audio should follow article retention -- when an article is deleted, its
   associated TTS records can be cleaned up too.

### 9.3 Database Changes Needed

Compared to the current schema, the following additions/changes are required:

- **`ArticleTTS`** table: `article_id`, `voice_id`, `audio_data`/`audio_path`,
  `created_at`, `created_by_user_id` (for attribution, not ownership).
- **`UserVoiceSubscription`** table: `user_id`, `voice_id`, `is_enabled`, `created_at`.
- **`UserArticleTTSHistory`** table: `user_id`, `article_id`, `last_voice_id`,
  `last_played_at`.
- **`UserSourceSubscription`** additions: `user_category` (nullable, for per-user
  categorization of custom sources), `retention_days` (nullable, user's retention
  filter preference).
- **`ContentSource`** changes: ensure `user_id` supports multi-user references
  (possibly a join table `UserCustomSource` instead of a single `user_id` FK, to
  support multiple users referencing the same source).

### 9.4 Key Invariants

1. System content fetching is never triggered by individual users.
2. No user action can delete content that another user still has access to.
3. TTS audio is always shared -- never duplicated per user.
4. User retention settings are query-time filters, never deletion triggers.
5. Category assignments for custom sources are per-user, not global.
6. The News feed is always sorted most-recent-first across all subscribed sources.

---

## 10. Source Content Blacklisting

To prevent users from adding custom sources that host illegal, racist, explicit,
NSFW, violent, or otherwise harmful content, the system maintains an in-memory
domain blacklist built from two open-source list providers.

### 10.1 Blacklist Sources

| Provider | License | Categories |
|----------|---------|------------|
| **UT1 Blacklists** (Univ. Toulouse) | CC BY-SA | malware, phishing, cryptojacking, stalkerware, dangerous_material, agressif, sect, hacking, drogue, warez, mixed_adult, adult |
| **Block List Project** | Unlicense | abuse, porn, drugs, fraud, malware, phishing, ransomware, piracy, scam |

Combined these provide ~1.5-2M unique domains after deduplication.

### 10.2 Refresh Schedule

- **On startup:** Load from disk cache (instant). If cache is missing or older than
  7 days, trigger a background download immediately.
- **Weekly:** Re-download all category lists, deduplicate, atomic-swap the in-memory
  set, and persist to disk.
- Background refresh runs as an asyncio task inside `DomainBlacklistService`, started
  and stopped alongside other app services in `main.py`.

### 10.3 Domain Matching Strategy

When a user attempts to add a custom source, the system:

1. Extracts the domain from the URL (`urlparse` → netloc, strip port, lowercase).
2. Generates domain variants by walking parent domains:
   `sub.evil.com` → `[sub.evil.com, evil.com]`.
3. Stops before bare TLDs (`com`) or two-part country-code TLDs (`co.uk`).
4. Checks each variant against the in-memory `set` — O(1) per lookup.
5. If any variant matches → **403 Forbidden** with a clear message.

### 10.4 First-Startup Graceful Degradation

If no disk cache exists (fresh install), the in-memory set starts empty. All domains
are allowed until the first download completes (~30-60 seconds). A warning is logged.
This avoids blocking app startup on network I/O.

### 10.5 Disk Cache

Cached files are stored in `backend/blacklists/` (git-ignored):

```
backend/blacklists/
  metadata.json       # last_download timestamp, domain_count, category_counts
  ut1_malware.txt     # one domain per line
  ut1_adult.txt
  blp_porn.txt
  ...
```

### 10.6 Memory and Disk Footprint

- **Memory:** ~150-200 MB for ~1.5-2M domains in a Python `set`.
- **Disk:** ~30-50 MB of plain-text domain files.
- Acceptable on t2.micro (1 GB RAM) given no other large in-memory structures.

---

*Last updated: 2026-02-17*
