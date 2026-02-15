# 🚀 네이버 카페 봇 수동 배포 가이드

> 작성일: 2026-02-15
> 목표: 성공률 64.8% → 99%+

---

## 📦 배포 파일
- `github/main.py` (핵심 수정)
- `run_bot_enhanced.sh` (쉘 스크립트 개선)

---

## 🔐 1단계: 서버 접속

SSH로 Oracle Cloud 서버에 접속하세요.

```bash
# 예시 (실제 IP와 키 파일 경로를 사용하세요)
ssh -i ~/.ssh/oracle_key.pem ubuntu@[서버IP주소]
```

> **서버 IP 주소**: `ORACLE_DEPLOY.md` 파일 참조

---

## 📥 2단계: Git Pull (권장)

서버에서 직접 Git을 통해 최신 코드를 받습니다.

```bash
cd /home/ubuntu/navercafefeed

# 현재 상태 백업 (선택사항)
cp github/main.py github/main.py.backup.$(date +%Y%m%d_%H%M%S)
cp run_bot_enhanced.sh run_bot_enhanced.sh.backup.$(date +%Y%m%d_%H%M%S)

# Git pull
git pull origin main

# 또는 특정 브랜치
# git pull origin [브랜치명]
```

---

## 💾 2단계 대안: 파일 직접 복사

Git pull이 안 되는 경우, 로컬에서 파일을 복사하여 서버에 붙여넣기합니다.

### 2-1. 로컬에서 파일 내용 복사

#### **main.py 복사**
```bash
# Windows PowerShell에서
Get-Content "github/main.py" -Raw | Set-Clipboard
```

#### **run_bot_enhanced.sh 복사**
```bash
# Windows PowerShell에서
Get-Content "run_bot_enhanced.sh" -Raw | Set-Clipboard
```

### 2-2. 서버에서 파일 붙여넣기

#### **main.py 수정**
```bash
cd /home/ubuntu/navercafefeed

# 백업
cp github/main.py github/main.py.backup.$(date +%Y%m%d_%H%M%S)

# vim으로 편집 (붙여넣기)
vim github/main.py
# vim에서: i (입력모드) → Shift+Insert (붙여넣기) → Esc → :wq (저장)

# 또는 nano로 편집
nano github/main.py
# nano에서: Ctrl+Shift+V (붙여넣기) → Ctrl+X → Y → Enter (저장)
```

#### **run_bot_enhanced.sh 수정**
```bash
# 백업
cp run_bot_enhanced.sh run_bot_enhanced.sh.backup.$(date +%Y%m%d_%H%M%S)

# vim으로 편집
vim run_bot_enhanced.sh
# 또는 nano로 편집
nano run_bot_enhanced.sh
```

---

## ✅ 3단계: 권한 설정

```bash
cd /home/ubuntu/navercafefeed

# 실행 권한 부여
chmod +x run_bot_enhanced.sh
chmod +x github/main.py

# 권한 확인
ls -lh run_bot_enhanced.sh github/main.py
```

**예상 출력:**
```
-rwxr-xr-x 1 ubuntu ubuntu 4.0K Feb 15 15:50 run_bot_enhanced.sh
-rwxr-xr-x 1 ubuntu ubuntu  23K Feb 15 15:50 github/main.py
```

---

## 🧪 4단계: 테스트 실행

Cron 없이 1회 직접 실행하여 정상 작동 확인합니다.

```bash
cd /home/ubuntu/navercafefeed

# 수동 1회 실행
./run_bot_enhanced.sh

# 실시간 로그 확인
tail -f github/cron.log
```

**예상 로그 (정상):**
```
[2026-02-15 15:55:23] INFO: syncing python dependencies.
==================================================
실행 시작: 2026-02-15 15:55:25 (KST)
==================================================
네이버 카페 피드 조회 시작 (Selenium Headless)
heartbeat 갱신: /home/ubuntu/navercafefeed/github/last_run.txt
쿠키 개수: 11
초기 진입 결과: login, URL=https://nid.naver.com/nidlogin...
로그인 페이지로 리다이렉트됨: 쿠키 재적용 후 1회 재시도
재시도 진입 결과: ready, URL=https://section.cafe.naver.com/ca-fe/home/feed
게시글 조회 수: 10
--> 신규 게시글이 없습니다.
heartbeat 갱신: /home/ubuntu/navercafefeed/github/last_run.txt
[2026-02-15 15:57:28] OK: finished (450MB, disk 36%).
```

