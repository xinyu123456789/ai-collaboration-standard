# 雙 AI 工程協作標準協定

> 版本 2.0.2｜工具中立｜Repository-first｜極簡完成訊號

## 0. 協定邊界

本協定適用於一位 Owner、工程師端 AI（Engineer）與審核端 AI（Reviewer）。
它的目的，是讓不同電腦、不同 LLM、沒有共同聊天記憶的兩端，仍能透過專案中的
報告安全交接。

程式只負責發布完成 JSON。以下工作一律不交給程式：

- 讀取或解釋對方的完成 JSON。
- 自動判斷下一位工作者。
- 自動授權下一輪。
- 自動判定 PASS、FIX_REQUIRED 或 HOLD。
- 自動 commit、push、merge、部署或刪除。
- 常駐監看目錄或自動啟動另一個 LLM。

兩端 AI 直接閱讀 JSON 與報告，按本協定行動。

## 1. 專案開始前設定

Owner 在每個新專案填妥以下內容，不得把空白項目交給 AI 猜測：

| 項目 | 專案設定 |
|---|---|
| 專案名稱 | `{{PROJECT_NAME}}` |
| 一句話目標 | `{{OBJECTIVE}}` |
| 明確非目標 | `{{NON_GOALS}}` |
| 完成條件 | `{{DONE_CRITERIA}}` |
| 規格優先順序 | `{{SOURCE_OF_TRUTH}}` |
| Engineer 負責範圍 | `{{ENGINEER_SCOPE}}` |
| Reviewer 負責範圍 | `{{REVIEWER_SCOPE}}` |
| 每輪大小或時間上限 | `{{ROUND_LIMIT}}` |
| 必跑驗證 | `{{QUALITY_COMMANDS}}` |
| 允許修改的路徑 | `{{ALLOWED_PATHS}}` |
| 排除的路徑 | `{{OUT_OF_SCOPE_PATHS}}` |
| commit 權限 | `{{COMMIT_POLICY}}` |
| push 權限 | 預設 Owner |
| main merge 權限 | 預設 Owner |
| 外部服務與成本權限 | `{{EXTERNAL_POLICY}}` |
| Owner 決策管道 | `{{OWNER_CHANNEL}}` |
| 暫停或取消條件 | `{{STOP_CONDITIONS}}` |

需要改變這些設定時，由 Owner 決定並更新正式文件。聊天中的推測不是授權。

## 2. 角色與權限

### 2.1 Owner

Owner 決定需求、優先順序、重大架構、公開契約、成本、外部操作、刪除、
push、main merge、專案暫停與取消。

### 2.2 Engineer

Engineer 只執行最新 Reviewer 報告明確指定的一輪工作。它負責：

- 先列本輪計畫與可勾選清單。
- 在授權範圍內實作。
- 執行驗證並保留實際結果。
- 寫完整工作報告。
- 把發布程式當作本輪最後一個動作。

Engineer 不得自行展開下一輪、改 Reviewer 報告、猜 Owner 意圖，或在發布完成
JSON 後繼續修改。

### 2.3 Reviewer

Reviewer 負責獨立檢查與引導，不替 Engineer 偷做產品實作。它負責：

- 先確認交接 JSON 有效，再完整閱讀工作報告。
- 檢查範圍、實作、測試、錯誤路徑、風險與 Git 邊界。
- 清楚寫出問題的證據、影響、原因、修改指南與驗收方式。
- 只安排一個可獨立驗證的下一輪。
- 寫完整審核報告。
- 把發布程式當作審核最後一個動作。

Reviewer 不得為了讓結果通過而直接修改產品程式，也不得在待 Owner 決定時發布
完成 JSON。

## 3. 唯一交接來源

聊天內容只協助理解，不是正式交接。兩端共同依賴以下檔案：

```text
docs/ai-collaboration/
├─ PROTOCOL.md
├─ reports/
│  ├─ engineer/
│  └─ reviewer/
└─ signals/

tools/ai-collaboration/
├─ publish_engineer_complete.py
└─ publish_reviewer_complete.py
```

每一輪建立新的報告與新的 JSON，不覆寫舊檔。

建議命名：

