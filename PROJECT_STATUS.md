# Project Status

**Status:** FROZEN

**Frozen date:** 2026-09-27

## Original Goal

X上の特定アカウントから公開されるライブ・イベント・出演変更・チケット情報を見逃さず、予定として整理することが中心目的でした。

## Why Development Is Frozen

2026-09-27時点で、特定Xアカウントの投稿を無料かつ安定して取得する経路を確保できませんでした。これは外部プラットフォームの取得条件による開発凍結です。

### X Official API

公式API Collectorは実装済みです。実Live Testでは **HTTP 402 Payment Required** となり、無料運用の標準経路にできませんでした。利用する場合だけ設定するOptional機能として残しています。

### Twikit GuestClient

ログイン・X API Token・Cookieを使わないGuestClient PoCを実装しました。`@hc_staffACC`へのLive Testは「Twikit Guest取得に失敗しました。X側仕様変更またはGuest API制限の可能性があります。」（debug: `Exception`）で終了しました。GO条件を満たさないため **NO-GO** とし、通常のCollectorやWeb画面へ統合していません。

### Manual Import

無料で外部API通信のない手動取り込みは動作します。ただし、利用者が告知を発見してから貼り付ける方式です。元の中心目的である「X告知の見逃し防止」は完全には解決しません。

## What Works

- 今日・今週・月間・日別の予定とEvent詳細
- Artist、Event、Appearance、Sourceの管理
- Candidateの確認・編集・承認・却下
- 無料手動取り込み、Parserの解析だけ、X URL解析、重複防止
- 出演キャンセル等の変更告知Candidateと対象Event候補表示
- チケット発売予定、Google Calendarリンク、ICS
- Public Snapshot生成と静的Sites UI
- X公式APIのOptional Collector
- Twikit GuestのExperimental PoC（Live TestはNO-GO）

## What Is Not Implemented

- X自動監視と無料で安定したX投稿取得
- Eventの自動更新
- 定期スケジューラーと通知
- ChatGPT Sitesの一般公開

## Resume Conditions

以下のいずれかが成立した場合に再開を検討します。

1. X公式APIに実用的な無料Read枠が提供される。
2. X APIの料金が個人利用で十分小さくなる。
3. Twikit GuestClient等のログイン不要取得が安定して復旧する。
4. 無料で安定した合法的な公開投稿取得手段が登場する。
5. 公式サイト、RSS、イベントサービス等のX以外の公式告知経路だけで十分な見逃し防止が可能になる。
6. プロジェクトの目的を「X見逃し防止」から別の方向へ変更する。

## Security Decisions

今後も原則として、Xアカウントのパスワード、`auth_token`、`ct0`、ブラウザCookieの保存・流用、CAPTCHAやCloudflareの回避、Proxyや大量アカウントのrotation、認証回避、X内部仕様への過度な依存は採用しません。

## Current Recommended Usage

凍結中もローカルで使用できます。Xまたは公式サイトで告知を見つけ、`/admin/import`へ貼り付け、Parserの結果とCandidateを確認してEventを登録します。必要ならPublic Snapshotを生成します。この使い方は**見つけた告知の整理**であり、自動的な見逃し防止ではありません。
