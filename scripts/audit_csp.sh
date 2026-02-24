#!/usr/bin/env bash
# CSP Audit — detect mismatches between frontend external URLs and nginx CSP
# Usage: ./scripts/audit_csp.sh
# Exit code: 0 = all good, 1 = mismatches found

set -euo pipefail

FRONTEND_DIR="frontend/src"
NGINX_CONF="/etc/nginx/conf.d/tradebot.conf"

# Known external dependencies — update when adding new external services
# (Catches dynamically-constructed URLs that grep can't find)
REQUIRED_SCRIPT_DOMAINS="s3.tradingview.com"
REQUIRED_FRAME_DOMAINS="s3.tradingview.com s.tradingview.com www.youtube.com"
REQUIRED_STYLE_DOMAINS=""
REQUIRED_FONT_DOMAINS=""
REQUIRED_CONNECT_DOMAINS=""

FAILURES=0

echo "CSP Audit"
echo "========="
echo "Scanning $FRONTEND_DIR for external URLs..."
echo ""

# --- Step 1: Extract external domains from frontend code (skip test files) ---

# Scripts: createElement('script') + .src = 'https://...' or <script src="https://...">
SCRIPT_DOMAINS=$(grep -rn 'script\.src\s*=\s*["\x27]https\?://\|<script.*src=.*https\?://' "$FRONTEND_DIR" \
    --include='*.tsx' --include='*.ts' --include='*.html' \
    | grep -v '\.test\.' | grep -v '__tests__' \
    | grep -oP 'https?://[a-zA-Z0-9.-]+' | sort -u | sed 's|https\?://||' || true)

# Frames/iframes: <iframe src="https://..."> or src={`https://...`}
FRAME_DOMAINS=$(grep -rn '<iframe\|iframe.*src\|\.src.*youtube\|\.src.*tradingview' "$FRONTEND_DIR" \
    --include='*.tsx' --include='*.ts' --include='*.html' \
    | grep -v '\.test\.' | grep -v '__tests__' \
    | grep -oP 'https?://[a-zA-Z0-9.-]+' | sort -u | sed 's|https\?://||' || true)

# Stylesheets: <link href="https://..."> with rel="stylesheet"
STYLE_DOMAINS=$(grep -rn '<link.*href=.*https\?://.*stylesheet\|stylesheet.*href=.*https\?://' "$FRONTEND_DIR" \
    --include='*.tsx' --include='*.ts' --include='*.html' \
    | grep -v '\.test\.' | grep -v '__tests__' \
    | grep -oP 'https?://[a-zA-Z0-9.-]+' | sort -u | sed 's|https\?://||' || true)

# Fonts: url("https://fonts...")
FONT_DOMAINS=$(grep -rn 'url(.*https\?://fonts\.' "$FRONTEND_DIR" \
    --include='*.tsx' --include='*.ts' --include='*.css' \
    | grep -v '\.test\.' | grep -v '__tests__' \
    | grep -oP 'https?://[a-zA-Z0-9.-]+' | sort -u | sed 's|https\?://||' || true)

# Merge with known required domains
merge_domains() { echo "$1 $2" | tr ' ' '\n' | grep -v '^$' | sort -u | tr '\n' ' ' || true; }
SCRIPT_DOMAINS=$(merge_domains "$SCRIPT_DOMAINS" "$REQUIRED_SCRIPT_DOMAINS")
FRAME_DOMAINS=$(merge_domains "$FRAME_DOMAINS" "$REQUIRED_FRAME_DOMAINS")
STYLE_DOMAINS=$(merge_domains "$STYLE_DOMAINS" "$REQUIRED_STYLE_DOMAINS")
FONT_DOMAINS=$(merge_domains "$FONT_DOMAINS" "$REQUIRED_FONT_DOMAINS")
CONNECT_DOMAINS=$(merge_domains "" "$REQUIRED_CONNECT_DOMAINS")

print_found() {
    local label=$1; shift
    local domains="$*"
    if [ -n "$(echo "$domains" | tr -d ' ')" ]; then
        echo "External ${label} domains:"
        for d in $domains; do echo "  $d"; done
        echo ""
    fi
}
print_found "script" $SCRIPT_DOMAINS
print_found "frame" $FRAME_DOMAINS
print_found "style" $STYLE_DOMAINS
print_found "font" $FONT_DOMAINS
print_found "connect" $CONNECT_DOMAINS

# --- Step 2: Read CSP from nginx ---

if [ ! -f "$NGINX_CONF" ]; then
    echo "WARNING: $NGINX_CONF not found — skipping CSP check (run on EC2)"
    exit 0
fi

echo "Checking against nginx CSP ($NGINX_CONF)..."
echo ""

CSP_LINE=$(grep -oP "Content-Security-Policy\s+\"[^\"]+\"" "$NGINX_CONF" || true)
if [ -z "$CSP_LINE" ]; then
    echo "ERROR: No Content-Security-Policy header found in $NGINX_CONF"
    exit 1
fi

extract_directive() {
    echo "$CSP_LINE" | grep -oP "${1}\s+[^;]+" | sed "s/${1}\s*//" || true
}

CSP_SCRIPT=$(extract_directive "script-src")
CSP_FRAME=$(extract_directive "frame-src")
CSP_STYLE=$(extract_directive "style-src")
CSP_FONT=$(extract_directive "font-src")
CSP_CONNECT=$(extract_directive "connect-src")

# --- Step 3: Cross-reference ---

check_domain() {
    local directive_name=$1
    local domain=$2
    local csp_value=$3

    if echo "$csp_value" | grep -qF "$domain"; then
        echo "  OK  ${directive_name}: ${domain}"
    else
        echo "  FAIL  ${directive_name}: ${domain} — BLOCKED (not in ${directive_name} directive)"
        echo "        Fix: Add https://${domain} to ${directive_name} in ${NGINX_CONF}"
        FAILURES=$((FAILURES + 1))
    fi
}

for d in $SCRIPT_DOMAINS; do check_domain "script-src" "$d" "$CSP_SCRIPT"; done
for d in $FRAME_DOMAINS; do check_domain "frame-src" "$d" "$CSP_FRAME"; done
for d in $STYLE_DOMAINS; do check_domain "style-src" "$d" "$CSP_STYLE"; done
for d in $FONT_DOMAINS; do check_domain "font-src" "$d" "$CSP_FONT"; done
for d in $CONNECT_DOMAINS; do check_domain "connect-src" "$d" "$CSP_CONNECT"; done

echo ""
if [ "$FAILURES" -gt 0 ]; then
    echo "CSP AUDIT FAILED — ${FAILURES} mismatch(es) found"
    exit 1
else
    echo "All external domains are covered by CSP. No mismatches found."
    exit 0
fi
