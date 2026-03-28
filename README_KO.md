# DiffMind - AI 코드 리뷰 메모리

**DiffMind**는 팀의 버그 히스토리를 학습하고, 새로운 코드 변경에서 유사한 패턴이 발견되면 경고하는 CLI 도구입니다.

> [English README](README.md)

## 작동 원리

```
git diff → 변경된 코드를 벡터 임베딩
     ↓
과거 버그 수정 히스토리와 비교 (TurboQuant 압축)
     ↓
"이 패턴은 3개월 전 PR #142에서 버그였습니다" 경고
     ↓
git hook 또는 GitHub Action으로 자동 실행
```

## 설치

```bash
# 소스에서 설치
git clone https://github.com/wjddusrb03/diffmind.git
cd diffmind
pip install -e .
```

### 필수 패키지

- Python 3.9 이상
- [langchain-turboquant](https://pypi.org/project/langchain-turboquant/) - 벡터 압축
- [sentence-transformers](https://www.sbert.net/) - 임베딩 모델
- [Click](https://click.palletsprojects.com/) - CLI 프레임워크

## 빠른 시작

```bash
# 1. 저장소 히스토리 학습 (최초 1회)
diffmind learn . --since 2024-01-01

# 2. pre-commit 훅 설치 (최초 1회)
diffmind install --pre-commit

# 3. 이제 모든 커밋이 자동으로 리뷰됩니다!
git commit -m "로그인 수정"
# DiffMind: reviewing staged changes...
# [!!!] HIGH RISK: src/auth/login.py (93% similar to bugfix a1b2c3d)

# 4. 수동 리뷰
diffmind review --staged

# 5. 과거 변경사항 검색
diffmind search "null check 누락" --lang python

# 6. 통계 조회
diffmind stats

# 7. 증분 업데이트 (새 커밋만 학습)
diffmind learn --update
```

## 명령어

| 명령어 | 설명 |
|---|---|
| `diffmind learn [경로]` | git 히스토리에서 버그 패턴 학습 |
| `diffmind review` | 현재 변경사항을 과거 버그 패턴과 비교 리뷰 |
| `diffmind search 쿼리` | diff 히스토리에서 의미 기반 검색 |
| `diffmind stats` | 인덱스 통계 표시 |
| `diffmind install` | 자동화 훅 설치 |

## 주요 기능

- **팀 버그 메모리**: 일반 규칙이 아닌, 팀 고유의 버그 패턴을 학습
- **의미 기반 검색**: 키워드가 아닌 의미로 검색 ("인증 오류"로 auth 관련 버그 탐색)
- **TurboQuant 압축**: 대형 저장소에서 ~2배 메모리 절약
- **비대칭 스코어링**: 벡터 압축 해제 없이 바로 검색
- **Git Hook / GitHub Action**: 모든 커밋이나 PR에서 자동 리뷰
- **증분 학습**: `--update` 옵션으로 새 커밋만 추가 학습
- **다중 언어 지원**: Python, JavaScript, TypeScript, Java, Go, Rust, C/C++ 등 30+ 언어

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

```bash
diffmind learn [경로] [옵션]
```

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

```bash
diffmind review [옵션]
```

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `--staged` | 스테이징된 변경사항만 리뷰 | False |
| `--threshold N` | 유사도 임계값 | 0.75 |
| `-k N` | 경고당 최대 유사 항목 수 | 3 |
| `--fail-on 레벨` | 지정 위험도 이상 시 exit code 1 | 없음 |
| `--json` | JSON 형식 출력 (CI 연동용) | False |
| `--path 경로` | 대상 저장소 경로 | 현재 디렉토리 |

### `diffmind search`

```bash
diffmind search "검색어" [옵션]
```

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `-k N` | 결과 수 | 5 |
| `--file 경로` | 파일 경로로 필터 | 없음 |
| `--author 이름` | 작성자로 필터 | 없음 |
| `--lang 언어` | 프로그래밍 언어로 필터 | 없음 |
| `--bugfix-only` | 버그 수정 커밋만 검색 | False |
| `--path 경로` | 대상 저장소 경로 | 현재 디렉토리 |

### `diffmind install`

```bash
diffmind install [옵션]
```

| 옵션 | 설명 |
|---|---|
| `--pre-commit` | git pre-commit 훅 설치 |
| `--github-action` | GitHub Action 워크플로우 생성 |
| `--fail-on 레벨` | 자동 리뷰 실패 기준 (high/medium/low) |
| `--path 경로` | 대상 저장소 경로 |

## CI/CD 연동

### GitHub Action 자동 설치

```bash
diffmind install --github-action
```

이 명령은 `.github/workflows/diffmind.yml` 파일을 생성하여, 모든 PR에서 자동으로 DiffMind 리뷰가 실행되도록 합니다.

### JSON 출력으로 파이프라인 연동

```bash
diffmind review --staged --json --fail-on high
```

```json
{
  "total_hunks": 3,
  "warning_count": 1,
  "warnings": [
    {
      "file": "src/auth/login.py",
      "risk": "HIGH",
      "similarity": 0.93,
      "reason": "이 변경은 3개월 전 a1b2c3d 커밋에서 수정된 버그와 93% 유사합니다."
    }
  ]
}
```

## 다른 도구와의 비교

| 도구 | 하는 일 | DiffMind가 하는 일 |
|---|---|---|
| ESLint/Pylint | 일반적인 규칙 위반 검사 | 팀 고유 패턴 학습 |
| GitHub Copilot | 코드 생성 | 버그 패턴 기억 |
| CodeRabbit | 일반적인 AI 리뷰 | 프로젝트별 학습 |
| SonarQube | 정적 분석 | 의미 기반 유사도 검색 |
| `git log --grep` | 키워드 검색 | 의미 기반 검색 |

## 기술 스택

- **[langchain-turboquant](https://pypi.org/project/langchain-turboquant/)** - 3비트 벡터 양자화/압축으로 메모리 절약
- **[sentence-transformers](https://www.sbert.net/)** - all-MiniLM-L6-v2 모델로 코드 diff 임베딩
- **[Click](https://click.palletsprojects.com/)** - CLI 프레임워크
- **NumPy** - 벡터 연산

## 라이선스

MIT
