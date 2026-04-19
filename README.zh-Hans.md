# vercel-incident-toolkit

[English](README.md) · [한국어](README.ko.md) · [日本語](README.ja.md) · **简体中文**

> ⚠️ **免责声明。** 这不是官方工具,不是完整答案,也不能替代你自己的判断。这是一位工程师在 [Vercel 2026 年 4 月安全事件](https://vercel.com/kb/bulletin/vercel-april-2026-security-incident)披露后数小时内整理的**指南性技能**(结构化清单 + *可选的* CLI 自动化)。在使用 `--apply` 之前请阅读每个脚本。使用风险自负。权威指引始终是 Vercel 官方文档(正文内附链接)。

> 🤖 **不要把这份技能完全交给 AI 去跑后就撒手不管。** 本 toolkit 会直接操作你真实的 Vercel 账户。在任何 `--apply` 之前,都要亲自审阅脚本 — 要么自己读,要么*和 AI 一起*让它解释每段脚本、为其方案给出依据,并把你的副本与上游 `main` 做 diff。"AI 说没问题"只是检查点,不是绿灯。每一次破坏性操作都该由你自己决定。

用于 **Vercel 账户加固与事件响应**的**以指南为主的 toolkit + Claude Code 技能**。把它当成一份清单:可以一项项手动做,也可以交给脚本执行,每一步都由你选择。**仅限 Vercel**,零运行时依赖。

## 范围 — 它会触及什么

- **通过本机的 `vercel` CLI 认证,作用于你整个 Vercel 账户** — 通过官方 Vercel REST API 枚举你所在的每一个团队以及其中的每一个项目。不受限于某个仓库或本地目录。
- **不扫描本地 git 仓库。** 仅当你明确地把某条路径传给 `scripts/ignore-setup.py` 时才会触及本地路径。
- **除 `api.vercel.com` 之外不与任何主机通信。**
- **不修改 shell rc、系统 keychain 或全局配置。**

## 两种使用方式 — 可按步骤切换

| 模式 | 做法 | 适用情形 |
|---|---|---|
| **自动(CLI)** | 以 `--apply` 运行脚本 | 你信任 dry-run 的输出,愿意让 toolkit 执行变更 |
| **手动(参考)** | 运行 `scripts/audit.py`(始终只读)与 `scripts/handoff-gen.py`,其余全部在 Vercel dashboard 与 vendor dashboard 手动完成 | 希望 toolkit 告诉你*要改什么*,但实际变更由你亲手完成 |

不必为整个事件选同一种模式 — 每一步可自由组合。常见选择:Flow C 的内部随机值轮换走自动,vendor 轮换走手动。所有破坏性脚本**默认为 dry-run**,变更前均会 `y/N` 确认。

---

## Vercel 2026 年 4 月 — 首要响应清单

与 Vercel 官方建议("审查环境变量并启用 sensitive environment variable")保持一致。本 toolkit 将审查自动化,并在此之上叠加轮换 + 交接文档生成。

### 第 0 步 — 令牌与账户卫生(优先、不可跳过)

仅 `vercel logout && vercel login` **是不够的**。事件期间需要更广范围的清理:

1. [vercel.com/account/tokens](https://vercel.com/account/tokens) → **吊销所有当前不必要的令牌**。`vercel logout` 只会使当前机器的 CLI 令牌失效;其他机器、CI、集成持有的令牌依然有效。
2. 若未启用,[启用 2FA](https://vercel.com/account/security)。优先使用硬件安全密钥,其次才是 TOTP。
3. 每个团队:Team → Settings → Members → 确认所有成员都启用 2FA。移除已离开的成员与已终止的外包人员。
4. 在本机执行 `vercel logout && vercel login` — 获取一个全新的干净令牌。
5. Team → Audit Log → 在可疑窗口扫描 `token.create`、`member.add`、`role.change`、`project.create` 以及 deployment protection 的变更。

完成以上后再运行 toolkit。

### 第 1 步 — 审计并轮换内部秘密(toolkit)

```bash
git clone https://github.com/subinium/vercel-incident-toolkit
cd vercel-incident-toolkit
python3 scripts/preflight.py                 # 环境检查
python3 scripts/audit.py                     # 只读清单
python3 scripts/rotate-internal.py           # dry-run — 仅显示计划
python3 scripts/rotate-internal.py --apply   # 实际轮换
python3 scripts/handoff-gen.py               # 生成每个项目的后续文档
```

第 1 步之后,打开 `~/security-incident-<YYYY-MM>-vercel/` — 每个受影响项目一个 markdown 文件,列出仍需手动轮换的 vendor 密钥以及准确的后续命令。

### 第 2 步 — 外部 vendor 密钥轮换(手动、逐一)

vendor 密钥(Supabase service role、`DATABASE_URL`、OAuth client secret、第三方 API)**永远不会自动轮换**。按照 Vercel 的[官方轮换顺序](https://vercel.com/docs/environment-variables/rotating-secrets):

1. 在 vendor 控制台生成新的凭据(**此时不要**吊销旧的)
2. 将新值上传至 Vercel:`python3 scripts/update-env.py <project> <KEY> --from-stdin --apply`
3. 重新部署 Vercel 项目并验证正常
4. **然后**在 vendor 控制台吊销旧凭据

各 vendor 的 runbook:[`runbooks/vendor-*.md`](runbooks/)。一次处理一个 vendor,切勿批量。

### 第 3 步 — 加固(轮换完成后可选)

```bash
python3 scripts/harden-to-sensitive.py --apply
```

按照 [sensitive environment variables 官方文档](https://vercel.com/docs/environment-variables/sensitive-environment-variables)将所有 non-sensitive 转为 `sensitive`。此后值将无法在 dashboard 或 API 中读取 — 想再看到只能轮换。

> **Vercel 官方限制**:sensitive 类型仅支持 **production + preview** 目标,development 不支持。toolkit 会自动把 development 回退为 `encrypted`。

### 第 4 步 — 轮换之后(见 [`runbooks/04-after-rotation.md`](runbooks/04-after-rotation.md))

- 每个项目 `vercel env pull` — 刷新本地 `.env`
- 每个项目 `vercel --prod` — 强制 warm serverless 冷启动,清除仍持有旧值的实例
- 更新 CI/CD 的 secret mirror(GitHub Actions 等)
- 轮换每个 [Deploy Hook](https://vercel.com/docs/deployments/deploy-hooks) URL
- 之后 30 天每周跑 `scripts/audit.py`,比对是否出现异常的新 env var 或项目

---

## 威胁模型 — 与 Vercel 架构对齐

遵循 [Vercel sensitive env var 文档](https://vercel.com/docs/environment-variables/sensitive-environment-variables):

| 类型 | 解密密钥所在 | 事件后假设 |
|---|---|---|
| `plain` | 无 — 明文存储 | **假定已泄露** |
| `encrypted` | Vercel 内部 KMS — dashboard 与运行时通过服务端解密 | 触及内部系统的事件中**假定已泄露** |
| `sensitive` | 受限路径 — *"创建后不可读取"*,dashboard 与 API 均不返回 | 未触及 build/runtime 沙箱则**大概率存活** |

由此得出的规则:
1. 对已泄露的值,轮换优先于加固。加固只是保留了一个已泄露的值。
2. sensitive 并非银弹 — 构建期访问的值在 build 基础设施失陷时仍会外泄。
3. 官方:*"要将现有 env var 标为 sensitive,需先删除再重新添加"* — 类型变更不是原地编辑。

---

## 是否适合你

**适合**
- 在 Vercel 上运营若干 Next.js / Remix / SvelteKit / Nuxt 应用
- 希望以分钟级而非小时级的首要响应流程
- 使用常见 auth(Auth.js / NextAuth / Clerk / Supabase Auth)与 DB(Supabase / Neon / Postgres)

**部分适合**
- 非 JS 技术栈 — Flow A(审计)仍通用;Flow C(自动轮换)仅覆盖列出的键。用 `--include` 添加你框架里的安全随机键。
- 自定义 JWE / 字段级加密 / 轮换会导致数据不可访问的会话设计 — 手动处理。

**不适合**
- 合规产出物(SOC 2、ISO 27001)— 这是 operator playbook,不是审计证据。
- 每项变更都需变更管理委员会审批的环境 — 本工具的修改是即时的。

**toolkit 无法发现的(需手动)**
- 已注入过往生产部署的恶意代码 → `vercel ls --prod` + git SHA diff
- 通过社工新增的团队成员 → Audit Log 审查
- 被遗忘的其他设备上的令牌 → 在 dashboard 统一 revoke
- 关联服务的二次泄露 → 各 vendor 自身的审计日志

若有疑虑,把 toolkit 的输出当作验证清单,而不是"已完成"的证据。

---

## 四个流程

### A. 审计 — `scripts/audit.py`
枚举所有作用域(个人 + 各团队)中所有项目的 env var 并分类(`OK` sensitive / `HIGH` 高风险 encrypted / `MED` 一般 encrypted / `LOW-PLAIN` 明文)。只读。写入 `~/.vercel-security/audit-<timestamp>.json`。

### B. 加固 — `scripts/harden-to-sensitive.py`
将所有 non-sensitive 以相同值重新上传为 `sensitive` 类型,遵循 [sensitive env var 官方文档](https://vercel.com/docs/environment-variables/sensitive-environment-variables)。通过 `vercel env pull` 获取明文,再用官方 `DELETE` + `POST`。`NEXT_PUBLIC_*` 跳过。development 目标按 Vercel 限制回退为 `encrypted`。默认 dry-run。

### C. 事件响应 — `scripts/rotate-internal.py` + `handoff-gen.py`

自动轮换已知的内部随机秘密。使用 Vercel 文档化的 `PATCH /v9/projects/.../env/<id>` 端点进行值的原地原子更新 — 保留 env id 与类型,中间无变量缺失窗口。默认列表:

| Key | 保护对象 |
|---|---|
| `NEXTAUTH_SECRET` / `AUTH_SECRET` | NextAuth / Auth.js 会话 JWT |
| `SESSION_SECRET` / `COOKIE_SECRET` | Remix / Express / Hono / Fastify 会话与 cookie 签名 |
| `PAYLOAD_SECRET` | PayloadCMS |
| `PREVIEW_SECRET` / `REVALIDATION_SECRET` | Next.js preview / 按需 ISR |
| `CRON_SECRET` | Vercel Cron 授权 |
| `API_KEY_HMAC_SECRET` / `HMAC_SECRET` | 内部 API HMAC 签名 |
| `ADMIN_PASSWORD` | 简单 admin — **新值仅打印到 stdout 一次,不做任何持久化** |

传 `--include KEY1,KEY2` 扩展。匹配 `NEVER_ROTATE_PATTERNS`(at-rest 加密、vendor 秘密、长期 JWT 签名键 — 轮换会破坏有状态数据)时将**拒绝**。

`handoff-gen.py` 在 `~/security-incident-<YYYY-MM>-vercel/<project>.md` 为每个项目写出 markdown,**不含任何明文值**。

### D. Vendor 轮换 — `scripts/update-env.py`
在 vendor 控制台轮换后:
```bash
python3 scripts/update-env.py <project> <KEY> --from-stdin --apply
```
遵循 Vercel 的[安全轮换顺序](https://vercel.com/docs/environment-variables/rotating-secrets) — 上传新值(prod/preview 为 `sensitive`,development 为 `encrypted`),可选 `--redeploy` 立刻再部署,并写入 `~/.vercel-security/rotations.json`(不含明文)。

**顺序至关重要**:先更新 Vercel → 再部署并验证 → **然后**才去 vendor 吊销旧凭据。官方:*"安全轮换的关键是,在使旧凭据失效之前先更新 Vercel。"*

---

## 两个 `.gitignore` — 不要混淆

本 toolkit 仓库的 `.gitignore` 防止**贡献者在开发 toolkit 时误提交 artifact**。

你的 **Vercel 部署的应用仓库**也需要 ignore 模式 — 避免 `vercel env pull` 或 handoff 文档误入 git。每个应用仓库执行一次:

```bash
python3 scripts/ignore-setup.py /path/to/your/app-repo
```

向 `.gitignore`、`.vercelignore`、`.dockerignore`、`.npmignore` 追加模式。幂等 — 已存在则跳过。

默认情况下 toolkit 输出位于 `~/.vercel-security/` 与 `~/security-incident-*-vercel/` — 均在任何仓库之外。ignore 模式是为防止你主动把 handoff 文档拷入仓库时的双保险。

---

## 供应链 & 攻击者模型

假设攻击者已读遍本仓库每一行。

**他们能学到**:用于分类秘密的键名模式、本地 Vercel CLI auth 文件路径、我们使用的 Vercel API 端点集。这些在 Vercel 官方文档里也都能找到。

**他们学不到**:你的令牌(运行时才读取、不嵌入仓库)、你的项目名/ID、轮换日志、任何明文值。

**脚本的结构化安全属性**
- 秘密值仅通过 `getpass` 接收(CLI 参数会进入 shell history)
- 绝不打印或日志化 Vercel CLI 令牌(出错时也一样)
- 绝不把明文轮换值写入 disk(包括 `ADMIN_PASSWORD` — 仅打印 stdout 一次)
- 只在 `~/.vercel-security/`、`~/security-incident-*-vercel/`,以及显式给定的目标仓库路径内读写
- 除 `api.vercel.com` 之外不做任何网络调用
- 对幂等 API 调用的 429/5xx 指数回退重试;对 4xx 不重试

**供应链**
- 仅使用 Python 标准库。没有 `requirements.txt`,没有 npm,没有外部 import。你拿到的副本若有这些,则已被篡改。
- 发行版本打 tag 以便锁定:`git checkout v0.1.0`。
- 使用 fork 请先审计 diff。不要 clone 不认识的 fork 的 main。

若你 fork 并弱化上述任何属性,请在 README 顶部**高声**声明。用户不需要读 diff 就应知道安全属性变了。

---

## Runbook

流程
- [`00-incident-response.md`](runbooks/00-incident-response.md) — 分钟级 playbook
- [`01-prevention-hardening.md`](runbooks/01-prevention-hardening.md) — Vercel 安全设置(Git Fork Protection、Deploy Protection、Enforce Sensitive policy、OIDC)
- [`02-common-mistakes.md`](runbooks/02-common-mistakes.md) — 常见错误/应避免的做法
- [`03-post-incident-monitoring.md`](runbooks/03-post-incident-monitoring.md) — 每周 audit、canary、关单标准
- [`04-after-rotation.md`](runbooks/04-after-rotation.md) — toolkit 完成后的**"真正完成"含义**

各 vendor
- [Supabase](runbooks/vendor-supabase.md)
- [Google OAuth](runbooks/vendor-google-oauth.md)
- [Neon / Postgres](runbooks/vendor-neon.md)
- [通用第三方 API](runbooks/vendor-generic.md)

---

## 权威参考(官方 + 已验证)

Vercel 官方(始终以官方为准,优先于本 README):
- [Vercel 2026 年 4 月安全事件 — KB 公告](https://vercel.com/kb/bulletin/vercel-april-2026-security-incident)
- [环境变量轮换 — 官方流程](https://vercel.com/docs/environment-variables/rotating-secrets)
- [Sensitive environment variables](https://vercel.com/docs/environment-variables/sensitive-environment-variables)
- [环境变量总览](https://vercel.com/docs/environment-variables)
- [项目安全设置](https://vercel.com/docs/project-configuration/security-settings)
- [Tokens](https://vercel.com/docs/sign-in-with-vercel/tokens)
- [Deploy Protection](https://vercel.com/docs/deployment-protection)
- [OIDC Federation](https://vercel.com/docs/oidc) — 将 AWS/GCP 的长期密钥迁移为短期令牌

已验证的 3rd party
- [GitGuardian — Vercel API access token 泄漏处置](https://www.gitguardian.com/remediation/vercel-api-access-token)

本 README 有意不引用未经验证的博客。未在上列出现的来源,意味着交叉验证不足,不建议据此行动。

---

## License

MIT.
