# 推し活イベント予定 — Sites source mirror

このフォルダーは、ChatGPT Sites の読み取り専用イベントビューアーのソースミラーです。ローカルCodexで編集しやすいよう、アプリ本体とは分けています。

## ローカルで開く

リポジトリのルートから次を実行します。

```powershell
git fetch origin codex/sites-local-editor
git switch --track -c codex/sites-local-editor origin/codex/sites-local-editor
```

その後、`sites/oshi-schedule` フォルダーをCodexまたはVS Codeで開きます。Nodeや追加パッケージは不要です。PowerShellで次を実行すると画面を確認できます。

```powershell
Set-Location sites/oshi-schedule
python -m http.server 4173 --directory dist
```

ブラウザーで `http://localhost:4173` を開きます。

## データと制約

- `dist/data/public_snapshot.json` が表示用データです。現在は個人情報や実イベントを含まない空Snapshotです。
- Snapshotの契約は `schema_version: "1.0"`、`timezone: "Asia/Tokyo"` です。日時は日本時間で扱います。
- データ更新は手動です。自動監視、収集、定期実行、通知は追加しません。
- 投稿本文、`source_text`、Candidate、ローカルDB、秘密情報、個人の予定をこの公開リポジトリへ入れないでください。
- 表示対象はPublic Snapshotの許可項目だけにし、外部リンクはHTTP(S)に限定してください。

## 実際のSitesへの反映

このGitHubフォルダーとChatGPT Sitesは自動同期されません。変更をブランチへpushしたあと、Sites連携済みのChatGPT Codexに対象ブランチとコミットを伝えて反映を依頼してください。Site側では検査後に新しい未公開バージョンとして保存できます。公開・デプロイは別の明示指示がある場合だけ行います。
