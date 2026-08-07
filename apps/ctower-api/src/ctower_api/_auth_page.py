"""Human presentation for authentication states that cannot start sign-in."""

from __future__ import annotations

from fastapi.responses import HTMLResponse

__all__: tuple[str, ...] = ()

_UNAVAILABLE_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>Sign-in isn't available yet · ctower</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #ffffff;
      --surface: #fafafa;
      --line: #eaeaea;
      --ink: #171717;
      --ink-2: #525252;
      --accent: #0d9488;
      --font: -apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", ui-sans-serif,
        Roboto, "Helvetica Neue", Arial, sans-serif;
      --r-lg: 8px;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        color-scheme: dark;
        --bg: #0a0d13;
        --surface: #11161f;
        --line: #232c3c;
        --ink: #e9edf5;
        --ink-2: #a7b2c6;
        --accent: #2dd4bf;
      }
    }
    * { box-sizing: border-box; }
    body {
      min-height: 100vh;
      min-height: 100svh;
      margin: 0;
      display: grid;
      place-items: center;
      padding: 24px;
      background: var(--bg);
      color: var(--ink);
      font-family: var(--font);
      -webkit-font-smoothing: antialiased;
    }
    main { width: min(100%, 520px); }
    .brand {
      display: flex;
      align-items: center;
      gap: 9px;
      margin: 0 0 16px;
      color: var(--ink-2);
      font-size: 14px;
      font-weight: 600;
      letter-spacing: -.011em;
    }
    .mark {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent);
    }
    section {
      padding: clamp(28px, 7vw, 48px);
      border: 1px solid var(--line);
      border-radius: var(--r-lg);
      background: var(--surface);
    }
    h1 {
      margin: 0;
      font-size: clamp(28px, 7vw, 40px);
      font-weight: 600;
      letter-spacing: -.03em;
      line-height: 1.1;
    }
    p {
      max-width: 38ch;
      margin: 18px 0 0;
      color: var(--ink-2);
      font-size: 16px;
      line-height: 1.6;
    }
  </style>
</head>
<body>
  <main>
    <p class="brand"><span class="mark" aria-hidden="true"></span>ctower</p>
    <section aria-labelledby="page-title">
      <h1 id="page-title">Sign-in isn't available yet</h1>
      <p>Contact the operator or try again later.</p>
    </section>
  </main>
</body>
</html>
"""


def unavailable_auth_page() -> HTMLResponse:
    """Return the honest human surface while sign-in has no available provider."""

    return HTMLResponse(
        content=_UNAVAILABLE_PAGE,
        status_code=503,
        headers={"Cache-Control": "no-store"},
    )
