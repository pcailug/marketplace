import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gen_marketplace as gm  # noqa: E402

ORG = "example-org"
SELF = "example-org/marketplace"


def repo(name, **kw):
    r = {
        "name": name,
        "full_name": f"{ORG}/{name}",
        "private": False,
        "visibility": "public",
        "archived": False,
        "disabled": False,
        "fork": False,
        "default_branch": "main",
    }
    r.update(kw)
    return r


class FakeFiles:
    """(full_name, path) -> 檔案內容；不存在回 None。"""

    def __init__(self, files):
        self.files = files
        self.calls = []

    def __call__(self, full_name, path, ref):
        self.calls.append((full_name, path, ref))
        return self.files.get((full_name, path))


def pj(**kw):
    return json.dumps(kw)


class BuildTest(unittest.TestCase):
    def build(self, repos, files):
        warnings = []
        result = gm.build_marketplace(repos, FakeFiles(files), org=ORG, self_repo=SELF, warn=warnings.append)
        return result, warnings

    def test_lists_repo_with_plugin_json(self):
        result, warnings = self.build(
            [repo("github-convention")],
            {("example-org/github-convention", ".claude-plugin/plugin.json"): pj(name="github-convention", description="規範")},
        )
        self.assertEqual(
            result["plugins"],
            [
                {
                    "name": "github-convention",
                    "source": {"source": "github", "repo": "example-org/github-convention"},
                    "description": "規範",
                }
            ],
        )
        self.assertEqual(warnings, [])

    def test_top_level_fields(self):
        result, _ = self.build([], {})
        self.assertEqual(result["name"], "example-org")
        self.assertEqual(result["owner"], {"name": "example-org", "url": "https://github.com/example-org"})
        self.assertIn("description", result)
        self.assertEqual(result["plugins"], [])

    def test_skips_repo_without_plugin_json_silently(self):
        result, warnings = self.build([repo("notes")], {})
        self.assertEqual(result["plugins"], [])
        self.assertEqual(warnings, [])

    def test_skips_private_archived_fork_disabled_and_self(self):
        files = {}
        repos = [
            repo("a", private=True, visibility="private"),
            repo("b", archived=True),
            repo("c", fork=True),
            repo("d", disabled=True),
            repo("marketplace"),
        ]
        for r in repos:
            files[(r["full_name"], ".claude-plugin/plugin.json")] = pj(name=r["name"])
        fetch = FakeFiles(files)
        result = gm.build_marketplace(repos, fetch, org=ORG, self_repo=SELF, warn=lambda m: None)
        self.assertEqual(result["plugins"], [])
        self.assertEqual(fetch.calls, [])  # 不合格的 repo 連讀都不讀

    def test_reads_from_default_branch(self):
        fetch = FakeFiles({})
        gm.build_marketplace([repo("x", default_branch="trunk")], fetch, org=ORG, self_repo=SELF, warn=lambda m: None)
        self.assertEqual(fetch.calls[0], ("example-org/x", ".claude-plugin/plugin.json", "trunk"))

    def test_invalid_json_is_skipped_with_warning(self):
        result, warnings = self.build([repo("bad")], {("example-org/bad", ".claude-plugin/plugin.json"): "{nope"})
        self.assertEqual(result["plugins"], [])
        self.assertTrue(any("example-org/bad" in w and "JSON" in w for w in warnings))

    def test_invalid_name_is_skipped_with_warning(self):
        result, warnings = self.build(
            [repo("bad")], {("example-org/bad", ".claude-plugin/plugin.json"): pj(name="Bad_Name")}
        )
        self.assertEqual(result["plugins"], [])
        self.assertTrue(any("Bad_Name" in w for w in warnings))

    def test_name_falls_back_to_repo_name(self):
        result, _ = self.build([repo("tool-x")], {("example-org/tool-x", ".claude-plugin/plugin.json"): pj(description="d")})
        self.assertEqual(result["plugins"][0]["name"], "tool-x")

    def test_missing_description_becomes_empty_string(self):
        result, _ = self.build([repo("x")], {("example-org/x", ".claude-plugin/plugin.json"): pj(name="x")})
        self.assertEqual(result["plugins"][0]["description"], "")

    def test_duplicate_plugin_names_keep_first_repo_and_warn(self):
        files = {
            ("example-org/b-repo", ".claude-plugin/plugin.json"): pj(name="same"),
            ("example-org/a-repo", ".claude-plugin/plugin.json"): pj(name="same"),
        }
        result, warnings = self.build([repo("b-repo"), repo("a-repo")], files)
        self.assertEqual(len(result["plugins"]), 1)
        self.assertEqual(result["plugins"][0]["source"]["repo"], "example-org/a-repo")
        self.assertTrue(any("same" in w and "b-repo" in w for w in warnings))

    def test_plugins_sorted_by_name(self):
        files = {
            ("example-org/r1", ".claude-plugin/plugin.json"): pj(name="zeta"),
            ("example-org/r2", ".claude-plugin/plugin.json"): pj(name="alpha"),
        }
        result, _ = self.build([repo("r1"), repo("r2")], files)
        self.assertEqual([p["name"] for p in result["plugins"]], ["alpha", "zeta"])

    def test_warns_when_plugin_repo_ships_its_own_marketplace_json(self):
        files = {
            ("example-org/x", ".claude-plugin/plugin.json"): pj(name="x"),
            ("example-org/x", ".claude-plugin/marketplace.json"): "{}",
        }
        result, warnings = self.build([repo("x")], files)
        self.assertEqual(len(result["plugins"]), 1)
        self.assertTrue(any("marketplace.json" in w for w in warnings))


class NameRuleTest(unittest.TestCase):
    def test_valid_names(self):
        for n in ["github-convention", "x", "tool2", "a-b-c"]:
            self.assertTrue(gm.valid_plugin_name(n), n)

    def test_invalid_names(self):
        for n in ["", "Bad", "a_b", "-a", "a-", "a--b", "claude-x", "anthropic-x", "claude", 42, None]:
            self.assertFalse(gm.valid_plugin_name(n), n)


if __name__ == "__main__":
    unittest.main()
