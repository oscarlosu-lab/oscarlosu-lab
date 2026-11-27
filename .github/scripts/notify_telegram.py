"""Publishes new releases, new public repos, or manual announcements to Telegram."""

from __future__ import annotations

import html
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OWNER = "oscarlosu-lab"
INCLUDE_FORKS = {"greenlight"}
STATE_REL = Path(".github/state/telegram_seen.json")


def http_json(url: str, headers: dict[str, str] | None = None, data: bytes | None = None) -> object:
    req = urllib.request.Request(url, headers=headers or {}, data=data)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def gh_get(url: str, gh_token: str | None) -> object:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{OWNER}-telegram-news",
    }
    if gh_token:
        headers["Authorization"] = f"Bearer {gh_token}"
    return http_json(url, headers=headers)


def tg_send(bot_token: str, chat_id: str, text_html: str) -> None:
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text_html,
            "parse_mode": "HTML",
            "disable_web_page_preview": "false",
        }
    ).encode("utf-8")
    res = http_json(f"https://api.telegram.org/bot{bot_token}/sendMessage", data=payload)
    if not isinstance(res, dict) or not res.get("ok"):
        raise RuntimeError(f"Telegram API error: {res}")


def load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"repos": [], "releases": {}}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def format_release_msg(repo: dict, rel: dict) -> str:
    name = html.escape(repo["name"])
    tag = html.escape(rel.get("tag_name", ""))
    title = html.escape((rel.get("name") or tag).strip())
    url = rel.get("html_url") or repo["html_url"]
    is_pre = bool(rel.get("prerelease"))
    badge = "🧪 Pre-release / RC" if is_pre else "🚀 New Release / Nueva Versión"
    desc = html.escape((repo.get("description") or "").strip())
    if len(desc) > 180:
        desc = desc[:177].rstrip() + "..."
    lines = [
        f"<b>{badge}: {name} {tag}</b>",
        f"📌 {title}" if title and title != tag else "",
        f"\n{desc}" if desc else "",
        f'\n🔗 <a href="{url}">Download / Descargar</a> · <a href="https://ko-fi.com/oscarlosu">Ko-fi</a>',
    ]
    return "\n".join(x for x in lines if x)


def format_new_repo_msg(repo: dict) -> str:
    name = html.escape(repo["name"])
    url = repo["html_url"]
    desc = html.escape((repo.get("description") or "New open-source project.").strip())
    lang = html.escape(repo.get("language") or "Multi-platform")
    return (
        f"<b>✨ New Repository / Nuevo Repositorio: {name}</b>\n"
        f"🛠 Stack: <code>{lang}</code>\n\n"
        f"{desc}\n\n"
        f'🔗 <a href="{url}">GitHub</a> · <a href="https://ko-fi.com/oscarlosu">Ko-fi</a>'
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    gh_token = os.environ.get("GITHUB_TOKEN", "").strip() or None
    manual_title = os.environ.get("MANUAL_TITLE", "").strip()
    manual_body = os.environ.get("MANUAL_BODY", "").strip()
    include_pre = os.environ.get("INCLUDE_PRERELEASES", "true").lower() == "true"

    if not bot_token or not chat_id:
        print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.", file=sys.stderr)
        return 1

    if manual_title or manual_body:
        msg = f"<b>📣 {html.escape(manual_title or 'Announcement / Aviso')}</b>\n\n{html.escape(manual_body)}"
        tg_send(bot_token, chat_id, msg)
        print("Sent manual announcement.")
        return 0

    root = Path(__file__).resolve().parents[2]
    state_path = root / STATE_REL
    first_run = not state_path.exists()
    state = load_state(state_path)
    seen_repos = set(state.get("repos", []))
    seen_releases: dict[str, list[str]] = state.get("releases", {})

    repos = gh_get(f"https://api.github.com/users/{OWNER}/repos?type=owner&per_page=100&sort=pushed", gh_token)
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

    sent = 0
    for r in selected:
        rname = r["name"]
        if rname not in seen_repos:
            seen_repos.add(rname)
            if not first_run:
                tg_send(bot_token, chat_id, format_new_repo_msg(r))
                sent += 1

        try:
            rels = gh_get(f"https://api.github.com/repos/{OWNER}/{rname}/releases?per_page=5", gh_token)
        except urllib.error.HTTPError:
            rels = []
        if not isinstance(rels, list):
            continue

        known_tags = set(seen_releases.get(rname, []))
        for rel in reversed(rels):
            if rel.get("draft"):
                continue
            if rel.get("prerelease") and not include_pre:
                continue
            tag = rel.get("tag_name")
            if not tag or tag in known_tags:
                continue
            known_tags.add(tag)
            if not first_run:
                tg_send(bot_token, chat_id, format_release_msg(r, rel))
                sent += 1
        seen_releases[rname] = sorted(known_tags)

    state["repos"] = sorted(seen_repos)
    state["releases"] = seen_releases
    save_state(state_path, state)
    print(f"Done. first_run={first_run}, sent={sent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
