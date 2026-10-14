# Claude Code plugin marketplace

這個 org 的 Claude Code plugin 集散地。**org 底下的 plugin repo 會自動出現在清單裡，不需要手動註冊。**

以下的 `<org>` 是這個 repo 所在的 GitHub org，marketplace 名稱就是 org 名稱。

## 使用者：安裝 plugin

只需要做一次：

```
/plugin marketplace add <org>/marketplace
```

之後用 `/plugin` 選要裝的，或直接 `/plugin install <plugin>@<org>`。
新 plugin 上架後不用重新 add，`/plugin marketplace update <org>` 即可。

其他讀 Claude 格式 marketplace 的工具也能用同一份清單，例如 GitHub Copilot CLI
（`copilot plugin marketplace add <org>/marketplace`）。

## plugin 作者：怎麼上架

可以裝 `github-convention` plugin，用它的 `github-new-plugin` skill 一步步建。手動的話：

1. 在這個 org 底下建 **public** repo
2. 根目錄放 `.claude-plugin/plugin.json` —— **這是「是不是 plugin」的唯一判斷依據**
3. 建 `.github/workflows/marketplace.yml`：

   ```yaml
   name: Register to marketplace
   on:
     push: { branches: [main], paths: ['.claude-plugin/plugin.json'] }
     workflow_dispatch:
   jobs:
     notify:
       uses: <org>/marketplace/.github/workflows/notify.yml@main
       secrets: inherit
   ```

4. push 到 `main` → 清單自動更新

**只有 `.claude-plugin/plugin.json` 有異動時才會觸發**（清單只含 name／source／description，
都來自它）。改 skill、README 或程式碼不會、也不需要重新產生清單。

**不要自帶 `.claude-plugin/marketplace.json`。** 註冊一律靠上面的 workflow；CI 掃到會警告。

## 這個 repo 怎麼運作

```
push plugin repo（P）的 plugin.json
  └─ C1  notify.yml（在 P 執行）用 org secret 對 M 發 repository_dispatch
       └─ C2  regenerate.yml（在 M 執行）
            └─ gen_marketplace.py  掃 org 的 public repo、讀每個 plugin.json
                 └─ claude plugin validate → 產生 .claude-plugin/marketplace.json，有變更才 commit
```

**`.claude-plugin/marketplace.json` 是 CI 產物，不要手改** —— 下次重新產生就會被蓋掉。
要改名稱或描述請改該 plugin 自己的 `plugin.json`。

手動重新產生：`gh workflow run regenerate.yml -R <org>/marketplace`

程式裡沒有寫死任何 org 名稱：org 取自 repo 所在位置，所以整個 repo 可以直接 fork 或複製到別的 org 使用。

### 上架條件

repo 同時符合才會列入：在本 org、**public**、未封存、不是 fork、預設分支根目錄有合法的
`.claude-plugin/plugin.json`，且 `name` 是 kebab-case、不以 `claude-`／`anthropic-` 等保留字開頭。
單一 plugin 不合格只略過它並在 Actions 顯示警告，不影響其他 plugin。

### 設計上的幾個決定

| 決定 | 原因 |
|---|---|
| C2 在 M 執行，P 只發通知 | 能寫入 M 的權限只存在 M 一處（內建 `GITHUB_TOKEN`） |
| C2 每次全掃，不做增量 | idempotent。漏通知一次只是延遲，下次任何 P 改版或每日排程就補上 |
| 只收 public、未封存、非 fork 的 repo | 公開清單列 private repo 會洩漏名稱與描述，而且別人也裝不起來 |
| 來源用 `{"source":"github"}`、不鎖版本 | 使用者拿預設分支最新版；不需要 SSH 金鑰 |
| C2 沒有 push 觸發 | **防遞迴**。另外 `GITHUB_TOKEN` 的 commit 本來就不觸發 workflow，雙重保險 |

### 憑證

| 名稱 | 存在哪 | 用途 |
|---|---|---|
| `GITHUB_TOKEN` | Actions 內建 | C2 讀 org 的 public repo、push 回 M |
| `MARKETPLACE_DISPATCH_TOKEN` | **org 層級的 Actions secret** | C1 對 M 發 `repository_dispatch` |

`MARKETPLACE_DISPATCH_TOKEN` 是 fine-grained personal access token：

- Resource owner：本 org
- Repository access：**Only select repositories → `<org>/marketplace`**
- Permissions：**Contents: Read and write**（`repository_dispatch` 需要的最小權限）
- 設成 org secret（org Settings → Secrets and variables → Actions → New organization secret），
  Repository access 選 All repositories

token 過期時 C1 會在 plugin repo 那邊明確失敗（HTTP 401），清單則由每日排程照常更新。

## 疑難排解

| 症狀 | 原因 |
|---|---|
| plugin 沒出現在清單 | 不在本 org／不是 public／沒有 `.claude-plugin/plugin.json`／名稱不合規（看 C2 的 warning） |
| C1 失敗：token 是空的 | repo 不在本 org，或呼叫端沒寫 `secrets: inherit` |
| C1 失敗：HTTP 401 | token 過期，重建後更新 org secret |
| C1 失敗：HTTP 403／404 | token 沒有 `<org>/marketplace` 的 Contents 寫入權限 |
| 改了 repo 名稱／visibility 或封存，清單沒更新 | 這些不產生 commit。在 P 手動跑 workflow、在 M 跑 `regenerate.yml`，或等排程 |
| 清單裡有但裝不起來 | plugin repo 被改成 private |
