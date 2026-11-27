"""Auto-updates the public repositories table in README.md."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

OWNER = "oscarlosu-lab"
INCLUDE_FORKS = {"greenlight"}
START_MARKER = "<!-- REPOS:START -->"
END_MARKER = "<!-- REPOS:END -->"


def github_get(url: str, token: str | None) -> object:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{OWNER}-profile-updater",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def has_release(repo_name: str, token: str | None) -> bool:
    try:
        data = github_get(
            f"https://api.github.com/repos/{OWNER}/{repo_name}/releases?per_page=1",
            token,
        )
        return isinstance(data, list) and len(data) > 0
    except urllib.error.HTTPError:
        return False


def build_table(token: str | None) -> str:
    repos = github_get(
        f"https://api.github.com/users/{OWNER}/repos?type=owner&per_page=100&sort=pushed",
        token,
    )
    if not isinstance(repos, list):
        raise RuntimeError("Unexpected GitHub API response")

    selected = [
        r
        for r in repos
        if not r.get("private")
        and not r.get("archived")
        and r.get("name") != OWNER
        and (not r.get("fork") or r.get("name") in INCLUDE_FORKS)
    ]
    selected.sort(key=lambda r: r.get("pushed_at", ""), reverse=True)

    lines = [
        "| Repository | Stack | Stars | Updated | Links |",
        "|---|---|---:|---|---|",
    ]
    for r in selected:
        name = r["name"]
        html_url = r["html_url"]
        desc = (r.get("description") or "").replace("|", "\\|").strip()
        if len(desc) > 95:
            desc = desc[:92].rstrip() + "..."
        lang = r.get("language") or "—"
        stars = r.get("stargazers_count", 0)
        pushed = (r.get("pushed_at") or "")[:10]

        links = [f"[Repo]({html_url})"]
        homepage = (r.get("homepage") or "").strip()
        if homepage and homepage.startswith("http"):
            links.append(f"[Website]({homepage})")
        if has_release(name, token):
            links.append(f"[Releases]({html_url}/releases)")

        label = f"**[{name}]({html_url})**"
        if desc:
            label += f"<br/><sub>{desc}</sub>"

        lines.append(
            f"| {label} | `{lang}` | {stars} | `{pushed}` | {' · '.join(links)} |"
        )

    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    readme_path = Path(__file__).resolve().parents[2] / "README.md"
    content = readme_path.read_text(encoding="utf-8")
    if START_MARKER not in content or END_MARKER not in content:
        print("Missing REPOS markers in README.md", file=sys.stderr)
        return 1

    token = os.environ.get("GITHUB_TOKEN") or None
    table = build_table(token)
    replacement = f"{START_MARKER}\n{table}\n{END_MARKER}"
    updated = re.sub(
        f"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
        lambda _: replacement,
        content,
        flags=re.DOTALL,
    )

    if updated != content:
        readme_path.write_text(updated, encoding="utf-8", newline="\n")
        print("README.md updated.")
    else:
        print("README.md already up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
