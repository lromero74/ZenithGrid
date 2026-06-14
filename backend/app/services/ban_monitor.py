"""
Ban monitor — queries banned IPs and caches the results.

Two sources are supported, selected via BAN_SOURCE env var:
  * "fail2ban" (default): shells out to fail2ban-client. When running inside a
    distrobox (e.g., zenith-box on fedora.local) the call is routed through
    distrobox-host-exec so it reaches the host's fail2ban socket.
  * "cloudflare": lists account-level Firewall Access Rules. This is the right
    answer post-2026-04-29 when fail2ban writes its bans to Cloudflare via a
    custom action — CF is the source of truth.
  * "both": union of fail2ban-local + Cloudflare rules, deduped by IP.

Runs as a background task so the admin endpoint doesn't shell out on every request.
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ip-api.com batch endpoint — free tier, no key required, 100 IPs per request.
# Returns full country names directly so no pycountry resolution needed.
_GEO_BATCH_URL = "http://ip-api.com/batch"
_GEO_FIELDS = "status,country,countryCode,regionName,city,isp,query"
_GEO_BATCH_SIZE = 100

# ── Source selection ──────────────────────────────────────────────────────
# BAN_SOURCE selects which backing system to query. Default keeps the
# pre-2026-04-29 behavior so existing deployments work without re-config.
_BAN_SOURCE = os.environ.get("BAN_SOURCE", "fail2ban").lower()

# ── Distrobox bridge ──────────────────────────────────────────────────────
# fail2ban runs on the host (fedora.local), but ZenithGrid runs inside the
# zenith-box distrobox. distrobox-host-exec routes the call back to the host;
# outside a distrobox the prefix is empty and subprocess works as usual.
_F2B_CMD_PREFIX: list[str] = (
    ["distrobox-host-exec"]
    if (os.environ.get("CONTAINER_ID") and shutil.which("distrobox-host-exec"))
    else []
)

# ── Cloudflare API config (only used when BAN_SOURCE includes "cloudflare") ─
_CF_API_TOKEN = os.environ.get("CF_API_TOKEN", "")
_CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "")
_CF_API_BASE = "https://api.cloudflare.com/client/v4"


@dataclass
class BannedIP:
    ip: str
    jail: str
    city: str | None = None
    region: str | None = None
    country: str | None = None       # 2-letter ISO code
    country_name: str | None = None  # Full country name (e.g. "United States")
    org: str | None = None
    hostname: str | None = None


@dataclass
class BanSnapshot:
    """Cached snapshot of fail2ban state."""
    banned_ips: list[BannedIP] = field(default_factory=list)
    total_banned: int = 0
    currently_banned: int = 0
    total_failed: int = 0
    last_updated: float = 0.0


_snapshot = BanSnapshot()

# Geo cache: persists across refreshes so each IP is looked up only once.
# Avoids hammering the rate limit when hundreds of IPs are banned.
_geo_cache: dict[str, dict] = {}


def get_ban_snapshot() -> BanSnapshot:
    """Return the current cached ban snapshot."""
    return _snapshot


async def refresh_ban_snapshot() -> BanSnapshot:
    """Force an immediate refresh of the ban snapshot (admin-triggered)."""
    global _snapshot
    loop = asyncio.get_running_loop()
    _snapshot = await loop.run_in_executor(None, _query_bans)
    return _snapshot


def _query_bans() -> BanSnapshot:
    """Dispatch to the configured ban source. Single entry point used by all
    callers so the BAN_SOURCE switch only has to live in one place."""
    if _BAN_SOURCE == "cloudflare":
        return _query_cloudflare()
    if _BAN_SOURCE == "both":
        return _merge_snapshots(_query_fail2ban(), _query_cloudflare())
    return _query_fail2ban()


def _merge_snapshots(a: BanSnapshot, b: BanSnapshot) -> BanSnapshot:
    """Union two snapshots, deduped by (ip, jail). Counts are summed."""
    merged = BanSnapshot(last_updated=time.time())
    seen: set[tuple[str, str]] = set()
    for snap in (a, b):
        merged.currently_banned += snap.currently_banned
        merged.total_banned += snap.total_banned
        merged.total_failed += snap.total_failed
        for entry in snap.banned_ips:
            key = (entry.ip, entry.jail)
            if key in seen:
                continue
            seen.add(key)
            merged.banned_ips.append(entry)
    return merged


def _lookup_ip_geo_batch(ips: list[str]) -> dict[str, dict]:
    """Look up geolocation for a list of IPs via ip-api.com batch endpoint.

    - Already-cached IPs are served from _geo_cache without any network call.
    - Uncached IPs are fetched in batches of up to 100 per request.
    - Failed lookups return {} and are NOT stored in the cache.
    - Returns a mapping of {ip: geo_dict} for all IPs in the input list.
    """
    unique_ips = list(dict.fromkeys(ips))  # Deduplicate, preserve order
    result: dict[str, dict] = {}

    uncached = []
    for ip in unique_ips:
        if ip in _geo_cache:
            result[ip] = _geo_cache[ip]
        else:
            uncached.append(ip)

    if not uncached:
        return result

    for i in range(0, len(uncached), _GEO_BATCH_SIZE):
        batch = uncached[i:i + _GEO_BATCH_SIZE]
        try:
            body = json.dumps(batch).encode()
            req = urllib.request.Request(
                f"{_GEO_BATCH_URL}?fields={_GEO_FIELDS}",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "ZenithGrid-BanMonitor",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                entries = json.loads(resp.read())

            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                ip = entry.get("query")
                if not ip:
                    continue
                if entry.get("status") != "success":
                    result[ip] = {}
                    continue
                geo = {
                    "city": entry.get("city"),
                    "region": entry.get("regionName"),
                    "country": entry.get("countryCode"),
                    "country_name": entry.get("country"),
                    "org": entry.get("isp"),
                    "hostname": None,
                }
                _geo_cache[ip] = geo
                result[ip] = geo

        except Exception as e:
            logger.debug(f"Geo batch lookup failed (batch starting {batch[0]}): {e}")
            for ip in batch:
                result.setdefault(ip, {})

    return result


def _query_fail2ban() -> BanSnapshot:
    """Query fail2ban-client for current ban status. Runs synchronously (subprocess)."""
    snapshot = BanSnapshot(last_updated=time.time())

    try:
        # Get jail list
        result = subprocess.run(
            [*_F2B_CMD_PREFIX, "sudo", "fail2ban-client", "status"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            logger.warning(f"fail2ban-client status failed: {result.stderr}")
            return snapshot

        # Parse jail names
        jails = []
        for line in result.stdout.splitlines():
            if "Jail list:" in line:
                jails = [j.strip() for j in line.split(":", 1)[1].split(",") if j.strip()]

        # Pass 1: query each jail, collect (ip, jail) pairs and counts
        raw_bans: list[tuple[str, str]] = []  # (ip, jail)
        for jail in jails:
            jail_result = subprocess.run(
                [*_F2B_CMD_PREFIX, "sudo", "fail2ban-client", "status", jail],
                capture_output=True, text=True, timeout=10,
            )
            if jail_result.returncode != 0:
                continue

            for line in jail_result.stdout.splitlines():
                line = line.strip()
                if "Currently banned:" in line:
                    try:
                        snapshot.currently_banned += int(line.split(":")[-1].strip())
                    except ValueError:
                        pass
                elif "Total banned:" in line:
                    try:
                        snapshot.total_banned += int(line.split(":")[-1].strip())
                    except ValueError:
                        pass
                elif "Total failed:" in line:
                    try:
                        snapshot.total_failed += int(line.split(":")[-1].strip())
                    except ValueError:
                        pass
                elif "Banned IP list:" in line:
                    for ip in line.split(":", 1)[1].strip().split():
                        if ip.strip():
                            raw_bans.append((ip.strip(), jail))

        # Pass 2: batch geo lookup for all unique IPs (cache-aware)
        all_ips = [ip for ip, _ in raw_bans]
        geo_map = _lookup_ip_geo_batch(all_ips)

        for ip, jail in raw_bans:
            geo = geo_map.get(ip, {})
            snapshot.banned_ips.append(BannedIP(
                ip=ip, jail=jail,
                city=geo.get("city"),
                region=geo.get("region"),
                country=geo.get("country"),
                country_name=geo.get("country_name"),
                org=geo.get("org"),
                hostname=geo.get("hostname"),
            ))

    except subprocess.TimeoutExpired:
        logger.warning("fail2ban-client timed out")
    except FileNotFoundError:
        logger.info("fail2ban-client not found — ban monitor disabled")
    except Exception as e:
        logger.error(f"Ban monitor error: {e}")

    return snapshot


def _query_cloudflare() -> BanSnapshot:
    """Query Cloudflare account-level Firewall Access Rules and shape the
    response into a BanSnapshot. Each rule's `notes` field is parsed for the
    fail2ban jail name (the fail2ban-cf-ban wrapper writes "fail2ban:<jail>
    <ts>"). If the notes don't match, the jail is recorded as "cloudflare".

    Requires CF_API_TOKEN with `Account → Firewall Access Rules : Read` and
    CF_ACCOUNT_ID. Returns an empty snapshot on any error so the admin page
    just shows nothing rather than crashing.
    """
    snapshot = BanSnapshot(last_updated=time.time())

    if not _CF_API_TOKEN or not _CF_ACCOUNT_ID:
        logger.warning("CF_API_TOKEN/CF_ACCOUNT_ID not set — cloudflare ban source disabled")
        return snapshot

    raw_bans: list[tuple[str, str]] = []  # (ip, jail)
    page = 1
    per_page = 100  # CF max is 1000; 100 is a reasonable batch
    try:
        while True:
            url = (
                f"{_CF_API_BASE}/accounts/{_CF_ACCOUNT_ID}/firewall/access_rules/rules"
                f"?per_page={per_page}&page={page}"
            )
            req = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {_CF_API_TOKEN}",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read())

            if not payload.get("success"):
                logger.warning(f"CF list-rules failed: {payload.get('errors')}")
                break

            rules = payload.get("result", []) or []
            for rule in rules:
                cfg = rule.get("configuration") or {}
                if cfg.get("target") not in ("ip", "ip6"):
                    continue  # ignore CIDR / asn / country rules
                ip = cfg.get("value")
                if not ip:
                    continue
                # Notes pattern from fail2ban-cf-ban: "fail2ban:<jail> <ts>".
                notes = rule.get("notes") or ""
                jail = "cloudflare"
                if notes.startswith("fail2ban:"):
                    rest = notes[len("fail2ban:"):].strip()
                    jail = rest.split()[0] if rest else "fail2ban"
                raw_bans.append((ip, jail))

            # Paginate if there's another page.
            info = payload.get("result_info") or {}
            if page >= int(info.get("total_pages") or 1):
                break
            page += 1

        snapshot.currently_banned = len(raw_bans)
        snapshot.total_banned = len(raw_bans)

        # Geo-enrich (same path as fail2ban — single batch lookup, cache-aware)
        all_ips = [ip for ip, _ in raw_bans]
        geo_map = _lookup_ip_geo_batch(all_ips)
        for ip, jail in raw_bans:
            geo = geo_map.get(ip, {})
            snapshot.banned_ips.append(BannedIP(
                ip=ip, jail=jail,
                city=geo.get("city"),
                region=geo.get("region"),
                country=geo.get("country"),
                country_name=geo.get("country_name"),
                org=geo.get("org"),
                hostname=geo.get("hostname"),
            ))

    except urllib.error.HTTPError as e:
        logger.warning(f"CF list-rules HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        logger.warning(f"CF list-rules network error: {e.reason}")
    except Exception as e:
        logger.error(f"CF ban monitor error: {e}")

    return snapshot


async def run_ban_monitor_once(session_maker=None):
    """Query the configured ban source and cache the result. Called by
    APScheduler every 24 hours."""
    global _snapshot
    try:
        loop = asyncio.get_running_loop()
        _snapshot = await loop.run_in_executor(None, _query_bans)
        logger.info(
            f"Ban monitor (source={_BAN_SOURCE}): "
            f"{_snapshot.currently_banned} currently banned, "
            f"{_snapshot.total_banned} total banned"
        )
    except Exception as e:
        logger.error(f"Ban monitor error: {e}")
