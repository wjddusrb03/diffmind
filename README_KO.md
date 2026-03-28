# DiffMind - AI 코드 리뷰 메모리

> [English README](README.md)

**DiffMind**는 팀의 버그 히스토리를 학습하고, 새로운 코드 변경에서 유사한 패턴이 발견되면 LLM이 분석하여 수정 코드까지 제안하는 도구입니다.

## 작동 원리

```
git diff → 변경된 코드를 벡터 임베딩 (sentence-transformers)
     ↓
과거 버그 수정 히스토리와 비교 (TurboQuant 압축)
     ↓
"이 패턴은 3개월 전 PR #142에서 버그였습니다" 경고
     ↓
LLM이 분석 + 수정 코드 제안 (Claude / GPT / Ollama)
     ↓
VS Code / git hook / GitHub Action으로 자동 실행
```

## 설치

```bash
# 기본 CLI
git clone https://github.com/wjddusrb03/diffmind.git
cd diffmind
pip install -e .

# LLM 연동 포함 (Claude + OpenAI)
pip install -e ".[llm]"

# 전체 연동 포함 (GitHub, Slack, Discord)
pip install -e ".[connect]"
```

### VS Code 확장 설치

```bash
# .vsix 파일로 설치
cd vscode-extension
npm install && npm run compile
npx @vscode/vsce package --allow-missing-repository
code --install-extension diffmind-0.1.0.vsix
```

또는 VS Code에서 `vscode-extension` 폴더를 열고 `F5`를 눌러 디버그 모드로 실행할 수 있습니다.

## 빠른 시작

### CLI 사용법

```bash
# 1. 저장소 히스토리 학습 (최초 1회)
diffmind learn . --since 2024-01-01

# 2. 현재 변경사항 리뷰
diffmind review --staged

# 3. AI 리뷰 (LLM이 분석 + 수정 제안)
diffmind connect ai-review --staged --lang ko

# 4. 과거 변경사항 검색
diffmind search "null check 누락" --lang python

# 5. 통계 조회
diffmind stats

# 6. pre-commit 훅 설치 (커밋마다 자동 리뷰)
diffmind install --pre-commit
```

### VS Code 사용법

```
Ctrl+Shift+P → "DiffMind: Learn"        ← 최초 1회 설정
Ctrl+Shift+D                              ← 변경사항 리뷰
Ctrl+Shift+A                              ← AI 리뷰 (LLM 분석)
Ctrl+Shift+F6                             ← 버그 히스토리 검색
우클릭 → DiffMind 메뉴                    ← 컨텍스트 메뉴
```

## 전체 명령어

### 기본 CLI

| 명령어 | 설명 |
|---|---|
| `diffmind learn [경로]` | git 히스토리에서 버그 패턴 학습 |
| `diffmind review` | 현재 변경사항을 과거 버그 패턴과 비교 리뷰 |
| `diffmind search 쿼리` | diff 히스토리에서 의미 기반 검색 |
| `diffmind stats` | 인덱스 통계 표시 |
| `diffmind install` | git hook / GitHub Action 설치 |

### Connect (외부 연동)

| 명령어 | 설명 |
|---|---|
| `diffmind connect ai-review` | LLM이 경고를 분석하고 수정 코드 제안 |
| `diffmind connect github --pr N` | GitHub PR에 AI 리뷰 자동 게시 |
| `diffmind connect slack --test` | Slack 알림 전송 |
| `diffmind connect discord --test` | Discord 알림 전송 |
| `diffmind connect init` | 설정 파일 생성 |

### VS Code 확장

| 명령어 | 단축키 | 설명 |
|---|---|---|
| DiffMind: Learn | - | 저장소 히스토리 학습 |
| DiffMind: Review | `Ctrl+Shift+D` | 변경사항 리뷰 → Problems 패널 |
| DiffMind: Review Staged | - | 스테이징된 변경사항만 리뷰 |
| DiffMind: AI Review | `Ctrl+Shift+A` | LLM 분석 → WebView 패널 |
| DiffMind: Search | `Ctrl+Shift+F6` | 버그 히스토리 검색 |
| DiffMind: Stats | - | 통계 보기 |
| DiffMind: Toggle Auto-Review | - | 저장 시 자동 리뷰 켜기/끄기 |

## 주요 기능

