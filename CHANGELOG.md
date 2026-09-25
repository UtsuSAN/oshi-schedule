# Changelog

このファイルは利用者が確認できる変更を記録します。

## [0.1.0] - 2026-09-25

### Added

- 日本時間を使った今日、今週、月間、日別、イベント詳細の予定閲覧
- Artist、Event、Appearance、Sourceのローカル管理画面
- 手動の投稿本文取り込み、ルールベースParser、ImportCandidateの確認・編集・承認・却下
- Candidate承認前の重複確認と、Event・Appearance・Sourceの一括登録
- CLIからの本文、UTF-8ファイル、JSON配列の取り込みとdry-run
- 投稿URL、投稿元ID、入力ハッシュによる二重取り込み防止
- Google Calendar予定作成リンクとICS出力
- 架空イベント5件を作る日付相対seed

### Security

- 管理画面に認証はなく、現リリースは127.0.0.1へbindしたローカル利用を前提とする。FastAPIバックエンドをインターネットへ公開しないこと。
