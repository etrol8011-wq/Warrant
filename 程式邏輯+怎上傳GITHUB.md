# 權證雷達 Web 版 — 程式邏輯 + GitHub 上傳教學

對應 repo：https://github.com/etrol8011-wq/Warrant
對應網址：https://warrant-txy4.onrender.com

---

## 一、程式邏輯

### 1. 跟桌面版的關係

這支網頁版是從桌面版 `搜尋.py`（Tkinter）移植來的，**查詢/計算/篩選的邏輯完全相同**，
只是把 Tkinter 介面換成瀏覽器介面，這樣手機/人在外面也能用。

### 2. 檔案結構

```
web/
├─ core.py          查詢、正規化、篩選條件計算 — 跟桌面版同一套邏輯，純 Python 無 GUI
├─ app.py           Flask 後端：網址路由、登入保護、把 core.py 包成 API
├─ templates/
│   ├─ login.html   登入頁
│   └─ index.html   主頁面（骨架，實際內容由 app.js 動態畫）
├─ static/
│   ├─ style.css    外觀（深色主題，手機響應式）
│   └─ app.js       前端邏輯：打 API、畫表格、篩選條件設定視窗…
├─ certs/
│   └─ twca_chain.pem   元大權證網的憑證鏈（解決 Render SSL 驗證問題用，見下方說明）
├─ data/            執行期間自動產生，存自選股/篩選條件（不會進 git，見 .gitignore）
├─ requirements.txt Python 套件清單
├─ render.yaml      Render 部署設定（Build/Start 指令、環境變數宣告）
└─ README.md        完整部署步驟（英文技術細節較多，這份文件是中文摘要+GitHub操作）
```

### 3. 資料流程（使用者查一檔股票時）

1. 瀏覽器呼叫 `GET /api/quote?code=2379&type=認購`
2. `app.py` 呼叫 `core.WarrantAPI.fetch_all()` → POST 到元大權證網 API
   （`https://www.warrantwin.com.tw/eyuanta/ws/GetWarData.ashx`），自動翻頁抓全部
3. 每一筆原始資料丟進 `core.normalize()`：算出差槓比、價差比、實質槓桿、
   Black-Scholes 合理價、價內外% 等所有欄位
4. 丟進 `core.eval_all_conds()`：用目前的 5 組篩選條件（差槓比/江大/自訂3~5）
   各自判斷 True/False，存在每筆資料的 `_conds` 欄位
5. `core.calc_iv_stats()`：算同類IV中位數、IV偏離%、IV評價
6. 整包 JSON 回給前端，`app.js` 依照目前開啟的快速篩選按鈕做 AND 篩選、排序、畫表格

> 小提醒（跟桌面版一樣的既有特性，不是網頁版新增的）：
> 「自訂3/4/5」如果沒設規則，預設一律算「通過」，所以沒自訂規則時表格常常整排都是
> 金色（表示通過2個以上條件）。這是桌面版原本就有的行為，等你把自訂3/4/5也設定規則
> 後就會正常分流。

### 4. 篩選條件系統

- 5 組條件，每組可設最多 8 條規則（`<`、`<=`、`>`、`>=`、`between`）
- 同一組內的規則是 **AND**（全部要符合才算通過這組）
- 快速篩選列上多選幾個條件按鈕 = 這幾組條件也是 **AND**（全部要通過）
- 條件存在 `data/conditions.json`；自選股存在 `data/watchlist.json`

### 5. 登入保護

`app.py` 用 Flask session + 環境變數 `APP_PASSWORD` 做單一共用密碼保護，
沒設 `APP_PASSWORD` 時（例如本機測試）就不會要求登入。

### 6. 已知問題與修法記錄

