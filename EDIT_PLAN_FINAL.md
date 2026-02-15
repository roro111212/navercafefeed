# 네이버 카페 봇 수정 플랜 (최종 보완본)
> 작성일: 2026-02-15
> 기반 데이터: log_260215_105318.txt (179회 실행, 9.5시간)
> 서버 스펙: Oracle Cloud, Ubuntu 24.04, 1GB RAM, Swap 36%

---

## 0. 현황 요약

### 정량 지표
| 지표 | 값 | 비율 |
|------|-----|------|
| 총 실행 | 179회 | 100% |
| **정상 완료** | 116회 | **64.8%** |
| 타임아웃 (150s) | 51회 | 28.5% |
| 강제종료 (137) | 24회 | 13.4% |

### 신버전(03:08~) 지표 (핵심)
| 지표 | 값 |
|------|-----|
| **첫시도 성공률** | 8.3% (12/145) |
| **재시도 성공률** | 94.7% (126/133) |
| **최종 성공률** | **~97%** |
| 메모리 사용량 | 390~460MB |

### 근본 원인
- **첫시도 실패가 91.7%로 압도적** → 네이버가 첫 쿠키 적용을 거의 항상 무시
- 재시도(쿠키 재적용)하면 94.7% 성공 → 쿠키 자체는 유효
- **타임아웃 51회는 전부 구버전(Phase 1) 코드에서 발생** → 신버전에서는 해결됨
- 137 강제종료 24회 중 대부분도 구버전 → 신버전에서 1회만 발생

---

## 1단계: 즉시 적용 (P0, 리스크 최소)

### 1-1. run_bot_enhanced.sh: 종료코드 137 원인 추적
**현재 문제**: 137(SIGKILL) 발생 시 OOM인지 timeout kill인지 구분 불가

**수정 내용**:
```bash
# cleanup() 함수 내, 137 분기에 추가
elif [ "$MAIN_EXIT" -eq 137 ]; then
    log "ERROR: main killed (code=137). Memory/OOM dump:"
    free -m >> "$LOG_FILE" 2>&1
    dmesg | tail -5 >> "$LOG_FILE" 2>&1
```

### 1-2. main.py: 실패 시 페이지 소스 저장 제한
**현재 문제**: 매 실패마다 `driver.page_source[:2000]` 출력 → 로그 289KB 비대화

**수정 내용**:
- 페이지 소스 출력을 **최초 1회만** 으로 제한
- 이후 실패는 URL과 title만 로깅
```python
# 환경변수 또는 파일 플래그로 "이미 소스 출력했는지" 체크
if len(elements) == 0 and not _page_source_logged():
    print(driver.page_source[:1000])
    _mark_page_source_logged()
else:
    print(f"[skip] 페이지 소스 생략 (URL={driver.current_url})")
```

### 1-3. run_bot_enhanced.sh: 로그 로테이션
**현재 문제**: cron.log가 1.2MB → 무한 증가

**수정 내용**:
```bash
# 로그 파일이 5MB 초과 시 백업 후 초기화
LOG_MAX_SIZE=5242880  # 5MB
if [ -f "$LOG_FILE" ] && [ "$(stat -f%z "$LOG_FILE" 2>/dev/null || stat -c%s "$LOG_FILE")" -gt "$LOG_MAX_SIZE" ]; then
    mv "$LOG_FILE" "${LOG_FILE}.bak"
    log "INFO: log rotated."
fi
```

---

## 2단계: 성능 최적화 (P1, 성공률 97% → 99%)

### 2-1. main.py: 첫시도 성공률 개선 (핵심!)
**현재 문제**: 첫시도 성공률 8.3%로 매우 낮음 → 항상 재시도 필요 → 시간/자원 낭비

**원인 분석**:
- `naver.com` 접속 → 쿠키 설정 → `naver.com` 재방문 → 카페 이동
- 네이버가 **첫 접속의 쿠키를 JS로 덮어쓰는 것으로 추정**
- 재시도 시 쿠키가 **2회 적용**되므로 성공

**수정 내용**: 쿠키를 **처음부터 2회 적용**하여 첫시도 성공률을 높임
```python
# ── 1단계: 네이버 도메인 확보 ──
driver.get("https://www.naver.com")
# readyState 대기
...

# ── 1.5단계: 쿠키를 2회 적용 (네이버 JS 덮어쓰기 방어) ──
_apply_cookies(driver, cookie_pairs)
driver.get("https://www.naver.com")
time.sleep(0.5)
_apply_cookies(driver, cookie_pairs)  # ← 2차 적용 (핵심!)

# ── 2단계: 쿠키 활성화 ──
driver.get("https://www.naver.com")
time.sleep(1)

# ── 3단계: 카페 피드 이동 ──
driver.get("https://section.cafe.naver.com/ca-fe/home/feed")
result = _wait_url_or_feed(driver, timeout=20)
```

