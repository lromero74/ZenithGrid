# Branding

This directory controls the visual identity of your trading bot instance.

## Structure

```
branding/
├── README.md              ← You are here
├── template/              ← Tracked in git — default brand (copy this to start)
│   ├── brand.json         ← All configurable fields with defaults
│   └── images/            ← Place your brand images here
└── custom/                ← NOT tracked in git — your active brand
    ├── brand.json
    └── images/
        └── hero.jpg       ← Login page background (optional)
```

## Setup

1. Copy the template to create your custom brand:
   ```bash
   cp -r branding/template branding/custom
   ```

2. Edit `branding/custom/brand.json` with your brand details.

3. Add any images to `branding/custom/images/`.

4. Restart the backend to pick up changes:
   ```bash
   ./bot.sh restart --dev --back-end
   ```

The app reads from `branding/custom/` first. If that doesn't exist, it falls back to `branding/template/` defaults.

## brand.json Fields

| Field | Description | Example |
|-------|-------------|---------|
| `name` | Full brand name (login page title) | `"Big Truckin' Crypto Bot"` |
| `shortName` | Short name (header, emails, about) | `"BTC-Bot"` |
| `tagline` | Subtitle shown in header and emails | `"Autonomous Trading Platform"` |
| `loginTitle` | Title on login page (can differ from name) | `"Big Truckin' Crypto Bot"` |
| `loginTagline` | Tagline on login page | `"Autonomous Trading. Road-Tested."` |
| `company` | Company name | `"Romero Tech Solutions"` |
| `companyLine` | Shown below login tagline (leave empty to hide) | `"A Romero Tech Solutions Product"` |
| `copyright` | Footer text in emails | `"Romero Tech Solutions"` |
| `defaultTheme` | `"neon"` or `"classic"` (user can override in Settings) | `"neon"` |
| `colors.primary` | Primary accent color (CSS hex) | `"#00d4ff"` |
| `colors.primaryHover` | Primary hover color | `"#00b8e6"` |
| `images.loginBackground` | Filename in `images/` for login backdrop (empty = none) | `"hero.jpg"` |

## Images

Place images in `branding/custom/images/`. They're served at `/api/brand/images/<filename>`.

- **hero.jpg** — Login page background (displayed at low opacity behind the form)
- Keep images small (< 200KB) for fast page loads
- Supported formats: jpg, png, webp, svg

## Notes

- The `branding/custom/` directory is in `.gitignore` — your brand assets stay private
- Changes to `brand.json` require a backend restart to take effect
- Theme choice (`neon` / `classic`) sets the default; users can toggle in Settings
- The maintenance page (`frontend/maintenance.html`) is static HTML and must be edited manually