```text
ENG-0001_R01-topic.md
REV-0001_R01-topic.md
ENG-0001_R01-topic.engineer.complete.json
REV-0001_R01-topic.reviewer.complete.json
```

草稿可以使用 `.draft.md`；準備發布前先改成正式 `.md` 名稱。發布程式拒絕
`.draft.md`。

## 4. 一輪一停

同一時間只有一端可以工作：

```text
Reviewer 報告指定一輪
  → Reviewer 發布完成 JSON 並等待
  → Engineer 驗證 JSON、閱讀報告、完成一輪
  → Engineer 發布完成 JSON 並等待
  → Reviewer 驗證 JSON、閱讀報告、完成檢查
  → 產生下一份 Reviewer 報告或等待 Owner
```

一輪只包含一個能獨立驗證的目標。即使 Engineer 提早完成，也不能順便做下一輪。
即使 Reviewer 已經看出後續方向，也只能把它寫進下一輪指南，不能讓兩端同時工作。

第一輪由 Reviewer 建立 bootstrap 審核報告，列出第一個短輪次，再發布 Reviewer
完成 JSON。

## 5. Owner 決策停工

遇到以下事項時必須停下來：

- 需求或驗收條件有多種合理解釋。
- 需要更改公開介面、資料模型、架構或技術棧。
- 需要新增外部服務、成本、帳號、權限或敏感資料。
- 需要刪除、push、merge main、部署或改動他人範圍。
- 規格、報告與現況互相衝突。
- 選項會明顯影響時程、品質或專題方向。

停工說明必須包含：

1. 原本在做什麼、做到哪裡。
2. 發現了什麼證據。
3. 為什麼不能依現有授權決定。
4. 可行選項及各自影響。
5. Reviewer 的建議與理由。
6. Owner 需要回答的精確問題。
7. Owner 決定後如何恢復。

有待決事項時保留草稿，不呼叫發布程式。Owner 回覆後，必須等 Owner 明確說
「可以繼續」，才完成同一輪剩餘工作。

## 6. 報告規則

- 報告是兩端唯一完整對話管道，不能只寫結果。
- 所有修改指南都必須落在 Reviewer 報告。
- 所有實際變更與驗證證據都必須落在 Engineer 報告。
- 正式報告發布後不得修改、覆寫、改名或刪除。
- 報告有錯時，新建 correction report，說明取代哪一份，不改原檔。
- 每份報告最後只能給出一個下一步：另一端工作、等待 Owner，或專案停止。
- 不得在報告未完成時預先呼叫發布程式。
- Engineer 的「本輪規劃步驟」必須在修改產品檔案前寫定；開始執行後不得回頭
  修改，實際差異只能記入「問題、偏差與風險」。
- Engineer 必須把 Reviewer 指定的 checklist 原樣複製到工作報告；未完成項目
  保留 `[ ]` 並說明原因，不得刪除。

## 7. Engineer 工作報告範本

Engineer 每輪直接複製以下內容建立新的工作報告。第零節必須在修改任何產品檔案
前完成；開始執行後不得重寫，實際差異只能記入第五節。

