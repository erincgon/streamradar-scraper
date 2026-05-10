"""Helpers to read Next.js embedded page state from HTML."""

from __future__ import annotations

import json
import re


def parse_next_data_json(html: str) -> dict | None:
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
        html,
        re.DOTALL,
    )
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