**에러 발생 시:**
```bash
# Python 경로 확인
which python3

# 의존성 재설치
cd /home/ubuntu/navercafefeed
source ../venv/bin/activate
pip install -r github/requirements.txt

# Chrome/Chromedriver 확인
which google-chrome
which chromedriver
```

---

## 📊 5단계: 모니터링 (24시간)

배포 후 24시간 동안 로그를 모니터링합니다.

### 실시간 로그 확인
```bash
# 로그 실시간 추적 (Ctrl+C로 종료)
tail -f /home/ubuntu/navercafefeed/github/cron.log

# 최근 50줄만 보기
tail -50 /home/ubuntu/navercafefeed/github/cron.log

# 성공/실패 요약
grep -E "OK: finished|ERROR:|실행 시작:" /home/ubuntu/navercafefeed/github/cron.log | tail -30
```

### 핵심 지표 확인 (1시간마다)

```bash
cd /home/ubuntu/navercafefeed/github

# 최근 1시간 통계
echo "=== 최근 60분 통계 ($(date '+%H:%M')) ==="
log_1h=$(tail -2000 cron.log)
echo "총 실행: $(echo "$log_1h" | grep -c "실행 시작:")"
echo "정상 완료: $(echo "$log_1h" | grep -c "OK: finished")"
echo "타임아웃: $(echo "$log_1h" | grep -c "ERROR: timeout")"
echo "강제종료 137: $(echo "$log_1h" | grep -c "exit code=137")"
echo "재시도 성공: $(echo "$log_1h" | grep -c "재시도 진입 결과: ready")"
```

### 메모리 사용량 확인
```bash
# 메모리 상태
free -h

# 프로세스 확인
ps aux | grep -E "chrome|python" | grep -v grep
```

---

## 🎯 6단계: 성공 기준 (KPI)

### 24시간 후 목표 달성 확인

| 지표 | 현재 (구버전) | 목표 | 확인 명령어 |
|------|--------------|------|-------------|
| **성공률** | 64.8% | **99%+** | `grep -E "OK: finished\|ERROR:" cron.log \| tail -100` |
| **타임아웃** | 28.5% | **~0%** | `grep "timeout hit" cron.log \| wc -l` |
| **강제종료 137** | 13.4% | **~1%** | `grep "exit code=137" cron.log \| wc -l` |
| **로그 크기** | 289KB/9.5h | **~50KB/9.5h** | `ls -lh cron.log` |

### 성공 판정
```bash
# 최근 100회 실행 중 성공률 계산
recent_100=$(tail -5000 /home/ubuntu/navercafefeed/github/cron.log)
total=$(echo "$recent_100" | grep -c "실행 시작:")
success=$(echo "$recent_100" | grep -c "OK: finished")
echo "성공률: $(awk "BEGIN {printf \"%.1f%%\", ($success/$total)*100}")"
```

**목표: 99% 이상**

---

## 🔧 7단계: 추가 최적화 (선택)

### Cron 주기 완화 (1주일 후)

성공률이 안정적으로 99% 이상 유지되면 서버 부하 감소를 위해 주기 완화:

```bash
# Crontab 편집
crontab -e

# 현재: */3 * * * * (3분마다)
# 변경: */5 * * * * (5분마다)
```

### 로그 백업 자동화
```bash
# 주간 로그 백업 Cron 추가
0 0 * * 0 cd /home/ubuntu/navercafefeed/github && cp cron.log cron.log.weekly.$(date +\%Y\%m\%d) && echo "" > cron.log
```

---

## ⚠️ 문제 발생 시

### 롤백 (이전 버전으로 복구)
```bash
cd /home/ubuntu/navercafefeed

# 백업에서 복구
cp github/main.py.backup.[날짜] github/main.py
cp run_bot_enhanced.sh.backup.[날짜] run_bot_enhanced.sh

# Cron 재시작 (자동으로 다음 주기에 실행됨)
```

### 긴급 중지
```bash
# Cron 비활성화
crontab -e
# 해당 줄 앞에 # 추가하여 주석 처리

# 실행 중인 프로세스 종료
pkill -f "main.py"
```

---

## 📞 지원

문제 발생 시:
1. `cron.log` 최근 100줄 확인
2. `dmesg | tail -20` 확인 (OOM 에러)
3. `free -h` 메모리 확인

---

**배포 완료 후 이 문서를 보관하세요!** 🎉
