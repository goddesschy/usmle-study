# [2026-06-09] USMLE Study System — 아키텍처 및 워크플로우

> 📅 **마지막 업데이트: 2026-06-09** — 문서를 편집할 때마다 위 제목의 날짜와 이 줄을 그날 날짜로 바꾸세요.
> (자동 갱신을 원하면 아래 "문서 날짜 자동 스탬프" 메모 참고)

## 시스템 구성

### 파일 구조
```
002. 공부 c AI 프로젝트\
    ├── usmle_server.py       로컬 HTTP 서버 (포트 8765)
    ├── index.html            브라우저 뷰어
    ├── config.txt            스캔할 폴더 경로 목록 ({USERNAME} 플레이스홀더)
    ├── flashcards.csv        Noji 가져오기용 암기카드 누적 파일 (자동 생성)
    ├── progress.json         채점 기록 로컬 저장 (자동 생성)
    ├── .env                  Anthropic API 키 (GitHub 제외)
    ├── .gitignore            .env / *.csv / progress.json 제외 설정
    └── .vscode\
            ├── settings.json
            ├── launch.json
            └── tasks.json    Ctrl+Shift+B 단축키 등록
```

### 외부 서비스
- **OneDrive**: PDF 파일 저장소 (집 PC 기준 약 105~120개)
- **GitHub**: https://github.com/goddesschy/usmle-study (코드 버전 관리)
- **Claude API**: api.anthropic.com (문제 분석·번역) — 별도 크레딧 필요
- **Noji**: noji.io — CSV 가져오기로 암기카드 연동 (공개 API 없음, 반자동)

---

## 데이터 흐름

```
OneDrive (PDF)
    ↓ 로컬 읽기
usmle_server.py (localhost:8765)
    ↓ HTTP
index.html (브라우저)
    ↓ POST /claude          POST /flashcard        GET /stats
Claude API 프록시       flashcards.csv 저장    progress.json 집계
    ↓                       ↓                      ↓
문제+해설+번역          Noji CSV 다운로드    통계 대시보드 표시
```

### 서버 엔드포인트
| 경로 | 설명 | 상태 |
|------|------|------|
| GET / | index.html 서빙 | ✅ 완료 |
| GET /health | 서버 상태 + API 키 여부 | ✅ 완료 |
| GET /subjects | 과목 목록 (config.txt 기반) | ✅ 완료 |
| GET /info?file=PATH | 파일 페이지 수 | ✅ 완료 |
| GET /page?file=PATH&p=N | N번째 페이지 JPEG | ✅ 완료 |
| POST /claude | Claude API 프록시 (CORS 우회) | ✅ 완료 |
| GET /crop?file=PATH&p=N&x=X&y=Y&w=W&h=H | 영역 크롭 → JPEG 반환 (+auto=1) | ✅ 완료 |
| POST /flashcard | 암기카드 1장 → flashcards.csv 추가 | 예정 |
| GET /flashcards.csv | CSV 다운로드 (Noji 가져오기용) | 예정 |
| GET /stats | 전체 진도·통계 JSON 반환 | 예정 |
| POST /progress | 채점 결과 저장 (progress.json) | 예정 |

---

## PDF 파일 형식

| 형식 | 예시 | 처리 방법 |
|------|------|-----------|
| ZIP+JPEG | `1_PDFsam_Neurology_390q.pdf` | zipfile로 직접 읽기 |
| 일반 PDF | `Neurology 390q.pdf` (590MB) | pymupdf로 렌더링 |

> **ZIP+JPEG 내부 구조**: 청크당 80페이지 이미지 + txt(비어있음) + manifest.json.
> 파일명 접두어(1, 81, 161…)는 원본 페이지 시작 번호.

### 문제 경계 식별 규칙
- 각 페이지 헤더: `Item X of 40` + `Question Id: NNNN`
- 같은 Question Id 연속 = 한 문제 (문제 1장 + 해설 N장)
- 40문제마다 Item 번호 리셋 → 블록 경계 검출 가능

---

## 일상 사용법

### 공부 시작
1. VS Code → 프로젝트 폴더 → `Ctrl+Shift+B` → 서버 실행
2. 브라우저 `http://localhost:8765`
3. 과목 선택 → Item 번호 입력 → 불러오기
4. 문제 풀기 → 정답/해설 보기 → 채점
5. 💬 Claude 질문 버튼 → 오른쪽 채팅 패널
6. 📇 Noji 카드 저장 버튼 → 틀린/중요 문제 암기카드 생성
7. 주 1회: Noji 앱 → Import Cards → `flashcards.csv` 업로드

