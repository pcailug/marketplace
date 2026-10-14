#!/usr/bin/env python3
"""掃描 GitHub org 裡的 Claude Code plugin，產生 marketplace.json 到 stdout。

判斷「是不是 plugin」的唯一依據：public repo 的預設分支根目錄有 .claude-plugin/plugin.json。
名稱與描述一律從該檔案讀取，本程式不另外維護一份，避免兩邊漂移。

環境變數：
  GITHUB_TOKEN       讀取 org 的 public repo（Actions 內建的即可）
  GITHUB_REPOSITORY  本 repo（<org>/<name>）。org 取自它，掃描時也排除自己
  ORG                可選，覆寫要掃描的 org

marketplace 名稱 = org 名稱，安裝時用 <plugin>@<org>。
"""
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

API = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")

DESCRIPTION = "Claude Code plugin 清單（由 CI 掃描 org 自動產生，請勿手改）"

PLUGIN_JSON = ".claude-plugin/plugin.json"
MARKETPLACE_JSON = ".claude-plugin/marketplace.json"

_KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# claude plugin validate 會拒絕的名稱
_RESERVED_PREFIXES = ("claude-", "anthropic-", "anthropics-", "cc-plugin-")
_RESERVED_NAMES = {"claude", "anthropic", "claude-code", "claude-mods"}


def valid_plugin_name(name):
    if not isinstance(name, str) or not _KEBAB.match(name):
        return False
    return name not in _RESERVED_NAMES and not name.startswith(_RESERVED_PREFIXES)


def eligible(repo, self_repo):
    return not (
        repo.get("private")
        or repo.get("visibility", "public") != "public"
        or repo.get("archived")
        or repo.get("disabled")
        or repo.get("fork")
        or repo["full_name"].lower() == (self_repo or "").lower()
    )


def build_marketplace(repos, fetch_file, *, org, self_repo, warn):
    """repos：GitHub API 的 repo 物件；fetch_file(full_name, path, ref) -> str | None。"""
    plugins = {}
    for repo in sorted(repos, key=lambda r: r["full_name"].lower()):
        if not eligible(repo, self_repo):
            continue
        full, ref = repo["full_name"], repo.get("default_branch") or "main"

        raw = fetch_file(full, PLUGIN_JSON, ref)
        if raw is None:
            continue
        try:
            meta = json.loads(raw)
            if not isinstance(meta, dict):
                raise ValueError("不是 JSON 物件")
        except ValueError as e:
            warn(f"{full} 的 {PLUGIN_JSON} 不是合法 JSON：{e}，略過")
            continue

        name = meta.get("name", repo["name"])
        if not valid_plugin_name(name):
            warn(f"{full} 的 plugin 名稱 {name!r} 不合規（需 kebab-case，且不能用 claude-／anthropic- 等保留字開頭），略過")
            continue
        if name in plugins:
            warn(f"plugin 名稱 {name!r} 重複：保留 {plugins[name]['source']['repo']}，略過 {full}")
            continue
        if fetch_file(full, MARKETPLACE_JSON, ref) is not None:
            warn(f"{full} 自帶 {MARKETPLACE_JSON}，註冊應只靠 C1（見 github-convention）")

        desc = meta.get("description")
        plugins[name] = {
            "name": name,
            "source": {"source": "github", "repo": full},
            "description": desc if isinstance(desc, str) else "",
        }

    return {
        "name": org,
        "owner": {"name": org, "url": f"https://github.com/{org}"},
        "description": DESCRIPTION,
        "plugins": [plugins[n] for n in sorted(plugins)],
    }


# ── GitHub API ──────────────────────────────────────────────────────────────


def _request(url, token, accept="application/vnd.github+json"):
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "claude-plugin-marketplace-generator"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30)


def list_org_repos(org, token):
    page = 1
    while True:
        url = f"{API}/orgs/{org}/repos?type=public&per_page=100&page={page}"
        with _request(url, token) as r:
            batch = json.load(r)
        yield from batch
        if len(batch) < 100:
            return
        page += 1


def make_fetcher(token):
    def fetch_file(full_name, path, ref):
        url = f"{API}/repos/{full_name}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(ref)}"
        try:
            with _request(url, token) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise
        if isinstance(data, dict) and data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8")
        return None

    return fetch_file


def main():
    self_repo = os.environ.get("GITHUB_REPOSITORY", "")
    org = os.environ.get("ORG") or self_repo.partition("/")[0]
    if not org:
        sys.exit("需要 GITHUB_REPOSITORY（<org>/<repo>）或 ORG")
    token = os.environ.get("GITHUB_TOKEN", "")

    def warn(msg):
        # GitHub Actions 會把 ::warning:: 顯示在執行摘要
        print(f"::warning::{msg}", file=sys.stderr)

    repos = list(list_org_repos(org, token))
    result = build_marketplace(repos, make_fetcher(token), org=org, self_repo=self_repo, warn=warn)
    print(f"掃描 {len(repos)} 個 public repo，上架 {len(result['plugins'])} 個 plugin", file=sys.stderr)
    for p in result["plugins"]:
        print(f"  · {p['name']} ← {p['source']['repo']}", file=sys.stderr)

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
