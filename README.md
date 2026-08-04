# AI Collaboration Standard

這是一個可整包複製的雙 AI 工程協作標準。它只提供兩支小型完成發布程式，
不提供訊號讀取器、watcher、Git 管理器或自動工作流程。

## 資料夾內容

```text
ai-collaboration-standard/
├─ README.md
├─ AI_COLLABORATION_PROTOCOL.md
└─ tools/
   ├─ publish_engineer_complete.py
   └─ publish_reviewer_complete.py
```

只需要 Git、Python 3.11 以上與 UTF-8 檔案系統。程式不需要第三方套件、
LLM SDK 或網路。

## 兩支程式只做什麼

來源端完成一份報告後，呼叫自己的發布程式。程式只會：

1. 確認指定報告存在於該角色的報告目錄。
2. 讀取報告並計算 SHA-256。
3. 移除報告的寫入權限，避免完成後順手修改。
4. 最後才建立一個 `*.complete.json`。

程式不會讀取任何完成 JSON，也不會判斷誰可以開始哪一輪。

## 導入新專案

將本文件與兩支程式複製成：

```text
<PROJECT>/
├─ docs/ai-collaboration/
│  ├─ PROTOCOL.md
│  ├─ reports/
│  │  ├─ engineer/
│  │  └─ reviewer/
│  └─ signals/
└─ tools/ai-collaboration/
   ├─ publish_engineer_complete.py
   └─ publish_reviewer_complete.py
```

`PROTOCOL.md` 就是本套件的 `AI_COLLABORATION_PROTOCOL.md`。開始前由 Owner
填妥其中的專案設定，並讓兩端 AI 完整閱讀。Engineer 每輪依協定 §7 直接建立
新的工作報告；在修改產品檔案前，必須先寫定其中的完整執行步驟表、決策點、
風險退路與明確不做。

## 來源端的最後一個動作

工程師端：

```text
python3 tools/ai-collaboration/publish_engineer_complete.py \
  --project-root . \
  --report docs/ai-collaboration/reports/engineer/<REPORT>.md
```

審核端：

```text
python3 tools/ai-collaboration/publish_reviewer_complete.py \
  --project-root . \
  --report docs/ai-collaboration/reports/reviewer/<REPORT>.md
```

Windows 可把 `python3` 換成 `py -3`。只有 exit code 0 才代表發布成功；
成功後來源端立即等待，不再修改任何檔案。

## 目的端如何接手

不使用專用程式讀訊號。目的端直接打開新 JSON，依序確認：

1. JSON 能完整解析。
2. `complete` 存在，而且是布林值 `true`。
3. `source` 是預期角色。
4. `report_path` 指向存在的報告。
5. 報告 SHA-256 與 `report_sha256` 相同。
6. 完整讀完報告後，才依報告中的唯一下一步行動。

看到檔名建立不等於可以開工。JSON 不完整、`complete` 不是 `true`、雜湊不符，
或報告仍有待 Owner 決定事項時，都必須等待。

## JSON 範例

```json
{
  "schema_version": "ai-collaboration-completion/v1",
  "source": "engineer",
  "report_path": "docs/ai-collaboration/reports/engineer/ENG-0001_R01.md",
  "report_sha256": "<64 個十六進位字元>",
  "created_at": "2026-08-04T08:00:00Z",
  "complete": true
}
```

`complete` 固定為最後一個欄位。訊號只負責指向一份已封存報告，不包含工作授權；
工作內容、修改指南與下一步都寫在報告裡。