### 코드 업데이트 & 병원 PC 동기화
```bash
git add . && git commit -m "변경 내용" && git push   # 집
git pull                                              # 병원
```
> config.txt의 `{USERNAME}` 플레이스홀더가 집(USER)·병원(godde) 자동 처리

---

## 설치 요구사항
- Python 3.x
- `pip install pymupdf pillow numpy`
- Git + Anthropic API 키 (`.env`) + API 크레딧

---

## 현재 상태 (2026-06-09)

### ✅ 완료
- [x] 로컬 서버 + 집·병원 PC 양쪽 동작
- [x] config.txt `{USERNAME}` 플레이스홀더
- [x] GitHub 연동 + VS Code `Ctrl+Shift+B`
- [x] index.html 뷰어 (과목·문제번호·페이지)
- [x] Claude API 프록시 (CORS 해결)
- [x] `.env` 로딩 버그 해결 (utf-8-sig + 따옴표 제거)
- [x] API 크레딧 충전 + `/claude` 스모크 테스트 성공
- [x] 오른쪽 사이드 채팅 패널 (멀티턴, 문제 컨텍스트 자동 포함)
- [x] Neurology 문제 색인 완성 (194문제, 5블록) — 헤더 OCR로 자동 생성, `Neurology_index.json`
- [x] **B-1 `/crop` 엔드포인트** — 좌표/자동 크롭, usmle_server.py에 통합, 실제 PDF로 검증

### 📋 예정
- [ ] **B-2** Claude 좌표 추출 ← 다음 작업 (색 기반 자동탐지의 MRI·표·형식 한계 해결)
- [ ] **B-3** 표·Exhibit 팝업 처리
- [ ] **B-4** 뷰어 해설에 그림 인라인 표시 (현재는 "이미지 있음" 텍스트만 나옴)
- [ ] Noji 암기카드 연동 (N-1 ~ N-3)
- [ ] 전체 통계 + 준비도 대시보드 (S-1 ~ S-4)
- [ ] Google Sheets 진도 기록
- [ ] 오답 기반 유사문제 생성

---

## 개발 로드맵 — 하루 1시간 단위

> 원칙: 하루 1시간 안에 시작·완료·커밋. 모든 작업은 독립적으로 완결.

---

### Phase 1 — 기반 완료 ✅

| # | 작업 | 완료 기준 |
|---|---|---|
| ✅ 1 | API 크레딧 충전 + 스모크 테스트 | `/claude` Hello 왕복 성공 |
| ✅ 2 | 오른쪽 채팅 사이드 패널 | 멀티턴, 문제 컨텍스트 자동 포함 |

---

### Phase 2 — 그림/표 크롭 자동화 (B 방식)

| # | 작업 | 완료 기준 |
|---|---|---|
| ✅ 3 | **B-1** `/crop` 서버 엔드포인트 | `?file&p&x&y&w&h` → 크롭 JPEG 반환 (+`auto=1` 자동탐지) — 완료 |
| 4 | **B-2** Claude 좌표 추출 | 해설 페이지 → `{"figures":[{x,y,w,h,label,type}]}` |
| 5 | **B-3** 표·Exhibit 팝업 처리 | 흰배경 표 + 파란 팝업 둘 다 올바르게 크롭 |
| 6 | **B-4** 뷰어 인라인 표시 | 해설 아래 그림/표가 `<img>` + 캡션으로 표시 |

---

### Phase 3 — Noji 암기카드 연동

> **Noji 공개 API 없음** → CSV 가져오기 방식으로 구현
> 문제 풀 때마다 버튼 클릭 → Claude가 앞/뒷면 자동 생성 → CSV 누적 → Noji에 주기적 업로드

| # | 작업 | 완료 기준 |
|---|---|---|
| 7 | **N-1** "Noji 카드 저장" 버튼 + Claude 앞/뒷면 생성 | 채점 후 버튼 클릭 → 앞면(증례 요약)/뒷면(핵심 포인트) 미리보기 표시 |
| 8 | **N-2** `/flashcard` 엔드포인트 → `flashcards.csv` 누적 | 서버가 카드를 CSV에 append, QID·분야·날짜 포함 |
| 9 | **N-3** CSV 다운로드 버튼 + Noji 가져오기 안내 | 버튼 클릭 → `flashcards.csv` 다운로드, 가져오기 방법 툴팁 표시 |

