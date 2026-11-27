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


def build_table(repos: list[dict], token: str | None, lang_mode: str = "en") -> str:
    if lang_mode == "es":
        lines = [
            "| Proyecto | Stack | Estrellas | Actualizado | Enlaces |",
            "|---|---|---:|:---:|---|",
        ]
        repo_lbl, web_lbl, rel_lbl, docs_lbl = "Repo", "Web", "Releases", "Docs"
    else:
        lines = [
            "| Project | Stack | Stars | Updated | Links |",
            "|---|---|---:|:---:|---|",
        ]
        repo_lbl, web_lbl, rel_lbl, docs_lbl = "Repo", "Website", "Releases", "Docs"

    for r in repos:
        name = r["name"]
        html_url = r["html_url"]
        desc = (r.get("description") or "").replace("|", "\\|").strip()
        if len(desc) > 105:
            desc = desc[:102].rstrip() + "..."
        lang = r.get("language") or docs_lbl
        stars = r.get("stargazers_count", 0)
        stars_cell = f"⭐ {stars}" if stars > 0 else "—"
        pushed = (r.get("pushed_at") or "")[:10]

        links = [f"[{repo_lbl}]({html_url})"]
        homepage = (r.get("homepage") or "").strip()
        if homepage and homepage.startswith("http"):
            links.append(f"[{web_lbl}]({homepage})")
        if r.get("_has_release"):
            links.append(f"[{rel_lbl}]({html_url}/releases)")

        label = f"**[{name}]({html_url})**"
        if desc:
            label += f"<br/><sub>{desc}</sub>"

        lines.append(
            f"| {label} | `{lang}` | {stars_cell} | `{pushed}` | {' · '.join(links)} |"
        )

    return "\n".join(lines)


def update_file(path: Path, table: str) -> bool:
    if not path.exists():
        return False
    content = path.read_text(encoding="utf-8")
    if START_MARKER not in content or END_MARKER not in content:
        return False
    replacement = f"{START_MARKER}\n{table}\n{END_MARKER}"
    updated = re.sub(
        f"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
        lambda _: replacement,
        content,
        flags=re.DOTALL,
    )
    if updated != content:
        path.write_text(updated, encoding="utf-8", newline="\n")
        return True
    return False


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    root = Path(__file__).resolve().parents[2]
    token = os.environ.get("GITHUB_TOKEN") or None
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
    for r in selected:
        r["_has_release"] = has_release(r["name"], token)

    changed = False
    for fname, mode in (("README.md", "en"), ("README_ES.md", "es")):
        if update_file(root / fname, build_table(selected, token, mode)):
            print(f"{fname} updated.")
            changed = True
    if not changed:
        print("README files already up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