```markdown
# Engineer Work Report｜{{ROUND_ID}} {{TOPIC}}

| 項目 | 內容 |
|---|---|
| 日期 | `{{DATE}}` |
| 輪次 | `{{ROUND_ID}}` |
| 狀態 | `COMPLETE` / `INCOMPLETE` / `BLOCKED` |
| 實際耗時 | `{{ELAPSED_TIME}}` |
| Branch | `{{BRANCH}}` |
| Base commit | `{{BASE_COMMIT}}` |
| Head commit | `{{HEAD_COMMIT_OR_UNCOMMITTED}}` |
| 對應 Reviewer 報告 | `{{REVIEW_REPORT_PATH_AND_SECTION}}` |
| 輪次上限 | `{{ROUND_LIMIT}}` |

---

## 〇、本輪規劃步驟

> 本節必須在修改任何產品檔案前寫定。
>
> 開始執行後，本節即凍結，不得因實際做法不同而回頭修改。所有差異一律如實記入
> 「五、問題、偏差與風險」。

| 規劃紀錄 | 內容 |
|---|---|
| 規劃完成時間 | `{{PLANNING_COMPLETED_AT}}` |
| 規劃時 HEAD | `{{PLANNING_HEAD}}` |
| 授權來源 | `{{REVIEW_REPORT_PATH_AND_SECTION}}` |

### 0.1 唯一目標與允許範圍

**唯一目標：** {{ONE_VERIFIABLE_OBJECTIVE}}

**允許新增／修改：**

- `{{ALLOWED_PATH}}`

**完成條件：**

- {{OBJECTIVE_DONE_CRITERION}}

### 0.2 執行步驟表

> 每一列都是可獨立驗證的最小動作。禁止只寫「實作某模組」、「補測試」或
> 「更新文件」。若無法用一句話說明怎麼知道做完，必須再拆小。

| # | 動作 | 產出檔案 | 完成判準 | 驗證方式 | 依賴 | 預估 |
|---:|---|---|---|---|---|---:|
| 1 | {{CONCRETE_ACTION}} | `{{PATH}}`（新增／修改） | {{OBJECTIVE_CRITERION}} | `{{COMMAND_OR_CHECK}}` | — | {{TIME}} |
| 2 | {{CONCRETE_ACTION}} | `{{PATH}}`（新增／修改） | {{OBJECTIVE_CRITERION}} | `{{COMMAND_OR_CHECK}}` | 1 | {{TIME}} |

**預估合計：** {{TOTAL_ESTIMATE}}

### 0.3 決策點

> 尚未核准的決策出現時立即停止，不自行套用預設，也不先做其他部分。

| 編號 | 事項 | 必須在何步前決定 | 現有授權或待問問題 | 未解時動作 |
|---|---|---:|---|---|
| P-1 | {{DECISION_POINT_OR_NONE}} | {{STEP}} | {{AUTHORITY_OR_QUESTION}} | {{STOP_ACTION}} |

### 0.4 風險步驟與退路

| 編號 | 風險 | 影響步驟 | 預防／偵測方式 | 失敗時退路或停止條件 |
|---|---|---:|---|---|
| R-1 | {{RISK}} | {{STEP}} | {{PREVENTION_OR_PROBE}} | {{FALLBACK_OR_STOP}} |

### 0.5 本輪明確不做

- 不修改 `{{PROTECTED_PATH}}`。
- 不開始 `{{NEXT_ROUND_OR_FEATURE}}`。
- 不執行未授權的 commit、push、merge、部署、刪除或外部寫入。
- {{OTHER_EXPLICIT_NON_GOAL}}

---

## 一、Reviewer Checklist

> 將來源 Reviewer 報告的當輪 checklist **原樣複製**到下方。執行中只更新
> `[ ]`／`[x]`；不得改寫、重排或刪除項目。未完成項保留 `[ ]` 並說明原因。

- [ ] 1. {{COPY_FROM_REVIEW_REPORT_VERBATIM}}
- [ ] 2. {{COPY_FROM_REVIEW_REPORT_VERBATIM}}

**完成統計：** {{COMPLETED_COUNT}} / {{TOTAL_COUNT}}

---

## 二、本輪變更

### 2.1 本輪新增

| 檔案／symbol | 目的與實際內容 |
|---|---|
| `{{PATH_OR_SYMBOL}}` | {{CHANGE_AND_REASON}} |

### 2.2 本輪修改

| 檔案／symbol | 修改前 | 修改後 | 原因 |
|---|---|---|---|
| `{{PATH_OR_SYMBOL}}` | {{BEFORE}} | {{AFTER}} | {{REASON}} |

### 2.3 本輪刪除

沒有則明寫「無」。有則列出 Owner／Reviewer 授權來源與可恢復性。

### 2.4 本輪開始前已存在

列出進入本輪前就存在的未提交變更或檔案，避免把他人或前輪成果算成本輪交付。

### 2.5 他人同時修改

沒有則明寫「無」。有則列出路徑、發現時間、影響與停止／協調方式。

### 2.6 未觸碰與受保護項目

列出 Reviewer 指定不得改動的路徑，並說明如何確認沒有漂移。

---

## 三、驗證證據

每項都列出完整命令、exit code、關鍵輸出與判讀。未執行時明寫「未驗證」及原因。
搜尋無結果時，要區分「無符合項」與「命令執行失敗」。

### 3.1 必跑驗證

```console
$ {{COMMAND}}
{{KEY_OUTPUT}}
exit={{EXIT_CODE}}
```

**判讀：** {{INTERPRETATION}}

### 3.2 正向、負向與回歸案例

| 案例 | 期望 | 實際 | 結果 |
|---|---|---|---|
| {{CASE}} | {{EXPECTED}} | {{ACTUAL}} | PASS／FAIL／未驗證 |

---

## 四、Git 證據

```console
$ git branch --show-current
{{BRANCH}}