**Noji 카드 형식 (확정)**
```
앞면: [증례 핵심 1~2줄] → [질문]
      예) 29세 여성, 간질 병력, 30분째 발작 지속 → 1st line 치료는?

뒷면: ✅ [정답] — [기전 1줄]
      ▸ [핵심 포인트 3개]
      ▸ [감별진단 또는 주의사항]
      예) Lorazepam IV — GABA 수용체 활성화로 발작 억제
          ▸ Status epilepticus: 발작 5분 이상 또는 2회 이상
          ▸ Diazepam → Phenytoin → Phenobarbital → Propofol
          ▸ 임산부: Magnesium sulfate 우선
```

---

### Phase 4 — 전체 통계 + 준비도 대시보드

> **점수 추정 한계 (근거 기반)**:
> UWorld 정답률과 실제 Step 2 CK 점수의 상관관계는 r = 0.55 수준으로 단독 예측은 어렵고,
> UWSA-2 모의고사가 r = 0.895로 훨씬 신뢰도가 높음.
> 따라서 이 시스템은 **"정확한 점수 예측"이 아닌 "준비도 및 약점 시각화"**를 목표로 함.
> 2025-26 합격 기준: 218점 / 중앙값: ~245점 / 75퍼센타일: ~256점

| # | 작업 | 완료 기준 |
|---|---|---|
| 10 | **S-1** `progress.json` 저장 구조 설계 + `/progress` POST 엔드포인트 | 채점 시 QID·분야·정오답·날짜·소요시간 자동 저장 |
| 11 | **S-2** `/stats` GET 엔드포인트 — 집계 로직 | 분야별 정답률·완료수·오답 목록 JSON 반환 |
| 12 | **S-3** 통계 대시보드 UI (index.html 탭 추가) | 분야별 정답률 바 차트 + 전체 완료율 링 차트 표시 |
| 13 | **S-4** 준비도 지표 + 약점 분석 패널 | 아래 4가지 지표를 카드로 표시 |

**S-4 준비도 지표 (표시 항목)**
```
① 전체 정답률        — 예) 68% (131/194문제 완료)
② 분야별 정답률 순위 — 강점 TOP 3 / 약점 TOP 3
③ 준비도 신호등      — 🔴 <55% / 🟡 55~70% / 🟢 70%+
   (UWorld 정답률 기준, 단순 참고용임을 명시)
④ 오답 집중 분야     — 재학습 우선순위 제안
   예) "Seizure disorder 정답률 52% — 오답 문제 8개"
```

> ⚠️ 대시보드에 "이 수치는 준비도 참고용이며 실제 시험 점수와 다를 수 있습니다" 경고 표시 필수

---

### Phase 5 — 심화 기능

| # | 작업 | 완료 기준 |
|---|---|---|
| 14 | 응답 캐시 저장 | 번역·해설을 로컬 JSON 캐시, 재호출 시 API 비용 0 |
| 15 | Google Sheets 인증 + 진도 기록 | 서비스 계정 키 발급 → 채점 시 시트에 자동 1줄 추가 |
| 16 | 분야 카운트 연결 | `.tsx` 트래커에 실제 완료 문제 수 연동 |
| 17 | 오답 유사문제 생성 | 오답 1건 → Claude가 비슷한 구조의 새 문제 1개 생성 |

---

## 기술 메모 (반복 실수 방지)
- OneDrive + Norton이 `.bat` 차단 → VS Code tasks 사용
- Windows 경로 백슬래시/슬래시 혼용 → 404. `os.path.normpath`로 정규화
- `file:///`는 localhost API 호출 차단 → `index.html`을 서버로 서빙
- Git `master`/`main` 충돌 → `git push origin master:main` 후 브랜치 이름 변경
- `.env`는 BOM 가능성 → `utf-8-sig`로 읽고 값의 따옴표 제거
- **Max 구독 ≠ API 사용권**. API는 별도 크레딧
- PowerShell에서 `curl` = `Invoke-WebRequest` (다름). 진짜 curl은 `curl.exe`

## 그림 크롭 기술 메모 (2026-06-02 테스트)
- 페이지 크기: 1372 × 896 px / 헤더 ~110px / 푸터 ~50px (모두 파란색)
- **사진형 이미지**: numpy std>25 연속 블록으로 자동 탐지 성공 (MRI 완벽 크롭 확인)
- **흰배경 표**: 휴리스틱 실패 → Claude API bounding box 방식 필요
- **Exhibit Display 팝업**: 파란 테두리 팝업 → 내부 콘텐츠만 크롭 필요
- `/crop` 구현: PIL `image.crop((x1,y1,x2,y2))` + BytesIO JPEG 반환

