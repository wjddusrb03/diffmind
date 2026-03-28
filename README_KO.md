# DiffMind - AI 코드 리뷰 메모리

> [English README](README.md)

**DiffMind**는 팀의 버그 히스토리를 학습하고, 새로운 코드 변경에서 유사한 패턴이 발견되면 자동으로 경고하는 도구입니다.

## 왜 DiffMind인가?

```
ESLint:     "변수를 사용하기 전에 선언하세요"           (일반 규칙)
DiffMind:   "이 패턴은 2달 전 PR #142에서 수정한 버그와 93% 유사합니다"  (팀 고유 경험)
```

기존 도구는 **일반적인 규칙**을 검사하지만, DiffMind는 **우리 팀이 과거에 실제로 실수한 패턴**을 기억하고 경고합니다.

## 작동 원리

```
git diff → 변경된 코드를 벡터 임베딩 (sentence-transformers)
     ↓
과거 버그 수정 히스토리와 비교 (TurboQuant 압축)
     ↓
"이 패턴은 3개월 전 PR #142에서 버그였습니다" 경고
     ↓
VS Code Problems 패널 / 터미널 / git hook으로 자동 표시
```

---

## 설치

### CLI 설치

```bash
git clone https://github.com/wjddusrb03/diffmind.git
cd diffmind
pip install -e .
```

### VS Code 확장 설치

```bash
cd vscode-extension
npm install && npm run compile
npx @vscode/vsce package --no-dependencies
code --install-extension diffmind-0.1.1.vsix
```

설치 후 VS Code를 **재시작**하면 하단 상태바에 `🛡 DiffMind`가 나타납니다.

---

## VS Code 사용법 (단계별 가이드)

### Step 1: 프로젝트 열기

VS Code에서 **git 저장소**가 있는 프로젝트 폴더를 엽니다.

```
파일(F) → 폴더 열기 → git 프로젝트 폴더 선택
```

> DiffMind는 git 커밋 히스토리를 분석합니다. `git init`된 프로젝트에서만 작동합니다.

### Step 2: 히스토리 학습 (최초 1회)

```
Ctrl+Shift+P → "DiffMind: Learn" 입력 → Enter
```

- 날짜를 묻는 입력창이 뜹니다
- **빈칸으로 Enter** = 전체 히스토리 학습
- `2024-01-01` 입력 = 2024년 이후 커밋만 학습

학습이 완료되면:
- 하단 상태바: `🛡 DiffMind: Ready`
- 팝업: "DiffMind Learn complete!" 메시지

> 커밋이 많을수록 더 정확합니다. 최소 5~10개 이상의 커밋이 있어야 효과적입니다.

### Step 3: 코드 수정 후 리뷰

파일을 수정한 후:

```
Ctrl+Shift+D
```

**결과 확인 방법:**

| 위치 | 내용 |
|---|---|
| **하단 상태바** | `✓ DiffMind: Clean` (문제없음) 또는 `⚠ DiffMind: N warnings` |
| **Problems 패널** (`Ctrl+Shift+M`) | 파일별 경고 목록 (빨간색=HIGH, 노란색=MEDIUM) |
| **경고 팝업** | "Show Details" 또는 "Show Problems" 버튼 |

### Step 4: 버그 히스토리 검색

```
Ctrl+Shift+F6
```

검색어 입력 예시:
- `"null check"` - null 관련 버그 검색
- `"API 오류"` - API 관련 문제 검색
- `"로그인 버그"` - 인증 관련 버그 검색

Output 패널에 유사도 순으로 결과가 표시됩니다.

### Step 5: 통계 확인

```
Ctrl+Shift+P → "DiffMind: Stats"
```

Output 패널에 표시되는 정보:
- 총 커밋 수, 버그 수정 비율
- 가장 버그가 많은 파일 Top 5
- 메모리 사용량 (원본 vs 압축)

### Step 6: 자동 리뷰 켜기 (선택)

```
Ctrl+Shift+P → "DiffMind: Toggle Auto-Review on Save"
```

켜면 **파일 저장할 때마다** 자동으로 리뷰가 실행됩니다.

### 우클릭 메뉴

에디터에서 **우클릭**하면 DiffMind 메뉴 3개가 보입니다:
- Review Current Changes
- AI Review
- Search Bug History

---

## VS Code 단축키 요약