$ git rev-parse HEAD
{{HEAD}}

$ git status --short
{{STATUS_OUTPUT_OR_EMPTY}}

$ git diff --stat
{{DIFF_STAT}}
```

| 項目 | 狀態 |
|---|---|
| Index／staged | {{STATE}} |
| Commit | {{NOT_CREATED_OR_SHA_AND_AUTHORITY}} |
| Push | {{NOT_PERFORMED_OR_AUTHORITY}} |
| Main merge | {{NOT_PERFORMED_OR_AUTHORITY}} |

---

## 五、問題、偏差與風險

### 5.1 規劃與實際差異

| 規劃步驟 | 原計畫 | 實際 | 原因 | 影響 |
|---:|---|---|---|---|
| {{STEP}} | {{PLAN}} | {{ACTUAL}} | {{REASON}} | {{IMPACT}} |

沒有差異也要明寫「無」。

### 5.2 失敗嘗試與未完成

列出失敗命令、未完成 checklist、未驗證項目及原因，不得隱藏。

### 5.3 範圍外變更

沒有則明寫「無」。若存在，列出路徑、原因、授權狀態與處置。

### 5.4 工時偏差與已知限制

比較各步驟預估與實際；說明殘留限制及對下一輪的影響。

---

## 六、待決事項

沒有則明寫「無」。

若需要 Owner 決定，必須交代原工作、進度、證據、不能自行決定的原因、選項與影響、
建議、精確問題及恢復方式；保留草稿並停止，不呼叫完成發布程式。

---

## 七、給 Reviewer 的重現步驟

從 repository 當前狀態開始逐條列出，讓 Reviewer 不需詢問即可重現：

1. {{REPRODUCTION_STEP}}
2. {{REPRODUCTION_STEP}}

---

## 八、停止聲明

- 本輪狀態：{{COMPLETE_OR_INCOMPLETE_OR_BLOCKED}}
- Reviewer checklist：{{COMPLETED_COUNT}} / {{TOTAL_COUNT}}
- 下一輪：**尚未開始**
- 未授權的 commit／push／merge／部署／刪除：**未執行**
- 本報告發布後不再修改；若需更正，新增 correction report，不覆寫本檔。
- 發布程式成功後立即等待 Reviewer。
```

規劃不是成果展示。若實際執行順序、方法或工時與原計畫不同，不得回頭修飾第零節，
必須如實寫入第五節。

## 8. Reviewer 審核報告範本

```markdown
# Review Report｜R01 主題

| 項目 | 內容 |
|---|---|
| 檢查時間 | ... |
| 對應 Engineer 報告 | ... |
| 檢查基線 | branch、base、head |
| 結論 | PASS／FIX_REQUIRED／HOLD |
| 下一個允許輪次 | 輪次 ID 或「無」 |

## 1. 結論先行

先說明 outcome、原因，以及下一端目前能不能開始。

## 2. 檢查範圍、輸入與 baseline

列出已檢查、未檢查、報告雜湊、實際檔案、branch、base/head 與工作樹狀態。

## 3. Findings

每個問題包含編號、嚴重度、證據、影響、根因、修改指南與驗收方式。

## 4. Reviewer 獨立驗證

列出實際命令、exit code、額外案例與結果。

## 5. 下一輪精確 Scope

列出唯一目標、允許新增／修改、必須保持不變及明確禁止。

## 6. 修改指南與 PASS 條件

依正確順序提供具體方法、負向案例、驗收命令與停止條件。

## 7. 待 Owner 決定事項

交代完整前因後果、選項、影響與建議；仍待決時停止且不發布 JSON。

## 8. Engineer 當輪 Checklist

- [ ] 1. 前置基線與來源報告確認。
- [ ] 2. 建立新工作報告，先寫完整第零節規劃再動產品檔案。
- [ ] 3. 一個可獨立驗收的實作或修正步驟。
- [ ] 4. 必要的正向、負向與回歸驗證。
- [ ] 5. 最終 scope、Git 與報告完整性核對。
- [ ] 6. 呼叫發布程式並立即等待。

## 9. 工作報告必填與停止條件

說明 Engineer 報告必須提供的特殊證據，以及遇到哪些情況必須停止。

## 10. 下一個唯一動作

明確寫 Engineer 可以開始哪一輪、應等待 Owner，或專案停止。
```

