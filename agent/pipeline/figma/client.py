"""
Loads a Figma file as JSON, from a saved .json file or from the Figma REST API.
Files downloaded from the API are saved in agent/.cache/figma/ and reused,
so each file is only downloaded once (the free Figma plan allows very few calls).
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# agent/.cache/figma/ -- where downloaded files are saved (ignored by git)
CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "figma"

#Pull the file key out of a Figma URL, e.g. figma.com/design/<KEY>/My-File -> <KEY>.
def get_file_key(url: str) -> str:
    match = re.search(r"figma\.com/(?:design|file)/([A-Za-z0-9]+)", url)
    if not match:
        raise ValueError(f"Not a Figma file URL: {url}")
    return match.group(1)

#Download one Figma file's full JSON from the Figma REST API
def fetch_from_api(file_key: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"https://api.figma.com/v1/files/{file_key}",
        headers={"X-Figma-Token": token},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data: dict[str, Any] = json.load(response)
            return data
    except urllib.error.HTTPError as error:
        # Turn the common failures into messages a person can act on
        if error.code == 429:
            wait = error.headers.get("Retry-After", "unknown")
            raise RuntimeError(f"Figma rate limit hit. Try again in {wait} seconds.") from error
        if error.code == 403:
            raise RuntimeError("Figma said no: the token is wrong or can't open this file.") from error
        if error.code == 404:
            raise RuntimeError(f"Figma file {file_key} not found.") from error
        raise


def load_figma_file(source: str, refresh: bool = False) -> dict[str, Any]:
    """
    Load a Figma file from a local .json path or a Figma URL.
    For URLs, a saved copy in the cache is used when there is one.
    refresh=True ignores the saved copy and downloads the file again.
    """
    # Local file: just read it
    if not source.startswith("http"):
        data: dict[str, Any] = json.loads(Path(source).read_text())
        return data

    file_key = get_file_key(source)
    cache_file = CACHE_DIR / f"{file_key}.json"

    # Saved copy: reuse it instead of calling Figma
    if cache_file.exists() and not refresh:
        print(f"Using cached copy: {cache_file}")
        cached: dict[str, Any] = json.loads(cache_file.read_text())
        return cached

    # No saved copy: download it once and save it
    token = os.environ.get("FIGMA_TOKEN")
    if not token:
        raise RuntimeError("FIGMA_TOKEN is not set. Add FIGMA_TOKEN=... to agent/.env")
    print(f"Downloading Figma file {file_key} ...")
    data = fetch_from_api(file_key, token)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data))
    return data