| 단축키 | 기능 | 설명 |
|---|---|---|
| `Ctrl+Shift+D` | **리뷰** | 현재 변경사항을 과거 버그와 비교 |
| `Ctrl+Shift+A` | **AI 리뷰** | LLM이 분석 + 수정 코드 제안 |
| `Ctrl+Shift+F6` | **검색** | 버그 히스토리 의미 기반 검색 |
| `Ctrl+Shift+M` | **Problems** | 경고 목록 보기 (VS Code 기본) |
| `Ctrl+Shift+P` | **명령어** | DiffMind 명령어 검색 |

---

## VS Code 설정

`Ctrl+,` → "diffmind" 검색:

| 설정 | 기본값 | 설명 |
|---|---|---|
| `diffmind.pythonPath` | `python` | Python 경로 |
| `diffmind.autoReviewOnSave` | `false` | 저장 시 자동 리뷰 |
| `diffmind.threshold` | `0.75` | 유사도 임계값 (낮출수록 경고 많아짐) |
| `diffmind.aiProvider` | `claude` | AI 리뷰 제공자 (claude/openai/ollama) |
| `diffmind.aiLanguage` | `en` | AI 리뷰 언어 (`ko`로 바꾸면 한국어) |
| `diffmind.maxWarningsPerHunk` | `3` | 코드 덩어리당 최대 경고 수 |
| `diffmind.showStatusBar` | `true` | 상태바 표시 여부 |

---

## CLI 사용법

### 빠른 시작

```bash
# 1. 저장소 히스토리 학습 (최초 1회)
diffmind learn .

# 2. 현재 변경사항 리뷰
diffmind review

# 3. 스테이징된 변경사항만 리뷰
diffmind review --staged

# 4. JSON 출력 (CI 연동용)
diffmind review --json

# 5. 과거 변경사항 검색
diffmind search "null check 누락"

# 6. 통계 조회
diffmind stats

# 7. pre-commit 훅 설치 (커밋마다 자동 리뷰)
diffmind install --pre-commit

# 8. GitHub Action 생성
diffmind install --github-action
```

### 전체 명령어

| 명령어 | 설명 |
|---|---|
| `diffmind learn [경로]` | git 히스토리에서 버그 패턴 학습 |
| `diffmind review` | 현재 변경사항을 과거 버그 패턴과 비교 리뷰 |
| `diffmind search "쿼리"` | diff 히스토리에서 의미 기반 검색 |
| `diffmind stats` | 인덱스 통계 표시 |
| `diffmind install` | git hook / GitHub Action 설치 |

### 상세 옵션

#### `diffmind learn`

| 옵션 | 설명 | 예시 |
|---|---|---|
| `--since 날짜` | 지정 날짜 이후만 학습 | `--since 2024-01-01` |
| `--until 날짜` | 지정 날짜 이전만 학습 | `--until 2024-12-31` |
| `--branch 브랜치` | 특정 브랜치만 학습 | `--branch main` |
| `--bugfix-only` | 버그 수정 커밋만 학습 | |
| `--model 모델명` | 임베딩 모델 지정 | `--model all-MiniLM-L6-v2` |
| `--bits N` | 압축 비트 (2, 3, 4) | `--bits 3` (기본) |
| `--update` | 증분 학습 (새 커밋만 추가) | |

#### `diffmind review`

| 옵션 | 설명 | 예시 |
|---|---|---|
| `--staged` | 스테이징된 변경사항만 | |
| `--threshold N` | 유사도 임계값 (0~1) | `--threshold 0.80` |
| `-k N` | 경고당 최대 유사 항목 수 | `-k 5` |
| `--fail-on 레벨` | 위험도 이상 시 종료 코드 1 | `--fail-on high` |
| `--json` | JSON 형식 출력 | |

#### `diffmind search`

| 옵션 | 설명 | 예시 |
|---|---|---|
| `-k N` | 결과 수 | `-k 10` |
| `--file 경로` | 파일 경로로 필터 | `--file src/auth/` |
| `--author 이름` | 작성자로 필터 | `--author "홍길동"` |
| `--lang 언어` | 프로그래밍 언어로 필터 | `--lang python` |
| `--bugfix-only` | 버그 수정 커밋만 검색 | |

---

## 실전 활용 시나리오

### 개인 개발자

```bash
# 매일 작업 루틴
git add .
diffmind review --staged     # 커밋 전 확인
git commit -m "feat: ..."
```