Reviewer 的 checklist 是 Engineer 的授權邊界，不是 Engineer 的執行計畫替代品。
Engineer 必須先原樣複製 checklist，再依依賴關係拆成第零節的七欄步驟表。

checklist 必須有順序、能勾選且能驗收；不能只列抽象結果。報告寫不清楚本身就是
finding，Reviewer 應要求 Engineer 修正溝通品質，避免同一錯誤反覆發生。

## 9. 發布完成 JSON

來源端只有在以下條件全部成立時才能呼叫發布程式：

- 報告內容已完全寫完並重新讀過。
- 沒有待 Owner 決定事項。
- 報告已使用正式 `.md` 名稱。
- 本輪不會再修改任何檔案。
- 即將進入等待。

工程師端最後呼叫：

```text
python3 tools/ai-collaboration/publish_engineer_complete.py \
  --project-root . \
  --report docs/ai-collaboration/reports/engineer/<REPORT>.md
```

審核端最後呼叫：

```text
python3 tools/ai-collaboration/publish_reviewer_complete.py \
  --project-root . \
  --report docs/ai-collaboration/reports/reviewer/<REPORT>.md
```

發布程式執行順序固定：

1. 找到自己的報告。
2. 計算報告 SHA-256。
3. 準備完整 JSON。
4. 將報告設為唯讀並再次確認內容未變。
5. 最後才讓正式 `*.complete.json` 路徑出現。

來源端不得手寫、補寫或修改 JSON。exit code 0 後立即等待。

## 10. JSON 格式

```json
{
  "schema_version": "ai-collaboration-completion/v1",
  "source": "reviewer",
  "report_path": "docs/ai-collaboration/reports/reviewer/REV-0001_R01.md",
  "report_sha256": "<SHA-256>",
  "created_at": "2026-08-04T08:30:00Z",
  "complete": true
}
```

欄位只有：

| 欄位 | 用途 |
|---|---|
| `schema_version` | 辨識格式版本 |
| `source` | `engineer` 或 `reviewer` |
| `report_path` | 從專案根目錄定位正式報告 |
| `report_sha256` | 發現報告發布後遭修改 |
| `created_at` | UTC 發布時間 |
| `complete` | 只有布林值 `true` 才成立 |

`complete` 是最後一個欄位。JSON 不放 outcome、next_actor 或 authorized_round；
這些人類語意只存在報告中，避免程式接管協作判斷。

## 11. 目的端接手規則

目的端可以自行查看 signal 目錄，也可以由人提醒，但不使用本套件以外的自動讀取
程式。看到 JSON 檔名時仍不能直接開始工作。

目的端必須：

1. 直接讀取完整 JSON。
2. 確認 JSON 可解析。
3. 確認 `complete` 的型別是 boolean 且值為 `true`；字串 `"true"` 不算。
4. 確認 `source` 是正在等待的對方角色。
5. 依 `report_path` 開啟正式報告。
6. 用作業系統既有工具計算報告 SHA-256，確認與 JSON 相同。
7. 完整讀取報告與相關實際檔案。
8. 只依報告的「下一個唯一動作」決定開始、等待或停止。

任一步失敗都不能工作。目的端應把異常告訴 Owner，不得自行修 JSON 或報告。

## 12. 報告唯讀的實際界線

發布程式會移除報告寫入權限，避免 LLM 完成後順手繼續修改。相同系統帳號仍可能
刻意把權限改回，因此這不是對惡意行為的絕對防護。