- **팀 버그 메모리**: 일반 규칙이 아닌, 팀 고유의 버그 패턴을 학습
- **LLM 분석**: Claude/GPT/Ollama가 경고를 분석하고 수정 코드 제안
- **VS Code 연동**: 인라인 경고, WebView 패널, 상태바, 저장 시 자동 리뷰
- **의미 기반 검색**: 키워드가 아닌 의미로 검색 ("인증 오류"로 auth 관련 버그 탐색)
- **TurboQuant 압축**: 대형 저장소에서 ~2배 메모리 절약
- **GitHub PR 봇**: PR에 AI 리뷰 코멘트 자동 게시
- **Slack / Discord 알림**: 위험 패턴 발견 시 실시간 알림
- **Git Hook / GitHub Action**: 모든 커밋이나 PR에서 자동 리뷰
- **증분 학습**: `--update` 옵션으로 새 커밋만 추가 학습
- **이중 언어**: AI 리뷰를 영어/한국어로 출력
- **다중 언어 지원**: Python, JavaScript, TypeScript, Java, Go, Rust, C/C++ 등 30+ 언어

## AI 리뷰 (Connect)

DiffMind Connect는 패턴 감지와 LLM 분석을 결합합니다:

```bash
# Claude로 리뷰 (기본)
diffmind connect ai-review --staged

# OpenAI로 리뷰
diffmind connect ai-review --staged --provider openai

# 로컬 Ollama로 리뷰 (무료, 오프라인)
diffmind connect ai-review --staged --provider ollama

# 한국어 출력
diffmind connect ai-review --staged --lang ko

# CI용 JSON 출력
diffmind connect ai-review --staged --json --fail-on high
```

**출력 예시:**
```
============================================================
  DiffMind AI Review Report
  Provider: claude (claude-sonnet-4-20250514)
  Overall risk: HIGH
============================================================

[!!!] HIGH: src/auth/login.py
  Confidence: 95%

  Summary: user 객체가 None일 때 NoneType 에러 발생 가능

  Explanation:
    3개월 전 동일한 패턴에서 user.name 접근 시 NoneType 에러가
    발생했습니다. 현재 변경에서도 null 체크가 빠져있습니다.

  Suggestion: user 객체 검증 로직을 추가하세요.

  Suggested fix:
    if user is None:
        raise ValueError("User not found")
------------------------------------------------------------
```

## VS Code 확장 상세

### 화면 구성

- **상태바** (좌측 하단): `🛡 DiffMind` → 클릭하면 리뷰 실행
- **Problems 패널**: HIGH = 빨간 에러, MEDIUM = 노란 경고로 표시
- **WebView 패널**: AI 리뷰 결과를 보기 좋게 렌더링 (수정 코드 포함)
- **컨텍스트 메뉴**: 에디터에서 우클릭 → DiffMind 리뷰/검색

### VS Code 설정

`Ctrl+,` → "diffmind" 검색:

| 설정 | 기본값 | 설명 |
|---|---|---|
| `diffmind.pythonPath` | `python` | Python 경로 |
| `diffmind.autoReviewOnSave` | `false` | 저장 시 자동 리뷰 |
| `diffmind.threshold` | `0.75` | 유사도 임계값 (0~1) |
| `diffmind.aiProvider` | `claude` | LLM 제공자 (claude/openai/ollama) |
| `diffmind.aiLanguage` | `en` | AI 리뷰 출력 언어 (en/ko) |
| `diffmind.maxWarningsPerHunk` | `3` | 코드 덩어리당 최대 경고 수 |
| `diffmind.showStatusBar` | `true` | 상태바 표시 여부 |

## GitHub PR 봇

```bash
# PR에 AI 리뷰 코멘트 자동 게시
diffmind connect github --pr 42
```

### GitHub Action에서 자동 실행

```yaml
# .github/workflows/diffmind.yml
- name: AI Review
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: |
    diffmind learn . --since 6months
    diffmind connect ai-review --staged --json --fail-on high
```

## 알림 연동

```bash
# Slack 알림 설정
diffmind connect slack --test --webhook https://hooks.slack.com/services/...

# Discord 알림 설정
diffmind connect discord --test --webhook https://discord.com/api/webhooks/...
```

### 설정 파일

```bash
diffmind connect init
# → .diffmind/config.yml 생성
```

```yaml
llm:
  provider: claude          # claude, openai, ollama
  language: ko              # en 또는 ko
github:
  token: ""                 # 또는 GITHUB_TOKEN 환경변수
  repo: owner/repo
slack:
  webhook_url: ""
  min_risk: MEDIUM          # MEDIUM 이상만 알림
discord:
  webhook_url: ""
  min_risk: HIGH            # HIGH만 알림
```

## 버그 감지 방식

DiffMind는 다음 기준으로 버그 수정 커밋을 식별합니다:

1. **PR 라벨**: `bug`, `hotfix` 등
2. **이슈 참조**: `fix #123`, `closes #456` 등
3. **Conventional Commits**: `fix:`, `bugfix:`, `hotfix:` 접두사
4. **키워드**: `fix`, `bug`, `resolve`, `수정`, `버그` 등
5. **Revert 커밋**: 되돌린 커밋은 버그 수정으로 분류

