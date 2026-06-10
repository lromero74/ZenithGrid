"""
Cache-control policy for serving the built SPA.

Vite emits content-hashed filenames under dist/assets/, so those files never
change in place — they are safe to cache forever (immutable). index.html is
the opposite: it is the pointer to the current hashes, and a stale cached copy
references chunk files deleted by the last rebuild, which boots the app from a
404 and renders a blank screen. It must always be revalidated.
"""

from fastapi.staticfiles import StaticFiles

# Hashed assets: cache for a year, never revalidate.
ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"

# SPA shell (index.html and other non-hashed files): always revalidate.
# Conditional requests still get 304s, so this costs one small request.
HTML_CACHE_CONTROL = "no-cache"


class CachedStaticFiles(StaticFiles):
    """StaticFiles that marks content-hashed assets as immutable."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = ASSET_CACHE_CONTROL
        return response