本協定使用兩層保障：

- 唯讀權限防止意外修改。
- JSON 中的 SHA-256 讓目的端發現內容曾改變。

任何角色都不得把權限改回來修舊報告。需要更正時新增 correction report，發布
新的 JSON，並在新報告清楚指向舊報告。

## 13. Git 與外部操作

完成 JSON 只代表「這份報告可以讀」，不代表：

- 可以 commit。
- 可以 push。
- 可以 merge main。
- 可以部署。
- 可以刪除檔案、branch 或資料。
- 可以呼叫付費或有副作用的外部服務。

這些權限必須由 Owner 在專案設定或當次決定中逐項授權，不能互相推定。

## 14. 兩端啟動提示詞

### Engineer

```text
你是 Engineer AI。完整閱讀 PROTOCOL、正式規格、最新有效 Reviewer JSON，
以及它指向的完整 Reviewer 報告。不能只因檔案存在就開工；必須確認
complete 是 boolean true、source 正確、report_path 存在且 SHA-256 相同。

只執行報告明確指定的一輪。先把 Reviewer checklist 原樣複製到新工作報告，
並在任何產品修改前寫完且凍結第零節：唯一目標、七欄執行步驟表、決策點、
風險與退路、明確不做。開始執行後不得修改第零節，差異只能記入偏差章節。
之後才可實作與驗證。
需要 Owner 決定時停止，不發布完成 JSON。全部完成後，發布程式是最後一個動作；
成功後立即等待，不開始下一輪，也不修改已發布報告。
```

### Reviewer

```text
你是 Reviewer AI。完整閱讀 PROTOCOL、正式規格、最新有效 Engineer JSON，
以及它指向的完整 Engineer 報告。不能只因檔案存在就檢查；必須確認
complete 是 boolean true、source 正確、report_path 存在且 SHA-256 相同。

獨立檢查實際檔案與驗證結果，在審核報告中寫完整 finding、修改指南和下一輪
checklist，不直接替 Engineer 改產品程式。需要 Owner 決定時停止並保留草稿，
不發布完成 JSON。全部完成後，發布程式是最後一個動作；成功後立即等待。
```

## 15. 啟動驗收清單

- [ ] Owner 已填完專案設定，沒有未處理 placeholder。
- [ ] 兩端 AI 已完整閱讀協定與自己的啟動提示詞。
- [ ] 報告與 signals 目錄已事先建立。
- [ ] 專案只放兩支發布程式，沒有訊號讀取器或 watcher。
- [ ] 兩端知道「檔案存在」不等於完成。
- [ ] 兩端只接受 boolean `complete: true`。
- [ ] 兩端會依 `report_path` 讀報告並核對 SHA-256。
- [ ] Engineer 知道每輪直接複製本協定 §7 建立新的工作報告。
- [ ] Engineer 知道先原樣複製 Reviewer checklist，再寫自己的七欄執行步驟表。
- [ ] Engineer 知道第零節須在產品改動前凍結，差異只能寫入偏差章節。
- [ ] 兩端知道正式報告不能修改，只能新增 correction report。
- [ ] Owner 決策停工與恢復條件已確認。
- [ ] commit、push、merge、部署與刪除權限已分別寫清楚。
- [ ] Reviewer 已用 bootstrap 報告只解鎖第一輪。

任一項未成立時，只能修正協作環境，不開始產品工作。

## 16. 專案暫停或取消

Owner 宣布暫停或取消後，兩端立即停止新工作。保留報告、JSON 與 Git 歷史供後續
稽核；除非 Owner 明確指定，不自動刪 branch、不 reset、不 push、不 merge。

## 17. 版本紀錄

| 版本 | 日期 | 內容 |
|---|---|---|
| 2.0.2 | 2026-08-04 | 將 Engineer 工作報告範本完整內嵌於本協定 §7，不再維護獨立範本檔。 |
| 2.0.1 | 2026-08-04 | 依既有成熟工作報告恢復執行前七欄步驟表、決策點、風險退路、明確不做與八節證據格式。 |
| 2.0.0 | 2026-08-04 | 精簡為兩支只負責發布 JSON 的程式；移除訊號讀取、watcher、Git 狀態機與自動授權。 |