## 위험도 분류

| 위험도 | 조건 | 의미 |
|---|---|---|
| **HIGH** | 유사도 ≥ 90% + 버그 수정 커밋 | 과거 버그와 매우 유사한 패턴 |
| **MEDIUM** | 유사도 ≥ 80% + 버그 수정 커밋 | 주의가 필요한 패턴 |
| **LOW** | 유사도 ≥ 75% | 참고용 유사 변경사항 |

## 상세 옵션

### `diffmind learn`

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `--since 날짜` | 지정 날짜 이후 커밋만 학습 | 전체 |
| `--until 날짜` | 지정 날짜 이전 커밋만 학습 | 현재 |
| `--branch 브랜치` | 특정 브랜치만 학습 | 현재 브랜치 |
| `--bugfix-only` | 버그 수정 커밋만 학습 | False |
| `--model 모델명` | 임베딩 모델 | all-MiniLM-L6-v2 |
| `--bits N` | 압축 비트 (2, 3, 4) | 3 |
| `--update` | 증분 학습 (새 커밋만) | False |

### `diffmind review`

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `--staged` | 스테이징된 변경사항만 리뷰 | False |
| `--threshold N` | 유사도 임계값 | 0.75 |
| `-k N` | 경고당 최대 유사 항목 수 | 3 |
| `--fail-on 레벨` | 지정 위험도 이상 시 exit code 1 | 없음 |
| `--json` | JSON 형식 출력 (CI 연동용) | False |

### `diffmind connect ai-review`

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `--provider` | LLM 제공자 (claude/openai/ollama) | claude |
| `--model 모델명` | 모델 직접 지정 | 자동 |
| `--lang` | 출력 언어 (en/ko) | en |
| `--json` | JSON 출력 | False |
| `--fail-on 레벨` | CI용 exit code | 없음 |

### `diffmind search`

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `-k N` | 결과 수 | 5 |
| `--file 경로` | 파일 경로로 필터 | 없음 |
| `--author 이름` | 작성자로 필터 | 없음 |
| `--lang 언어` | 프로그래밍 언어로 필터 | 없음 |
| `--bugfix-only` | 버그 수정 커밋만 검색 | False |

## 다른 도구와의 비교

| 도구 | 하는 일 | DiffMind가 하는 일 |
|---|---|---|
| ESLint/Pylint | 일반적인 규칙 위반 검사 | 팀 고유 버그 패턴 학습 |
| GitHub Copilot | 코드 생성 | 버그 패턴 기억 + 수정 제안 |
| CodeRabbit | 일반적인 AI 리뷰 | 프로젝트별 학습 + LLM 분석 |
| SonarQube | 정적 분석 | 의미 기반 유사도 + 수정 코드 |
| `git log --grep` | 키워드 검색 | 의미 기반 검색 |

## 프로젝트 구조

```
src/diffmind/
├── cli.py              # CLI (learn, review, search, stats, install, connect)
├── models.py           # DiffHunk, ReviewWarning, ReviewComment, ReviewReport
├── parser.py           # Git 로그/diff 파서, 버그 감지
├── indexer.py          # 임베딩 + TurboQuant 압축
├── reviewer.py         # 유사도 기반 리뷰 엔진
├── searcher.py         # 의미 기반 검색
├── storage.py          # 인덱스 저장/불러오기
├── display.py          # 터미널 + JSON 포맷팅
├── hooks.py            # Git hook + GitHub Action 생성
└── connect/
    ├── llm.py          # LLM 리뷰어 (Claude/OpenAI/Ollama)
    ├── github_bot.py   # GitHub PR 코멘트
    ├── slack.py        # Slack 알림
    ├── discord.py      # Discord 알림
    ├── config.py       # YAML 설정 + 환경변수
    └── prompts.py      # 이중 언어 프롬프트

vscode-extension/
├── src/extension.ts    # VS Code 확장
└── package.json        # 확장 매니페스트

tests/                  # 440개 테스트
```

## 기술 스택

**코어:**
- [langchain-turboquant](https://pypi.org/project/langchain-turboquant/) - 3비트 벡터 양자화/압축
- [sentence-transformers](https://www.sbert.net/) - all-MiniLM-L6-v2 임베딩
- [Click](https://click.palletsprojects.com/) - CLI 프레임워크
- NumPy - 벡터 연산

**Connect (선택):**
- [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python) - Claude API
- [OpenAI SDK](https://github.com/openai/openai-python) - OpenAI API
- [PyGithub](https://github.com/PyGithub/PyGithub) - GitHub API

**VS Code 확장:**
- TypeScript + VS Code Extension API

## 테스트

```bash
# 전체 440개 테스트 실행
pytest tests/ -v
```

## 라이선스

MIT
