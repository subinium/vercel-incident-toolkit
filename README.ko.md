# vercel-incident-toolkit

[English](README.md) · **한국어** · [日本語](README.ja.md) · [简体中文](README.zh-Hans.md)

> ⚠️ **주의.** 공식 도구 아니고, 완전한 해답 아니고, 사고(思考)를 대체하지도 않아요. [Vercel 2026년 4월 보안 사고](https://vercel.com/kb/bulletin/vercel-april-2026-security-incident) 발표 직후 엔지니어 한 명이 급히 정리한 **가이드라인 스킬**(구조화된 체크리스트 + *선택적* CLI 자동화) 입니다. `--apply` 붙이기 전에 모든 스크립트 읽어보세요. 본인 책임. 최종 권위는 언제나 Vercel 공식 문서 (본문 곳곳에 링크).

> 🤖 **AI에게 맡기고 자리 비우지 마세요.** 이 toolkit은 당신의 실제 Vercel 계정을 건드립니다. 어떤 `--apply` 전에도 스크립트를 직접 검수하세요 — 혼자 하시거나, *AI와 함께* 각 스크립트가 뭘 하는지 설명받고 계획의 근거를 따지고 upstream `main`과 diff 하면서. "AI가 괜찮다고 했다"는 녹색 신호가 아니라 체크포인트일 뿐. 모든 파괴적 행동은 당신의 결정입니다.

Vercel 계정 하드닝 + 사고 대응을 위한 **가이드라인 중심 toolkit 겸 Claude Code 스킬**. 체크리스트라고 생각하시면 돼요 — 손으로 하나씩 해도 되고, 스크립트가 실행하게 해도 되고, 단계별로 선택하면 됩니다. **Vercel 전용**, 런타임 의존성 없음.

## 범위 — 이게 건드리는 것

- **당신의 Vercel 계정 전체를 로컬 `vercel` CLI 인증을 통해** — 공식 Vercel REST API로 모든 소속 팀과 해당 팀 내 모든 프로젝트를 열거. 특정 레포나 로컬 디렉토리에 한정되지 않음.
- **로컬 git 레포지토리를 스캔하지 않음.** 로컬 경로는 당신이 `scripts/ignore-setup.py`에 명시적으로 path를 넘길 때만 건드림.
- **`api.vercel.com` 외에는 어떤 호스트와도 통신하지 않음.**
- **shell rc 파일·시스템 키체인·전역 설정을 수정하지 않음.**

## 사용 방식 2가지 — 단계별로 선택

| 모드 | 방법 | 언제 |
|---|---|---|
| **자동 (CLI)** | 스크립트를 `--apply`로 실행 | dry-run 출력을 신뢰하고 toolkit이 mutation을 실행하길 원함 |
| **수동 (레퍼런스)** | `scripts/audit.py`(항상 읽기 전용) + `scripts/handoff-gen.py` 돌리고, 나머지는 Vercel 대시보드와 벤더 대시보드에서 손으로 | toolkit에게 *무엇*을 바꿔야 하는지는 듣되 모든 변경은 본인이 하고 싶음 |

전체 사건을 한 모드로 통일할 필요 없어요 — 단계별로 섞으세요. 흔한 선택: Flow C의 내부 랜덤 회전은 자동, 외부 벤더 회전은 수동. 모든 파괴적 스크립트는 **dry-run이 디폴트**이고 변경 전에 `y/N` 확인.

---

## Vercel 2026년 4월 — 1차 대응 체크리스트

Vercel 공식 권고("환경변수를 점검하고 sensitive env var 기능을 활용하세요")에 맞춰 제작. 이 toolkit은 그 점검을 자동화하고, 위에 회전 + 인계 문서 생성을 얹어요.

### Step 0 — 토큰 & 계정 위생 먼저 (건너뛰지 말 것)

`vercel logout && vercel login`**만으로는 부족**합니다. 침해 중에는:

1. [vercel.com/account/tokens](https://vercel.com/account/tokens) → **현재 쓰고 있지 않은 토큰 전부 revoke**. `vercel logout`은 현재 머신의 CLI 토큰만 무효화함. 다른 머신·CI 러너·integration은 각자의 토큰을 그대로 들고 있음.
2. 아직이면 [2FA 활성화](https://vercel.com/account/security). 가능하면 하드웨어 키가 TOTP보다 좋음.
3. 각 팀별로: Team → Settings → Members → 모두 2FA 켜져 있는지 확인. 퇴사자/외주자 제거.
4. 이 머신에서 `vercel logout && vercel login` — 깨끗한 새 토큰 획득
5. Team → Audit Log → 침해 추정 window에서 `token.create`, `member.add`, `role.change`, `project.create`, deploy protection toggle 이력 전수 확인

이 단계 이후에야 toolkit 실행.

### Step 1 — 감사 & 내부 시크릿 회전 (toolkit)

```bash
git clone https://github.com/subinium/vercel-incident-toolkit
cd vercel-incident-toolkit
python3 scripts/preflight.py                 # 환경 체크
python3 scripts/audit.py                     # 읽기 전용 인벤토리
python3 scripts/rotate-internal.py           # dry-run — 계획만 출력
python3 scripts/rotate-internal.py --apply   # 실제 회전
python3 scripts/handoff-gen.py               # 프로젝트별 후속 문서 생성
```

Step 1 완료 후 `~/security-incident-<YYYY-MM>-vercel/` 열기 — 영향받은 프로젝트마다 마크다운 하나. 아직 손으로 회전해야 하는 벤더 키 목록과 정확한 후속 명령어까지 들어있음.

### Step 2 — 외부 벤더 키 회전 (수동, 하나씩)

벤더 키(Supabase service role, `DATABASE_URL`, OAuth client secret, 서드파티 API)는 **자동 회전 절대 안 함**. Vercel [공식 회전 패턴](https://vercel.com/docs/environment-variables/rotating-secrets)을 따라:

1. 벤더 대시보드에서 새 credential 생성 (이 시점에선 기존 것 무효화 **금지**)
2. Vercel에 새 값 업로드: `python3 scripts/update-env.py <project> <KEY> --from-stdin --apply`
3. Vercel 프로젝트 재배포 + 정상 동작 확인
4. **그제서야** 벤더 대시보드에서 기존 credential 무효화

벤더별 runbook: [`runbooks/vendor-*.md`](runbooks/). 한 번에 한 벤더 — 절대 배치하지 말 것.

### Step 3 — 하드닝 (회전 이후, 선택)

```bash
python3 scripts/harden-to-sensitive.py --apply
```

Vercel [sensitive env var 문서](https://vercel.com/docs/environment-variables/sensitive-environment-variables)대로 모든 non-sensitive env var를 `sensitive` 타입으로 전환. 이후엔 대시보드·API로 값 조회 불가 — 다시 보고 싶으면 회전이 유일한 경로.

> **Vercel 공식 제약:** sensitive 타입은 **production + preview** 타겟에만 지원. development 타겟은 불가. toolkit은 development에 대해 자동으로 `encrypted`로 fallback.

### Step 4 — 회전 이후 ([`runbooks/04-after-rotation.md`](runbooks/04-after-rotation.md) 참조)

- 각 프로젝트에서 `vercel env pull` — 로컬 `.env` 갱신
- `vercel --prod` 프로젝트마다 — warm serverless 강제 cold-start (기존 값 붙잡고 있는 인스턴스 정리)
- CI/CD secret mirror 업데이트 (GitHub Actions 등)
- 모든 [Deploy Hook](https://vercel.com/docs/deployments/deploy-hooks) URL 회전
- 30일간 주간 `scripts/audit.py` — 예기치 않은 새 env var·프로젝트 diff 감시

---

## 위협 모델 — Vercel 아키텍처와 정합

[Vercel sensitive env var 문서](https://vercel.com/docs/environment-variables/sensitive-environment-variables) 기준:

| 타입 | 복호화 키 위치 | 침해 시 가정 |
|---|---|---|
| `plain` | 어디에도 없음 — 평문 저장 | **유출 가정** |
| `encrypted` | Vercel 내부 KMS — 대시보드·런타임용으로 서버 측 복호화 | 내부 시스템까지 침투한 침해면 **유출 가정** |
| `sensitive` | 제한 경로 — *"생성 후 읽기 불가"*, 대시보드·API에서 반환하지 않음 | 빌드/런타임 샌드박스까지 뚫리지 않았다면 **살아있을 가능성** |

따라오는 규칙:
1. 유출된 값은 회전 > 하드닝. 하드닝은 이미 유출된 값을 보존할 뿐.
2. sensitive가 만능은 아님 — 빌드 타임 접근이면 빌드 인프라 침투 시 노출.
3. 공식 문서: *"기존 env var를 sensitive로 바꾸려면 remove + re-add"* — 타입 변경은 in-place edit 아님.

---

## 이 toolkit이 맞는 대상

**좋은 fit**
- Next.js / Remix / SvelteKit / Nuxt 앱 몇 개를 Vercel에 운영
- 몇 시간 아닌 몇 분 안에 반복 가능한 1차 대응 원함
- 흔한 auth(Auth.js / NextAuth / Clerk / Supabase Auth) + DB(Supabase / Neon / Postgres) 스택

**부분 fit**
- 비-JS 스택 — Flow A(감사)는 범용. Flow C(자동 회전)는 나열된 키만. `--include`로 본인 프레임워크의 안전한 랜덤 키 추가
- 커스텀 JWE / 필드 수준 암호화 / 회전이 데이터 접근 불가로 이어지는 세션 설계 — 수동으로

**맞지 않음**
- 컴플라이언스 artifact(SOC 2, ISO 27001) — 이건 operator playbook이지 감사 증적 아님
- Change Advisory Board 통과 프로세스 — 여기 모든 mutation은 즉시 실행

**toolkit이 잡지 못하는 것 (수동 필요)**
- 과거 프로덕션 배포에 이미 박힌 악성 코드 → `vercel ls --prod` + git SHA diff
- 소셜 엔지니어링으로 추가된 팀원 → Audit Log 리뷰
- 잊어버린 다른 디바이스의 토큰 → 대시보드에서 전체 revoke
- 연결된 외부 서비스의 2차 침해 → 벤더별 audit log 각각 확인

의심스러우면 toolkit 출력을 "끝난 증거"가 아닌 "검증 체크리스트"로 다루세요.

---

## 4가지 flow

### A. Audit — `scripts/audit.py`
모든 스코프(개인 + 팀)의 모든 프로젝트 env var를 열거·분류 (`OK` sensitive / `HIGH` 고위험 encrypted / `MED` 일반 encrypted / `LOW-PLAIN` 평문). 읽기 전용. `~/.vercel-security/audit-<timestamp>.json`에 기록.

### B. Harden — `scripts/harden-to-sensitive.py`
모든 non-sensitive env var를 값 유지한 채 `sensitive`로 전환. [공식 sensitive 문서](https://vercel.com/docs/environment-variables/sensitive-environment-variables) 준수. 평문 획득은 `vercel env pull`, 이후 공식 `DELETE` + `POST` 사용. `NEXT_PUBLIC_*` 스킵. development 타겟은 Vercel 제약상 `encrypted`로 fallback. Dry-run 디폴트.

### C. Incident — `scripts/rotate-internal.py` + `handoff-gen.py`

내부 랜덤 시크릿 자동 회전. Vercel `PATCH /v9/projects/.../env/<id>` endpoint 사용해 값만 atomic in-place 업데이트 — env id와 타입 그대로 유지, 변수 없는 window 없음. 기본 리스트:

| 키 | 용도 |
|---|---|
| `NEXTAUTH_SECRET` / `AUTH_SECRET` | NextAuth / Auth.js 세션 JWT |
| `SESSION_SECRET` / `COOKIE_SECRET` | Remix / Express / Hono / Fastify 세션 서명 |
| `PAYLOAD_SECRET` | PayloadCMS |
| `PREVIEW_SECRET` / `REVALIDATION_SECRET` | Next.js preview / on-demand ISR |
| `CRON_SECRET` | Vercel Cron 인증 |
| `API_KEY_HMAC_SECRET` / `HMAC_SECRET` | 내부 API HMAC 서명 |
| `ADMIN_PASSWORD` | 단순 admin — **새 값 stdout 1회만 출력, 저장 0** |

`--include KEY1,KEY2`로 확장 가능. `NEVER_ROTATE_PATTERNS`에 매칭되는 건 **거부** (at-rest 암호화, 벤더 시크릿, 장기 JWT 서명 키 — 회전하면 stateful 데이터 손상).

`handoff-gen.py`는 `~/security-incident-<YYYY-MM>-vercel/<project>.md`에 프로젝트별 마크다운 작성. 평문 값은 포함 X.

### D. 벤더 회전 — `scripts/update-env.py`
벤더 대시보드에서 키 회전 후:
```bash
python3 scripts/update-env.py <project> <KEY> --from-stdin --apply
```
Vercel [안전 회전 패턴](https://vercel.com/docs/environment-variables/rotating-secrets) 준수 — 새 값 업로드(프로덕션/프리뷰는 `sensitive`, development는 `encrypted`), 선택적 `--redeploy`로 즉시 재배포, `~/.vercel-security/rotations.json`에 로깅 (평문 없음).

**순서 중요:** Vercel에 새 값 업로드 → 재배포 검증 → **그 후** 벤더 기존 키 무효화. 공식 문서: *"안전한 회전의 핵심은 기존 credential을 무효화하기 전에 Vercel을 업데이트하는 것"*.

---

## `.gitignore` 두 종류 — 헷갈리지 마세요

이 toolkit 레포의 `.gitignore`는 **기여자가 toolkit 개발 중 발생하는 artifact**를 커밋하지 않도록 방지.

여러분의 **Vercel 배포 앱 레포**에도 ignore 패턴이 필요 — `vercel env pull`이나 handoff 문서가 실수로 git에 들어가지 않도록. 각 앱 레포마다 한 번:

```bash
python3 scripts/ignore-setup.py /path/to/your/app-repo
```

`.gitignore`, `.vercelignore`, `.dockerignore`, `.npmignore`에 패턴 추가. 멱등적 — 이미 있으면 건너뜀.

기본적으로 toolkit 출력은 `~/.vercel-security/` + `~/security-incident-*-vercel/` — 모든 레포 바깥. ignore 패턴은 여러분이 handoff 문서를 레포로 복사하는 상황에 대한 belt-and-suspenders.

---

## 공급망 & 공격자 모델

공격자가 이 레포 모든 줄 읽었다고 가정.

**배우는 것**: 시크릿 분류용 키 네임 패턴, 로컬 Vercel CLI auth 파일 경로, 사용 Vercel API endpoint 집합. 전부 Vercel 공식 문서에도 있음.

**배우지 못하는 것**: 여러분의 토큰(런타임에만 읽음, 임베드 X), 프로젝트명/ID, 회전 로그, 평문 값.

**스크립트의 구조적 안전 속성**
- 시크릿 값은 `getpass`로만 받음 (CLI args는 shell history에 남음)
- Vercel CLI 토큰을 절대 출력·로그하지 않음 (에러 시에도)
- 평문 회전 값을 절대 disk에 쓰지 않음 (`ADMIN_PASSWORD` 포함 — stdout 1회)
- `~/.vercel-security/`, `~/security-incident-*-vercel/`, 그리고 명시된 타겟 레포 외 path에 읽기/쓰기 X
- `api.vercel.com` 외 어떤 네트워크 호출도 X
- 멱등 API 호출은 429/5xx에서 exponential backoff 재시도; 4xx는 재시도 안 함

**공급망**
- Python stdlib만 사용. `requirements.txt`도 npm도 외부 import도 없음. 여러분 카피에 이런 게 있으면 변조된 것.
- 릴리스는 태그로 고정: `git checkout v0.1.0`.
- fork는 diff 감사 후 실행. 낯선 fork의 main을 clone하지 말 것.

fork해서 이 속성 중 하나라도 약화시킬 거면 README 최상단에 **크게** 명시. 사용자가 diff 읽지 않고도 안전성 변경을 알 수 있어야.

---

## Runbook

프로세스
- [`00-incident-response.md`](runbooks/00-incident-response.md) — 분 단위 playbook
- [`01-prevention-hardening.md`](runbooks/01-prevention-hardening.md) — Vercel 보안 설정 (Git Fork Protection, Deploy Protection, Enforce Sensitive policy, OIDC)
- [`02-common-mistakes.md`](runbooks/02-common-mistakes.md) — 자주 하는 실수 / 피해야 할 것
- [`03-post-incident-monitoring.md`](runbooks/03-post-incident-monitoring.md) — 주간 audit, canary, 종료 시점
- [`04-after-rotation.md`](runbooks/04-after-rotation.md) — toolkit 끝난 후 **진짜 "완료" 의미**

벤더별
- [Supabase](runbooks/vendor-supabase.md)
- [Google OAuth](runbooks/vendor-google-oauth.md)
- [Neon / Postgres](runbooks/vendor-neon.md)
- [일반 써드파티 API](runbooks/vendor-generic.md)

---

## 신뢰 가능한 참조 (공식 + 검증된 것)

Vercel 공식 (이 README보다 항상 공식 문서를 우선):
- [Vercel 2026년 4월 보안 사고 — KB bulletin](https://vercel.com/kb/bulletin/vercel-april-2026-security-incident)
- [환경변수 회전 — 공식 패턴](https://vercel.com/docs/environment-variables/rotating-secrets)
- [Sensitive 환경변수](https://vercel.com/docs/environment-variables/sensitive-environment-variables)
- [환경변수 개요](https://vercel.com/docs/environment-variables)
- [프로젝트 보안 설정](https://vercel.com/docs/project-configuration/security-settings)
- [Tokens](https://vercel.com/docs/sign-in-with-vercel/tokens)
- [Deploy Protection](https://vercel.com/docs/deployment-protection)
- [OIDC Federation](https://vercel.com/docs/oidc) — AWS/GCP 장기 키를 단기 토큰으로

검증된 3rd party
- [GitGuardian — Vercel API access token 유출 remediation](https://www.gitguardian.com/remediation/vercel-api-access-token)

이 README는 의도적으로 검증되지 않은 블로그는 인용하지 않아요. 여기 나열되지 않은 소스는 교차 검증이 부족했다는 뜻.

---

## License

MIT.
