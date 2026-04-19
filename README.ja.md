# vercel-incident-toolkit

[English](README.md) · [한국어](README.ko.md) · **日本語** · [简体中文](README.zh-Hans.md)

> ⚠️ **ご注意**。公式ツールではなく、完全な答えでもなく、思考の代わりにもなりません。[Vercel 2026年4月のセキュリティインシデント](https://vercel.com/kb/bulletin/vercel-april-2026-security-incident)の直後、一人のエンジニアが急ぎで書いた playbook です。`--apply` を付ける前に必ず各スクリプトを読んでください。自己責任でご利用ください。最終的な権威は常に Vercel 公式ドキュメント(本文に都度リンク)です。

Vercel アカウントのハードニングおよびインシデント対応のための toolkit 兼 Claude Code スキル。**Vercel 専用**、ランタイム依存ゼロ。

---

## Vercel 2026年4月 — 初動対応チェックリスト

Vercel 公式の推奨(「環境変数を見直し、sensitive environment variable 機能を活用する」)に沿って作成。この toolkit はその見直しを自動化し、ローテーション + 引き継ぎドキュメント生成を上乗せします。

### Step 0 — トークンとアカウント衛生(先に、絶対にスキップしない)

`vercel logout && vercel login` **だけでは不十分**。侵害中はより広範囲に:

1. [vercel.com/account/tokens](https://vercel.com/account/tokens) → 今必要でないトークンは**すべて revoke**。`vercel logout` は現在のマシンの CLI トークンのみを無効化します。他マシン・CI・integrations のトークンはそのまま残ります。
2. まだなら [2FA を有効化](https://vercel.com/account/security)。可能ならハードウェアキーを TOTP より優先。
3. 各チームで: Team → Settings → Members → 全員 2FA 有効か確認。元メンバー/契約終了者を削除。
4. このマシンで `vercel logout && vercel login` — クリーンな新トークン取得。
5. Team → Audit Log → 侵害推定ウィンドウで `token.create`, `member.add`, `role.change`, `project.create`, deploy protection の切替履歴を全走査。

ここまで終えてから toolkit を実行。

### Step 1 — 監査と内部シークレットのローテーション(toolkit)

```bash
git clone https://github.com/subinium/vercel-incident-toolkit
cd vercel-incident-toolkit
python3 scripts/preflight.py                 # 環境チェック
python3 scripts/audit.py                     # 読み取り専用インベントリ
python3 scripts/rotate-internal.py           # dry-run — 実行計画のみ表示
python3 scripts/rotate-internal.py --apply   # 実際にローテート
python3 scripts/handoff-gen.py               # プロジェクトごとの後続文書を生成
```

Step 1 の後、`~/security-incident-<YYYY-MM>-vercel/` を開いてください。影響のあったプロジェクトごとに markdown が一つ。手動でローテーションすべきベンダーキーと、正確な後続コマンドが載っています。

### Step 2 — 外部ベンダーキーのローテーション(手動、一つずつ)

ベンダーキー(Supabase service role、`DATABASE_URL`、OAuth client secret、サードパーティ API)は**絶対に自動ローテートしません**。Vercel の[公式ローテーションパターン](https://vercel.com/docs/environment-variables/rotating-secrets)に従う:

1. ベンダーダッシュボードで新しい credential を生成(この時点で古い方を無効化しては**いけない**)
2. Vercel に新値をアップロード: `python3 scripts/update-env.py <project> <KEY> --from-stdin --apply`
3. Vercel プロジェクトを再デプロイし、正常動作を確認
4. **その後** ベンダーダッシュボードで古い credential を無効化

ベンダー別 runbook: [`runbooks/vendor-*.md`](runbooks/)。一度に一ベンダーだけ — バッチは厳禁。

### Step 3 — ハードニング(任意、ローテーション後)

```bash
python3 scripts/harden-to-sensitive.py --apply
```

Vercel の [sensitive environment variables ドキュメント](https://vercel.com/docs/environment-variables/sensitive-environment-variables)に沿って、すべての非 sensitive を `sensitive` 型に変換。以降、値はダッシュボード・API から読めなくなります — 再度確認したければローテーションが唯一の道。

> **Vercel 公式制約**: sensitive 型は **production + preview** ターゲットのみサポート。development は対象外。toolkit は development に対して自動で `encrypted` にフォールバックします。

### Step 4 — ローテーション後([`runbooks/04-after-rotation.md`](runbooks/04-after-rotation.md))

- 各プロジェクトで `vercel env pull` — ローカル `.env` を更新
- `vercel --prod` を各プロジェクト — warm serverless を強制 cold-start(古い env を掴んだままのインスタンスを除去)
- CI/CD の secret mirror を更新(GitHub Actions 等)
- すべての [Deploy Hook](https://vercel.com/docs/deployments/deploy-hooks) URL をローテート
- 30 日間、週 1 の `scripts/audit.py` diff — 想定外の新 env var・プロジェクトを監視

---

## 脅威モデル — Vercel アーキテクチャに整合

[Vercel sensitive env var docs](https://vercel.com/docs/environment-variables/sensitive-environment-variables) 準拠:

| タイプ | 復号鍵の所在 | 侵害時の想定 |
|---|---|---|
| `plain` | どこにも無し — 平文保存 | **漏洩前提** |
| `encrypted` | Vercel 内部 KMS — ダッシュボード・ランタイム用にサーバサイドで復号 | 内部システムまで到達した侵害では**漏洩前提** |
| `sensitive` | 制限されたパス — *「作成後は読み取り不可」*、ダッシュボード・API から返されない | ビルド/ランタイムサンドボックスまで到達しなければ**生存の可能性** |

そこから導かれるルール:
1. 漏洩した値はローテーションが先、ハードニングは次。ハードニングは既に漏洩した値を保存するだけ。
2. sensitive は万能ではない — ビルド時にアクセスされる値はビルドインフラ侵害で露出。
3. 公式: *「既存 env var を sensitive にするには remove + re-add」* — 型変更は in-place edit ではない。

---

## この toolkit が合う対象

**良いフィット**
- Next.js / Remix / SvelteKit / Nuxt アプリ数個を Vercel で運用
- 数時間ではなく数分で初動対応を回せるようにしたい
- 一般的な auth(Auth.js / NextAuth / Clerk / Supabase Auth) + DB(Supabase / Neon / Postgres)

**部分的フィット**
- 非 JS スタック — Flow A(監査)は汎用。Flow C(自動ローテーション)は列挙したキーのみ。`--include` で自分のフレームワークの安全なランダムキーを追加。
- カスタム JWE / フィールド単位暗号化 / ローテが状態データ不可逆になる設計 — 手動で。

**合わない**
- コンプライアンス成果物(SOC 2, ISO 27001)— これは operator playbook であり監査証跡ではない。
- Change Advisory Board の承認を要する環境 — ここのミューテーションは即時。

**toolkit が検出できないもの(手動)**
- 過去の本番デプロイに既に入った悪意ある変更 → `vercel ls --prod` + git SHA 差分
- ソーシャルエンジニアリングで追加された team member → Audit Log レビュー
- 忘れている他デバイスのトークン → ダッシュボードから全 revoke
- 連携サービスの二次侵害 → ベンダー各々の audit log

疑わしいときは、toolkit の出力を「完了」証明ではなく「検証チェックリスト」として扱ってください。

---

## 4 つのフロー

### A. 監査 — `scripts/audit.py`
全スコープ(個人 + 各チーム)の全プロジェクトの env var を列挙・分類(`OK` sensitive / `HIGH` 高リスク encrypted / `MED` 一般 encrypted / `LOW-PLAIN` 平文)。読み取り専用。`~/.vercel-security/audit-<timestamp>.json` に保存。

### B. ハードニング — `scripts/harden-to-sensitive.py`
非 sensitive を値そのままに `sensitive` 型へ変換。[公式 sensitive docs](https://vercel.com/docs/environment-variables/sensitive-environment-variables) 準拠。平文取得は `vercel env pull`、その後公式 `DELETE` + `POST`。`NEXT_PUBLIC_*` はスキップ。development は Vercel 制約のため `encrypted` にフォールバック。Dry-run が既定。

### C. インシデント — `scripts/rotate-internal.py` + `handoff-gen.py`

内部ランダムシークレットを自動ローテート。Vercel の `PATCH /v9/projects/.../env/<id>` を使って atomic in-place の値のみ更新 — env id と型は保持、変数不在の窓は無し。既定リスト:

| キー | 守るもの |
|---|---|
| `NEXTAUTH_SECRET` / `AUTH_SECRET` | NextAuth / Auth.js セッション JWT |
| `SESSION_SECRET` / `COOKIE_SECRET` | Remix / Express / Hono / Fastify セッション署名 |
| `PAYLOAD_SECRET` | PayloadCMS |
| `PREVIEW_SECRET` / `REVALIDATION_SECRET` | Next.js preview / on-demand ISR |
| `CRON_SECRET` | Vercel Cron の認証 |
| `API_KEY_HMAC_SECRET` / `HMAC_SECRET` | 内部 API の HMAC 署名 |
| `ADMIN_PASSWORD` | 単純 admin — **新値は stdout に 1 回のみ、保存されない** |

`--include KEY1,KEY2` で拡張可。`NEVER_ROTATE_PATTERNS` に一致するものは**拒否**(at-rest 暗号化、ベンダーシークレット、長寿命 JWT 署名キー — 状態データを壊すため)。

`handoff-gen.py` は `~/security-incident-<YYYY-MM>-vercel/<project>.md` にプロジェクト毎のマークダウンを書き出し。平文は含めません。

### D. ベンダーローテーション — `scripts/update-env.py`
ベンダーダッシュボードでローテート後:
```bash
python3 scripts/update-env.py <project> <KEY> --from-stdin --apply
```
Vercel の[安全ローテーションパターン](https://vercel.com/docs/environment-variables/rotating-secrets)準拠 — 新値をアップロード(production/preview は `sensitive`、development は `encrypted`)、任意で `--redeploy` により即時再デプロイ、`~/.vercel-security/rotations.json` にログ(平文なし)。

**順序が重要**: Vercel を更新 → 再デプロイで検証 → **その後** ベンダーで古いキーを無効化。公式: *「安全なローテーションの鍵は、古い credential を無効化する前に Vercel を更新すること」*。

---

## `.gitignore` は 2 つ — 混同しない

この toolkit リポジトリの `.gitignore` は、**コントリビューターが toolkit 開発中に生成される artifact** のコミットを防ぎます。

あなたの **Vercel デプロイ済みアプリリポジトリ**にも ignore パターンが必要 — `vercel env pull` や handoff ドキュメントが誤って git に入らないよう。各アプリリポジトリで一度:

```bash
python3 scripts/ignore-setup.py /path/to/your/app-repo
```

`.gitignore`, `.vercelignore`, `.dockerignore`, `.npmignore` にパターンを追記。冪等 — 既にあればスキップ。

デフォルトでは toolkit の出力は `~/.vercel-security/` と `~/security-incident-*-vercel/` — どのリポジトリの外。ignore パターンは、handoff ドキュメントをリポジトリへ意図的にコピーしたとき用のベルト+サスペンダー。

---

## サプライチェーンと攻撃者モデル

攻撃者がこのリポジトリの全行を読んだと仮定。

**攻撃者が学ぶもの**: シークレット分類用のキー名パターン、ローカル Vercel CLI auth ファイルのパス、使用する Vercel API endpoint セット。すべて Vercel 公式ドキュメントにも記載。

**攻撃者が学ばないもの**: あなたのトークン(ランタイムに読むだけ、埋め込み無し)、プロジェクト名/ID、ローテーションログ、平文値。

**スクリプトの構造的セーフティ**
- シークレット値は `getpass` のみで受け取る(CLI 引数はシェル履歴に残るため)
- Vercel CLI トークンを出力・ログに出さない(エラー時も)
- 平文ローテーション値を disk に保存しない(`ADMIN_PASSWORD` 含む — stdout 1 回のみ)
- `~/.vercel-security/`、`~/security-incident-*-vercel/`、明示されたターゲットリポジトリパス以外を読み書きしない
- `api.vercel.com` 以外のネットワーク呼び出しをしない
- 冪等な API 呼び出しは 429/5xx で exponential backoff リトライ、4xx は再試行しない

**サプライチェーン**
- Python 標準ライブラリのみ。`requirements.txt` も npm も外部 import も無し。コピーにこれらが含まれていたら改ざん済み。
- リリースはタグで固定: `git checkout v0.1.0`。
- fork を使うなら差分を監査してから実行。未知の fork の main を clone しない。

fork してこれらを弱めるなら、README 冒頭で**目立つように**告知してください。利用者が差分を読まずとも安全性の変化を知れるように。

---

## Runbook

プロセス
- [`00-incident-response.md`](runbooks/00-incident-response.md) — 分単位の playbook
- [`01-prevention-hardening.md`](runbooks/01-prevention-hardening.md) — Vercel セキュリティ設定(Git Fork Protection、Deploy Protection、Enforce Sensitive policy、OIDC)
- [`02-common-mistakes.md`](runbooks/02-common-mistakes.md) — よくあるミス/避けるべき行動
- [`03-post-incident-monitoring.md`](runbooks/03-post-incident-monitoring.md) — 週次 audit、canary、クローズ基準
- [`04-after-rotation.md`](runbooks/04-after-rotation.md) — toolkit 完了後の**「完了」の本当の意味**

ベンダー別
- [Supabase](runbooks/vendor-supabase.md)
- [Google OAuth](runbooks/vendor-google-oauth.md)
- [Neon / Postgres](runbooks/vendor-neon.md)
- [汎用サードパーティ API](runbooks/vendor-generic.md)

---

## 信頼できる参照(公式 + 検証済)

Vercel 公式(この README より常に公式を優先):
- [Vercel 2026年4月のセキュリティインシデント — KB bulletin](https://vercel.com/kb/bulletin/vercel-april-2026-security-incident)
- [環境変数のローテーション — 公式パターン](https://vercel.com/docs/environment-variables/rotating-secrets)
- [Sensitive environment variables](https://vercel.com/docs/environment-variables/sensitive-environment-variables)
- [環境変数の概要](https://vercel.com/docs/environment-variables)
- [プロジェクトのセキュリティ設定](https://vercel.com/docs/project-configuration/security-settings)
- [Tokens](https://vercel.com/docs/sign-in-with-vercel/tokens)
- [Deploy Protection](https://vercel.com/docs/deployment-protection)
- [OIDC Federation](https://vercel.com/docs/oidc) — AWS/GCP の長寿命キーを短寿命トークンに移行

検証済みの 3rd party
- [GitGuardian — Vercel API access token 漏洩時の対処](https://www.gitguardian.com/remediation/vercel-api-access-token)

この README は意図的に未検証のブログ記事を引用しません。上記に無い情報源は、推奨に足る相互検証ができなかったということです。

---

## License

MIT.