## Noji 연동 기술 메모
- Noji 공개 REST API 없음 (2026-06-02 확인)
- 공식 지원 가져오기: CSV 파일 / Google Sheets 복붙 / Anki 덱 / Quizlet
- CSV 포맷: `앞면,뒷면` (쉼표 구분, 큰따옴표로 감싸기)
- 자동화 불가 → 반자동 (버튼 클릭으로 CSV 누적 → 주기적 Noji 업로드)
- `flashcards.csv`는 `.gitignore`에 추가 (개인 학습 데이터)

## 점수 추정 기술 메모
- UWorld 정답률 ↔ Step 2 CK 점수 상관: r ≈ 0.55 (단독 예측 부정확)
- UWSA-2 모의고사 ↔ 실제 점수 상관: r ≈ 0.895 (가장 신뢰도 높음)
- 2025-26 기준: 합격선 218 / 중앙값 245 / 75퍼센타일 ~256
- 이 시스템의 준비도 지표는 "참고용 신호등" 수준으로 표시, 과신 금지

## B-1 세션 메모 (2026-06-09)
- **`/crop`은 crop_endpoint.py 별도 파일이 아니라 usmle_server.py에 직접 통합**. 기존 핸들러(`get_page_jpeg`)를 재사용해 캐시·보안검사·파일타입 감지를 그대로 활용하고, `/page`와 동일한 픽셀 공간에서 크롭 → 좌표 일치 보장(B-2 대비). crop_endpoint.py는 삭제 가능.
- 추가 의존성: `pip install pillow numpy` (둘 다 없어도 다른 엔드포인트는 동작하도록 가드 처리).
- **디스크 파일 형식 주의**: 프로젝트에 올렸던 Neurology는 ZIP+JPEG(`1_PDFsam_Neurology_390q.pdf`, 밑줄)였지만, 실제 OneDrive의 UWorld QBank 2024 Neurology는 **일반 PDF**(`..._PDFsam_Neurology 390q.pdf`, 띄어쓰기)이고 PyMuPDF로 렌더링됨. 위치도 한 단계 더 깊음: `...\UWorld QBank 2024\Nervous System (Neurology) (390q)\`. 청크 prefix는 1041, 1121 등 전체 390q 범위까지 존재.
- **그림 자동탐지(`auto=1`)의 한계 — B-2가 필요한 이유**:
  - ✅ 컬러 그림·해부 일러스트: 잘 됨
  - ✅ 텍스트 페이지: 컬러 밀도 가드(`FIGURE_MIN_DENSITY=0.012`)로 "그림 없음" 처리
  - ⚠️ 회색 MRI/CT: 색이 없어 위치를 못 잡음
  - ⚠️ 임계값이 **렌더링 형식에 민감** — ZIP+JPEG로 맞춘 값이 일반 PDF(PyMuPDF) 렌더에는 안 맞음 (텍스트 페이지가 임계값을 넘김). → 픽셀 휴리스틱으로 형식·페이지 종류를 모두 커버하는 건 비현실적. **B-2(Claude 시각 인식)로 대체 필요**.
- 뷰어는 현재 텍스트 + "이미지 있음" 표시만 함. 실제 그림 인라인 표시는 **B-4**. (B-1→B-4 완성돼야 뷰어에서 그림이 보임)
- **브라우저 캐시 주의**: `/crop`·`/page` 응답에 `Cache-Control: max-age=3600`이 붙어 있어, 같은 URL은 서버에 묻지 않고 캐시를 보여줌. 테스트 중에는 URL 끝에 `&v=2` 같은 더미 파라미터로 캐시 우회.
- **서버 실행은 반드시 `--config` 포함**: VS Code ▶(Run File) 버튼은 인자 없이 실행해 현재 폴더만 스캔함(→ 다른 폴더 파일은 403). `Ctrl+Shift+B` 또는 `python usmle_server.py --config config.txt` 사용.

## 문서 날짜 자동 스탬프 (선택)
이 문서 제목의 날짜를 매번 손으로 바꾸는 대신, 저장 직전 아래 PowerShell 한 줄로 오늘 날짜로 갱신할 수 있음:
```powershell
(Get-Content SYSTEM_ARCHITECTURE.md -Raw) `
  -replace '# \[\d{4}-\d{2}-\d{2}\]', "# [$(Get-Date -Format yyyy-MM-dd)]" `
  -replace '마지막 업데이트: \d{4}-\d{2}-\d{2}', "마지막 업데이트: $(Get-Date -Format yyyy-MM-dd)" `
  | Set-Content SYSTEM_ARCHITECTURE.md -Encoding utf8
```
