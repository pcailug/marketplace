# Org-scanning Claude Code marketplace 設計

日期：2026-10-14　狀態：已核准（brainstorming 確認後使用者授權直接實作）

## 目標

公開的 Claude Code plugin marketplace。GitHub org 底下的 plugin repo **自動**出現在清單裡，
不需要手動註冊。程式不寫死 org 名稱（取自 repo 所在位置），可直接搬到任何 org 使用。

- 安裝：`/plugin marketplace add <org>/marketplace`，`/plugin install <name>@<org>`
- 第一版只產生 Claude 格式（同時涵蓋 Claude Code、Copilot CLI、Factory Droid、Qwen Code）。
  之後要加 Codex／Gemini／Cursor 格式時，由 `plugin.json` 產生，不改 plugin repo 的維護方式。

## 名詞

- **M**：`<org>/marketplace`
- **P**：任一 plugin repo，例如 `<org>/github-convention`
- **C1**：M 提供的可重用 workflow `notify.yml`，在 P 執行，通知 M
- **C2**：M 的 `regenerate.yml`，掃描 org 並產生清單

## 上架條件

repo 同時符合才會列入：

1. 在本 org 底下
2. **public**、未封存、不是 fork、不是 M 本身
3. 預設分支根目錄有 `.claude-plugin/plugin.json`，內容是合法 JSON，`name` 符合 kebab-case

private repo 不上架：公開清單會洩漏名稱與描述，而且別人裝不起來。

## 清單格式

```json
{
  "name": "<org>",
  "owner": { "name": "<org>", "url": "https://github.com/<org>" },
  "description": "Claude Code plugin 清單（由 CI 掃描 org 自動產生，請勿手改）",
  "plugins": [
    { "name": "<plugin.json name>", "source": { "source": "github", "repo": "<org>/<repo>" }, "description": "<plugin.json description>" }
  ]
}
```

- 名稱與描述**只**來自 P 的 `plugin.json`，M 不另外維護。
- 不鎖 `ref`／`sha`：使用者拿到預設分支最新版。P 有寫 `version` 時，更新必須 bump 才會被偵測。
- 依 `name` 排序，輸出穩定，沒有實質變更就不會產生 diff。
- 同名 plugin（兩個 repo 的 `plugin.json` 用同一個 `name`）：保留 repo 名稱排序在前者，其餘發出警告並略過。
- 單一 P 的 `plugin.json` 有問題只略過該 P 並發警告，不讓整份清單失敗。
- P 自帶 `.claude-plugin/marketplace.json` 時發警告（應該只靠 C1 註冊）。

## C2：regenerate.yml（在 M）

觸發：`repository_dispatch`（type `plugin-updated`）、每日排程（UTC 19:00 = 台北 03:00）、`workflow_dispatch`。
沒有 `push` 觸發；另外 `GITHUB_TOKEN` 產生的 commit 本來就不會觸發 workflow，兩層防遞迴。

步驟：單元測試 → `gen_marketplace.py` 產生 → `claude plugin validate . --strict` → 有變更才 commit 並 push。
權限：`contents: write`，只用內建 `GITHUB_TOKEN`（讀 public repo、寫回 M）。
`concurrency` 讓同時觸發的執行排隊，不互相覆蓋。

## C1：notify.yml（可重用，在 P 執行）

P 的 `.github/workflows/marketplace.yml`：

```yaml
on:
  push: { branches: [main], paths: ['.claude-plugin/plugin.json'] }
  workflow_dispatch:
jobs:
  notify:
    uses: <org>/marketplace/.github/workflows/notify.yml@main
    secrets: inherit
```

`notify.yml` 用 org secret `MARKETPLACE_DISPATCH_TOKEN` 呼叫
`POST /repos/${{ github.repository_owner }}/marketplace/dispatches`。token 是 fine-grained PAT，
只授權 `<org>/marketplace` 的 Contents 讀寫（`repository_dispatch` 需要的最小權限）。
secret 空白時 job 明確失敗並說明原因；token 過期時同樣失敗（401）。漏掉的通知由每日排程補上。

只在 `plugin.json` 變更時觸發：清單內容只來自它。改名、改 visibility、封存不產生 commit，
用 `workflow_dispatch` 手動觸發或等排程。

## github-convention plugin（第一個 P）

通用的 GitHub 作業規範（內容不含任何帳號或 org 名稱，執行時才判斷）：

| Skill | 用途 |
|---|---|
| `github-new-repo` | 在使用者的個人帳號或 org 建 repo：資料卡、唯讀檢查、push 前祕密與個資掃描、建立、驗證 |
| `github-new-plugin` | 在 plugin 專用 org 建 plugin repo 並上架：硬條件、`plugin.json`、C1、命名、下架、驗證、疑難排解 |

共用規範 `references/conventions.md`：命名、撞名、visibility、default branch、
個資與歷史改寫、實測過的細節（標註來源是「實測」或「官方文件」與版本）。

## 測試與驗證

- `gen_marketplace.py` 的篩選與組裝邏輯是純函式，用 `unittest`（標準函式庫）測試，HTTP 以假資料替換。
- 本機：`claude plugin validate` 檢查 M 與 github-convention。
- 上線後：手動觸發 C2，確認清單內容；在隔離的 `CLAUDE_CONFIG_DIR` 實際 add marketplace、install plugin，確認兩個 skill 載入。
- C1 → C2 全鏈路：使用者設好 org secret 後，在 github-convention 手動觸發一次，確認 M 收到 `repository_dispatch`。
