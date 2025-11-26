import os
import time
import asyncio
from telegram import Bot
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
WATCHDOG_FILE = 'last_run.txt'
THRESHOLD_SECONDS = 600  # 10분 (봇이 10분 이상 멈추면 알림)

async def send_alert(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram 설정 누락")
        return
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        print("경고 메시지 전송 성공")
    except Exception as e:
        print(f"경고 메시지 전송 실패: {e}")

async def check_bot_status():
    if not os.path.exists(WATCHDOG_FILE):
        print(f"{WATCHDOG_FILE} 파일이 없습니다. 아직 봇이 한 번도 실행되지 않았거나 파일이 삭제되었습니다.")
        return

    try:
        with open(WATCHDOG_FILE, 'r') as f:
            last_run_timestamp = float(f.read().strip())
        
        current_time = time.time()
        elapsed_time = current_time - last_run_timestamp
        
        if elapsed_time > THRESHOLD_SECONDS:
            minutes = int(elapsed_time / 60)
            msg = f"🚨 [비상] 네이버 카페 봇이 멈췄습니다!\n\n마지막 실행: {minutes}분 전\n서버 상태를 확인해주세요."
            print(msg)
            await send_alert(msg)
        else:
            print(f"봇 정상 작동 중 (마지막 실행: {int(elapsed_time)}초 전)")
            
    except Exception as e:
        print(f"상태 확인 중 오류 발생: {e}")

if __name__ == "__main__":
    asyncio.run(check_bot_status())
