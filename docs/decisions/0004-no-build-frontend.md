# 0004. Frontend is plain ES modules with vendored libraries and no build step

- **Status:** accepted
- **Date:** 2026-11-15 (recorded after the fact; in force since PR #8)
- **Relates to:** `app/static/`, security headers in `app/main.py`

## Context

The app is small, maintained occasionally, and self-hosted by people who should not need Node to run it. It handles money and logins, so it sends a strict Content-Security-Policy (`script-src 'self'`).

## Decision

FastAPI serves HTML skeletons; plain ES modules build the UI with the `el()` helper. Pico CSS and Chart.js are vendored in `app/static/vendor/`, nothing loads from a CDN. No inline scripts or handlers, and no `innerHTML` with data.

## Consequences

**Good:** no toolchain, nothing to compile before deploying, and the CSP blocks injected scripts. Pages work offline on the local network.

**Bad:** no TypeScript, no components, no tree-shaking. Updating Pico or Chart.js means replacing the vendored file by hand. Web fonts and other third-party assets must be vendored too, or skipped.

**Neutral:** themes are plain CSS files loaded after `style.css`.

## Alternatives considered

| Option | Why not |
|---|---|
| React/Vue/Svelte with a bundler | Toolchain and build step for a handful of pages |
| Server-rendered templates (Jinja) | Possible, but the API is already the single source for data |
| CDN-hosted libraries | Breaks the CSP and offline use |

## Revisit when

A page needs client-side state complex enough that `el()` code becomes hard to follow, or a dependency is only shipped as an npm package.
