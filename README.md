# 推し活スケジュール

SNSなどに散らばったライブ・イベント告知を、確認可能なCandidateフローを通して予定表へ整理するセルフホスト型Webアプリです。告知本文を手動で取り込み、内容を確認・修正してから予定へ反映します。

> **重要：管理画面に認証機能はありません。FastAPIバックエンドを現状のままインターネットへ公開しないでください。** 投稿本文や予定を含むローカルデータを扱います。現バージョンは自分のPC上での利用を前提としています。

## 概要

このプロジェクトは、ローカルで予定を閲覧・管理し、手動入力した告知から確認待ち候補を作るMVPです。X APIへの接続や自動取得はせず、Parserの結果を人が確認してからEventへ登録します。

## 画面・機能紹介

現在、公開用スクリーンショットは同梱していません。以下の画面をローカルサーバーで確認できます。

- 今日、今週、月間カレンダー、日別予定、イベント詳細
- Artist、Event、出演情報、Sourceの管理
- 投稿本文の取り込み、Candidateの確認・編集・承認・却下
- Google Calendarの予定作成リンクとICSファイル

## 主な機能

- 日本時間での予定閲覧とArtist絞り込み
- EventとArtistごとのAppearanceを分けた管理
- ルールベースParserによる告知本文の補助解析
- 重複取り込みの判定と人によるCandidate確認
- CLIからの単一投稿、ファイル、JSON配列の手動取り込み
- Google CalendarリンクとICSの生成。Google APIやOAuthは使用しません
- 架空データを使う日付相対のseed

## 設計方針

- 取り込んだ情報はImportCandidateとして保存し、承認されるまでEventへ反映しません。
- Parserの信頼度は確認の手掛かりです。自動承認や自動更新には使用しません。
- HTML画面とデータアクセス・業務処理を分け、将来のJSON APIからサービス層を再利用できる構造にしています。
- デモデータは架空の内容で、開催日をseed実行日の日本時間に合わせて作ります。

## v0.1.0の範囲

対応済み：

- 予定閲覧とArtist絞り込み
- Artist、Event、Appearance、Sourceの管理
- 手動の投稿本文ParserとCandidate確認フロー
- 手動取り込みCLIと二重取り込み防止
- Google CalendarリンクとICS

未対応：

- X API、自動監視、スケジューラー、通知
- 画像解析、OCR、AI解析
- 管理画面の認証
- インターネット向けの安全な本番配備
- Sites連携、公開用JSON API

公開画面のHTMLルートも、現在の構成ではこのFastAPIアプリから配信されます。認証のない管理ルートと同じバックエンド上にあるため、公開HTMLだけを使う場合もアプリ全体をインターネットへ公開しないでください。

## 必要環境

- Python 3.11以上
- Git
- Windows PowerShell（以下の手順）

## インストールと初期化

GitHubページのCodeメニューからHTTPS Clone URLをコピーします。次の最初の行を実行するとURLを尋ねるので、コピーした値を貼り付けてください。

    $RepositoryUrl = Read-Host "GitHub HTTPS Clone URL"
    git clone $RepositoryUrl
    $RepositoryDirectory = ($RepositoryUrl.TrimEnd('/') -split '/')[-1] -replace '\.git$', ''
    Set-Location $RepositoryDirectory
    python --version
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    python -m pip install -e ".[dev]"
    Copy-Item .env.example .env
    .\.venv\Scripts\python.exe -m alembic upgrade head
    .\.venv\Scripts\python.exe -X utf8 scripts/seed.py

PowerShellの実行ポリシーで仮想環境の有効化が拒否された場合は、有効化を省略し、後続コマンドのpythonを .\.venv\Scripts\python.exe に置き換えてください。例えば依存インストールは次の通りです。

    .\.venv\Scripts\python.exe -m pip install -e ".[dev]"

.env.exampleはローカルSQLiteとlocalhost用の無秘密情報設定です。コピーした.envを必要に応じて編集してください。設定項目は「環境設定」を参照してください。

## 起動

    .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

ブラウザーで http://127.0.0.1:8000/ を開きます。--host 127.0.0.1を維持してください。0.0.0.0など全ネットワークインターフェースで待ち受ける設定に変更しないでください。

主なルート：

- / または /today：今日
- /week：月曜日から日曜日までの今週
- /month：月間カレンダー
- /day/YYYY-MM-DD：日別予定
- /events/{event_id}：イベント詳細
- /admin：管理トップ
- /admin/artists、/admin/events：Artist・Event管理
- /admin/import、/admin/candidates：投稿取り込みとCandidate確認

イベントIDはローカルDBごとに異なります。/healthは起動確認用です。

## 使い方

初期化時にseedを実行すると、今日・明日・今週・翌月に関連した架空イベントが5件登録されます。DBにEventがすでに存在する場合、seedは何も追加せず終了します。

管理画面でArtistとEventを登録・編集できます。Eventには複数Artistの出演情報やSourceを設定できます。開催時刻（OPEN/START）とArtistの出演時間は別の項目です。

## 投稿取り込み

/admin/importで本文を貼り付けると、Parserの抽出結果がCandidateとして保存されます。候補画面で元本文と抽出結果を確認し、必要な項目を修正してください。承認するとEvent、Appearance、Sourceが作られます。重複候補を新規登録するときは、既存Eventを確認したうえで明示的に承認します。