### 팀 개발 (pre-commit 훅)

```bash
# 팀 리더가 한 번 설정
diffmind learn . --since 2024-01-01
diffmind install --pre-commit

# 이후 모든 팀원의 커밋에서 자동 리뷰
git commit -m "update handler"
# → DiffMind: reviewing staged changes...
# → [!!!] HIGH RISK: 이 패턴은 PR #142의 버그와 93% 유사
```

### CI/CD (GitHub Action)

```yaml
# .github/workflows/diffmind.yml
name: DiffMind Review
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install & Review
        run: |
          pip install diffmind
          diffmind learn . --since 6months
          diffmind review --staged --fail-on high
```

---

## 버그 감지 방식

DiffMind는 다음 기준으로 버그 수정 커밋을 식별합니다:

| 기준 | 예시 |
|---|---|
| Conventional Commits | `fix:`, `bugfix:`, `hotfix:` 접두사 |
| 이슈 참조 | `fix #123`, `closes #456`, `resolves #789` |
| 키워드 | `fix`, `bug`, `resolve`, `수정`, `버그` |
| PR 라벨 | `bug`, `hotfix` |
| Revert 커밋 | 되돌린 커밋은 버그 수정으로 분류 |

## 위험도 분류

| 위험도 | 조건 | VS Code 표시 | 의미 |
|---|---|---|---|
| **HIGH** | 유사도 ≥ 90% + 버그 수정 커밋 | 빨간색 에러 | 과거 버그와 매우 유사 |
| **MEDIUM** | 유사도 ≥ 80% + 버그 수정 커밋 | 노란색 경고 | 주의 필요 |
| **LOW** | 유사도 ≥ 75% | 파란색 정보 | 참고용 |

---

## 다른 도구와의 비교

| 도구 | 하는 일 | DiffMind가 하는 일 |
|---|---|---|
| ESLint/Pylint | 일반적인 규칙 위반 검사 | **팀 고유** 버그 패턴 학습 |
| GitHub Copilot | 코드 생성 | 버그 패턴 **기억** + 수정 제안 |
| CodeRabbit | 일반적인 AI 리뷰 | **프로젝트별** 학습 기반 리뷰 |
| SonarQube | 정적 분석 | **의미 기반** 유사도 분석 |
| `git log --grep` | 키워드 검색 | **의미** 기반 검색 |

---

## 프로젝트 구조

```
src/diffmind/
├── cli.py              # CLI (learn, review, search, stats, install)
├── models.py           # DiffHunk, ReviewWarning 등 데이터 모델
├── parser.py           # Git 로그/diff 파서, 버그 감지
├── indexer.py          # 임베딩 + TurboQuant 압축
├── reviewer.py         # 유사도 기반 리뷰 엔진
├── searcher.py         # 의미 기반 검색
├── storage.py          # 인덱스 저장/불러오기 (.diffmind/index.pkl)
├── display.py          # 터미널 + JSON 포맷팅
└── hooks.py            # Git hook + GitHub Action 생성

vscode-extension/
├── src/extension.ts    # VS Code 확장 (TypeScript)
└── package.json        # 확장 매니페스트

tests/                  # 318개 테스트
```

## 기술 스택

- [langchain-turboquant](https://pypi.org/project/langchain-turboquant/) - 3비트 벡터 양자화/압축
- [sentence-transformers](https://www.sbert.net/) - all-MiniLM-L6-v2 임베딩 (384차원)
- [Click](https://click.palletsprojects.com/) - CLI 프레임워크
- NumPy - 벡터 연산
- TypeScript - VS Code Extension API

## 테스트

```bash
pytest tests/ -v
```

## 자주 묻는 질문

**Q: "No diff hunks found" 에러가 나와요**
A: git 커밋이 너무 적은 프로젝트입니다. 최소 3~5개 이상의 커밋이 있어야 합니다.

**Q: 학습에 시간이 오래 걸려요**
A: `--since 2024-01-01`처럼 기간을 제한하면 빨라집니다.

**Q: VS Code에서 경고가 안 보여요**
A: `Ctrl+Shift+P` → `Developer: Reload Window` 후 다시 시도해보세요.

**Q: AI 리뷰는 어떻게 사용하나요?**
A: `ANTHROPIC_API_KEY` 또는 `OPENAI_API_KEY` 환경변수 설정 후 `Ctrl+Shift+A`를 누르세요.

## 라이선스

MIT
