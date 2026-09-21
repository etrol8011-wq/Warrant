# 權證雷達 Web 版

從桌面版 `搜尋.py`（Tkinter）移植的網頁版，核心查詢/篩選邏輯完全相同（`core.py`
就是把桌面版的 `WarrantAPI`、`MarginAPI`、`normalize()`、篩選條件系統原封不動搬過來），
差別只在介面改成瀏覽器可用、手機也能操作。

## 功能對照

| 桌面版功能 | 網頁版 |
|---|---|
| 自選股（新增/刪除/自動查名稱）| ✅ 存在伺服器 `data/watchlist.json` |
| 認購/認售/全部 切換 | ✅ |
| 5 組快速篩選條件（差槓比、江大…）| ✅ 存在伺服器 `data/conditions.json` |
| 篩選條件設定（規則編輯）| ✅ Modal 視窗編輯 |
| 欄位顯示設定 | ✅（存在瀏覽器 localStorage，各裝置各自設定；**不含**桌面版的欄位拖曳排序，只有顯示/隱藏）|
| 股期判斷 + 原始保證金 | ✅ |
| 表格排序、代碼點擊開元大權證網 | ✅ |
| 「程式說明」匯出 txt | ❌ 未搬（桌面限定功能，網頁版用不到）|

## 本機測試

```bash
cd 權證搜尋器/web
pip install -r requirements.txt
python app.py
```

開瀏覽器到 http://127.0.0.1:5000 。本機測試沒設 `APP_PASSWORD` 環境變數的話不會要求登入。

## 部署到 Render

1. **把 `web` 這個資料夾單獨建成一個 GitHub repo**（不要連桌面版 `搜尋.py` 一起放進同一個 repo，
   兩者用途不同、也不需要放在一起部署）：
   ```bash
   cd 權證搜尋器/web
   git init
   git add .
   git commit -m "init: 權證雷達 web 版"
   gh repo create warrant-radar --private --source=. --remote=origin --push
   ```
   （若沒有安裝 `gh`，也可以到 https://github.com/new 手動建一個 repo，
   再 `git remote add origin <你的repo網址>` 後 `git push -u origin main`）

2. 到 https://render.com 用 GitHub 帳號登入 → New → Web Service → 選剛剛的 repo。
   Render 會自動偵測到 `render.yaml`，套用以下設定：
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`

3. 在 Render 後台的 Environment 分頁設定環境變數：
   - `APP_PASSWORD`：你要用的登入密碼（自己選一組，不要用桌面版的任何帳密）
   - `SECRET_KEY`：留白讓 Render 自動產生即可（render.yaml 已設定 `generateValue: true`）

4. 部署完成後 Render 會給一個 `https://xxx.onrender.com` 網址，手機瀏覽器打開、
   輸入密碼就能用。建議把網址加到手機瀏覽器「加入主畫面」，開起來會很像 App。

## 重要限制

- **免費方案沒有持久化磁碟**：`data/watchlist.json`、`data/conditions.json` 是存在
  伺服器本機檔案系統，免費方案重新部署（或閒置太久被喚醒）時磁碟會重置，自選股
  和篩選條件設定可能會被清空。因為只是幾檔股票代號和篩選規則，重新設定成本很低，
  暫時先接受這個限制；之後如果想要「不會消失」，可以：
  - 升級 Render 付費方案掛 Persistent Disk，或
  - 改用 Railway（有免費的 Volume 可掛載），或
  - 把資料改存到外部資料庫（如 Supabase/Neon 的免費 Postgres）。
  目前先不做，避免過度工程化。
- 密碼保護是單一組共用密碼、簡易 session 機制，**不是**帳號系統，適合個人使用，
  不要拿來放需要多人權限分級的用途。
- 這支程式會即時打元大權證網、期交所的公開 API，跟桌面版行為一致，沒有另外快取，
  所以查詢速度取決於對方 API 回應時間。