### 2-2. main.py: ChromeDriver 죽음(Connection refused) 대응
**현재 문제**: 로그 807번 줄에서 `Connection refused` → ChromeDriver가 OOM으로 죽음

**수정 내용**:
```python
except Exception as e:
    error_msg = str(e)
    if "Connection refused" in error_msg or "no such session" in error_msg:
        print(f"ChromeDriver 연결 끊김 (OOM 의심): {error_msg[:100]}")
        fetch_ok = False  # 쿠키 만료가 아닌 시스템 에러로 분류
    else:
        print(f"피드 수집 실패: {error_msg[:200]}")
```

### 2-3. main.py: _wait_url_or_feed 타임아웃 최적화
**현재 문제**: 재시도 시 20초 대기 → 총 실행시간이 150초에 근접

**수정 내용**:
- 첫시도: 15초 (현재 20초 → 5초 절약)
- 재시도: 20초 유지
- 이유: 로그인 리다이렉트는 0.5~2초 내 감지됨. ready도 3~5초 내.
```python
result = _wait_url_or_feed(driver, timeout=15)  # 첫시도: 15초
...
if result == "login":
    ...
    result = _wait_url_or_feed(driver, timeout=20)  # 재시도: 20초 유지
```

---

## 3단계: 안정성 보강 (P2)

### 3-1. run_bot_enhanced.sh: flock 추가
**현재 상태**: main.py에만 flock 있음. 쉘에서 중복 Cron 실행은 막지 못함

**수정 내용**:
```bash
# 맨 위에 추가
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] SKIP: already running." >> "$LOG_FILE"
    exit 0
fi
```

### 3-2. main.py: 실행 시간 제한 (자체 타임아웃)
**현재 문제**: 150초 쉘 timeout에 의존 → SIGINT → asyncio.CancelledError → 스택트레이스

**수정 내용**: Python 내부에서 자체 타임아웃 관리
```python
import signal

def _timeout_handler(signum, frame):
    raise TimeoutError("자체 실행 시간 초과 (120초)")

# main() 시작부에서
signal.signal(signal.SIGALRM, _timeout_handler)
signal.alarm(120)  # 120초 후 자체 종료 (쉘 150초보다 30초 먼저)
```

### 3-3. Cron 주기 조정 검토
**현재**: */3 (3분마다)
**권장**: */5 (5분마다)

**이유**:
- 실행 1회에 평균 2~2.5분 소요 (쿠키 적용 + 재시도 + 피드 수집)
- 현재 3분 간격이면 **이전 실행이 끝나기 전에 다음이 시작**될 수 있음
- 5분이면 충분한 여유 확보 + 네이버 봇 탐지 위험 감소

---

## 적용하지 않는 항목 (사유)

| 원래 플랜 항목 | 미적용 사유 |
|--------------|-----------|
| 상태 머신(enum) | 현재 문자열 기반 상태("login"/"ready"/"timeout")로 충분 |
| 구조화 로그 포맷 | 1인 운영 봇에 파이프 구분 로그는 과도. 텍스트 로그 유지 |
| 지수 백오프 | Cron 주기와 충돌. Cron 자체가 간격 제어 |
| 크론 일시중단 플래그 | 성공률 97%에서 자동 중단 시 알림 놓침 위험 |
| 실패률 집계/임계치 경보 | 복잡도 대비 효과 미미. watchdog.py가 이미 존재 |
| nidlogin 연속 3회 차단 | 현재 코드가 이미 최대 2번만 시도 후 종료 |
| time.sleep → WebDriverWait 전면 교체 | _wait_url_or_feed()가 더 효과적 (0.1s 폴링) |
| Selenium locator 중앙화 | CSS 셀렉터 5개뿐. 별도 모듈 불필요 |

---

## 완료 기준 (KPI)

| 지표 | 현재 | 목표 |
|------|------|------|
| 최종 성공률 | 97% | **99%+** |
| 첫시도 성공률 | 8.3% | **50%+** (2차 쿠키 적용으로) |
| 타임아웃(150s) | 51회/179회 | **0~1회/200회** |
| 강제종료(137) | 24회/179회 | **0~2회/200회** |
| 로그 파일 크기 | 289KB/9.5h | **50KB/9.5h** (소스 출력 제한) |
| 단위 실행 시간 | 2~2.5분 | **1.5~2분** (타임아웃 단축) |

---

## 적용 순서

1. **즉시**: 1-2(페이지소스 제한) + 1-3(로그 로테이션)
2. **같은 날**: 2-1(쿠키 2회 적용) + 2-3(타임아웃 최적화)
3. **다음 날**: 1-1(137 원인 추적) + 3-1(쉘 flock)
4. **검증 후**: 3-2(자체 타임아웃) + 3-3(Cron 5분)
