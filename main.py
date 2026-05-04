"""Vercel/FastAPI entrypoint.

Vercel auto-detects FastAPI projects by looking for an `app` object in common
root files such as `main.py`. The actual application lives in
`decksweep.main`.
"""

from decksweep.main import app