| 問題 | 原因 | 修法 |
|---|---|---|
| Render 上查詢回「查無資料」| Render 的 Linux 環境 OpenSSL 對元大權證網（TWCA 憑證）驗證較嚴格，丟 SSL 錯誤 | 在 `core.py` 釘選 `certs/twca_chain.pem` 這條憑證鏈驗證；真的還是不行可設環境變數 `WARRANT_INSECURE_TLS=1` 當最後手段跳過驗證 |
| 股票（個股）原始保證金查不到 | 期交所 `SingleStockFuturesMargining` 這支 API 目前實際回傳 CSV 不是文件說的 JSON | `core.py` 的 `MarginAPI._ensure_loaded()` 改成先試 JSON、失敗自動改用 CSV 解析 |
| 手機打完代號沒地方按確定 | 原本只靠輸入框按 Enter 送出，手機鍵盤不一定方便觸發 | `templates/index.html` 的自選股輸入框旁加一顆「搜尋」按鈕（`static/style.css` 同步調整排版），點按鈕跟按 Enter 效果一樣 |

`app.py` 裡還留了一個 `/api/debug_probe?code=xxxx` 診斷用端點，直接把元大權證網 API
的原始回應印出來，確認整個查詢流程穩定後可以刪掉（非必要留著也無妨，反正有登入保護）。

### 7. 資料持久化的限制

Render 免費方案磁碟不是永久的，**重新部署或閒置太久被喚醒後，`data/` 下的
自選股、篩選條件設定可能會被清空**。因為只是幾檔代號和篩選規則，重新設定成本很低，
目前先接受這個限制，不做額外的資料庫整合（避免過度工程化）。

---

## 二、怎麼上傳 GitHub（之後要改程式碼時照這個流程）

你的 repo 在 https://github.com/etrol8011-wq/Warrant ，Render 有連著這個 repo，
**只要 repo 的 main 分支有新的 commit，Render 就會自動重新部署**，不用手動去 Render 按什麼。

### 情境 A：修改既有檔案（例如改 app.py、core.py）

1. 打開 https://github.com/etrol8011-wq/Warrant
2. 點進你要改的檔案（例如 `app.py`）
3. 點右上角 **鉛筆圖示**（Edit this file）
4. 把內容改好（或整個貼上新版內容覆蓋掉）
5. 捲到最下面，確認選的是「**Commit directly to the main branch**」
6. 點綠色的 **Commit changes** 按鈕
7. 等 1-2 分鐘，Render 會自動偵測到新 commit 開始重新部署

### 情境 B：新增一個檔案（例如新增 `certs/xxx.pem`）

1. 進到 repo 首頁，點 **Add file → Create new file**（純文字）
   或 **Add file → Upload files**（直接拖檔案上傳，適合二進位檔或整批檔案）
2. 如果用 Create new file，在檔名欄位直接打完整路徑（例如 `certs/xxx.pem`），
   GitHub 會自動幫你建好 `certs` 這個資料夾
3. 下面一樣選「Commit directly to the main branch」→ Commit

### 情境 C：想先在自己電腦測試，確定沒問題再上傳

```bash
cd 權證搜尋器/web
pip install -r requirements.txt
python app.py
```
開瀏覽器到 http://127.0.0.1:5000 測試。確定沒問題，再照情境 A/B 把改好的檔案
內容貼到 GitHub 網頁版。

### 怎麼確認 Render 真的部署成功了

1. 到 https://dashboard.render.com 登入
2. 點進 `warrant-txy4`（或你命名的服務）
3. 上面會有部署進度（Building → Deploying → Live），或在 **Events** / **Logs**
   分頁看有沒有紅字錯誤

### 環境變數在哪裡改

Render 後台 → 該服務 → **Environment** 分頁：
- `APP_PASSWORD`：網頁登入密碼
- `SECRET_KEY`：Flask session 加密用，留給 Render 自動產生就好
- `WARRANT_INSECURE_TLS`：只有在憑證釘選那招也救不回來時才設成 `1`（最後手段）

改完環境變數記得按 **Save Changes**，Render 會自動重啟服務套用新設定
（這個不需要 commit，跟程式碼上傳是分開的）。