Parserは日付、OPEN/START、出演・特典会の時間帯、会場、用途が分かるURLなどを補助的に抽出します。曖昧なタイトル、複数時間帯、年の省略、用途不明URL、画像内情報は正しく判定できない場合があります。解析警告の有無にかかわらず、承認前に人が内容を確認してください。

## CLI

Webと共通のImport Serviceを使い、Candidateを作成します。Eventを直接登録しません。

    # 1件の本文を解析し、保存せずに確認
    .\.venv\Scripts\python.exe scripts/update_events.py --text "2026/09/27 架空FES OPEN 17:00 START 17:30" --dry-run

    # 1件の本文をCandidateとして保存
    .\.venv\Scripts\python.exe scripts/update_events.py --text "2026/09/27 架空FES OPEN 17:00 START 17:30"

    # UTF-8ファイル（1ファイルにつき1投稿）
    .\.venv\Scripts\python.exe scripts/update_events.py --file examples/import_post.example.txt --dry-run

    # JSON配列の複数投稿
    .\.venv\Scripts\python.exe scripts/update_events.py --json examples/import_posts.example.json --dry-run

--text、--file、--jsonのいずれか1つを指定します。--source-url、--source-account、--artist-idも指定できます。JSON要素の形式はexamples/import_posts.example.jsonを参照してください。重複した投稿はスキップされます。保存後は管理画面で各Candidateを確認します。

APP_BASE_URLはCLIの結果に表示するCandidate画面URLを指定します。Uvicornの待受アドレスやアクセス制御を変更する設定ではありません。

## Google Calendar / ICS

イベント詳細から、イベント全体、Artistごとの出演、特典会を個別にGoogle Calendarへ追加、またはICSとして取得できます。Google CalendarリンクはGoogleの予定作成画面を開くだけで、自動登録はしません。Google API、OAuth、Google認証情報は使用しません。

日付と時刻は日本時間（Asia/Tokyo）で扱います。終日予定はOPENとSTARTのどちらも未設定の場合です。終了時刻がない予定はカレンダー形式を作るための仮の長さを使います（イベント2時間、出演30分、特典会60分）。この長さは実際の終了時刻を示すものではありません。

## テストとDBスキーマ確認

開発依存を入れた仮想環境で実行します。

    .\.venv\Scripts\python.exe -m pytest
    .\.venv\Scripts\python.exe -m alembic check

## データ保存

既定のSQLite DBはプロジェクト直下のdata/oshi_schedule.dbに作られます。data/とDBファイルはGit除外対象です。投稿本文や手入力の個人予定を含むデータは平文で保存されるため、PCのアカウントやバックアップ先を適切に保護してください。

ローカルデータを消去する場合は、サーバーを停止し、削除対象のDBファイルを確認してから削除してください。DBを削除すると予定とCandidateも失われます。その後はmigrationとseedを再実行できます。

## 環境設定

.env.exampleにはローカル実行に必要な項目だけを記載しています。

| 変数 | 用途 | 既定値 |
| --- | --- | --- |
| DATABASE_URL | SQLAlchemyのDB接続先。初期状態ではローカルSQLite | sqlite:///./data/oshi_schedule.db |
| APP_BASE_URL | CLIの結果に表示するCandidate一覧URLのベース | http://127.0.0.1:8000 |

.envにAPIキーなどの秘密情報を追加する必要はありません。.envと実DBをGitへ追加しないでください。

## セキュリティ

このリリースの管理画面・管理ルートには認証がありません。Event、Artist、Source、Candidateを読んだり変更したりできるため、FastAPIバックエンドを現状のままインターネットへ公開してはいけません。127.0.0.1にbindして、自分のPC上で使ってください。認証、CSRF対策、権限管理、TLSや本番配備設定は実装していません。

SourceとCandidateには投稿本文が保存されます。実投稿、個人の予定、個人情報を含むデータを公開Issue、Pull Request、サンプル、テストfixture、スクリーンショットへ入れないでください。資格情報やCookie、Tokenも登録・共有しないでください。

脆弱性の疑いは公開Issueに詳細や再現用資格情報を書かず、GitHubリポジトリで利用可能な非公開のSecurity Advisory（脆弱性報告）または保守担当者への非公開連絡を利用してください。報告方法の詳細はSECURITY.mdを参照してください。

## 既知の制限

- 認証がなく、ローカル利用専用です。
- Parserはルールベースです。複雑な投稿や画像からの解析はできず、人による確認が必要です。
- Xを含む外部サービスから投稿を自動取得しません。
- SQLite DBは暗号化されません。
- 今後のSites向けJSON APIはまだありません。
- テスト時、依存ライブラリのStarlette TestClientからhttpxを利用する箇所に非推奨警告が出る場合があります。テストの失敗を隠すための警告抑制は設定していません。

## ロードマップ

次の開発段階では、Sites向けの公開JSON APIと管理側のアクセス制御を別途設計します。APIではEvent、Artist、Appearanceの予定表示に必要な公開フィールドを明示し、Source.source_text、Candidate、内部の重複情報は公開しない方針です。認証なしの管理バックエンドを公開する構成は採用しません。

## ライセンス

MIT Licenseで公開します。詳細はLICENSEを参照してください。
