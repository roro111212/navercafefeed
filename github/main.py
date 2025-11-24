import os
import requests
import asyncio
from bs4 import BeautifulSoup
from telegram import Bot
from datetime import datetime, timedelta

# GitHub Secrets에서 환경 변수 로드
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
NAVER_COOKIE = os.environ.get('NAVER_COOKIE') # NID_AUT=...; NID_SES=...

async def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram 설정이 누락되었습니다.")
        return
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        print(f"텔레그램 전송 성공: {message[:20]}...")
    except Exception as e:
        print(f"텔레그램 전송 실패: {e}")

def get_feed_posts():
    if not NAVER_COOKIE:
        print("네이버 쿠키(NAVER_COOKIE)가 설정되지 않았습니다.")
        return []

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Cookie': NAVER_COOKIE
    }
    
    url = "https://section.cafe.naver.com/ca-fe/home/feed"
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        posts = []
        # PC 버전에서 확인한 선택자 사용
        items = soup.select("div.feed_item")
        
        for item in items[:5]: # 최신 5개
            try:
                title_el = item.select_one("strong.title")
                link_el = item.select_one("div.feed_content > a")
                date_el = item.select_one("span.date") # "방금 전", "1분 전" 등
                
                if title_el and link_el:
                    title = title_el.get_text(strip=True)
                    link = link_el['href']
                    date_text = date_el.get_text(strip=True) if date_el else ""
                    
                    posts.append({
                        'title': title, 
                        'link': link,
                        'date': date_text
                    })
            except Exception as e:
                continue
                
        return posts
        
    except Exception as e:
        print(f"피드 가져오기 실패: {e}")
        return []

async def main():
    print("네이버 카페 피드 확인 중...")
    posts = get_feed_posts()
    
    if not posts:
        print("새로운 게시글이 없거나 가져오는데 실패했습니다.")
        return

    # GitHub Actions는 상태 저장이 어려우므로, 
    # "방금 전" 또는 "N분 전" 인 게시글만 필터링해서 보냄 (5분 주기 실행 가정)
    # 또는 단순히 최신 1~2개를 보낼 수도 있지만 중복 알림 가능성이 있음.
    # 여기서는 "방금 전", "1분 전" ~ "5분 전" 인 글만 보냄.
    
    target_times = ["방금 전", "1분 전", "2분 전", "3분 전", "4분 전", "5분 전"]
    
    new_posts_count = 0
    for post in posts:
        # 날짜 텍스트가 target_times에 포함되면 알림 전송
        if any(t in post['date'] for t in target_times):
            msg = f"[새 글 알림]\n{post['title']}\n{post['link']}\n({post['date']})"
            await send_telegram_message(msg)
            new_posts_count += 1
            
    if new_posts_count == 0:
        print("최근 5분 내 작성된 새 글이 없습니다.")
    else:
        print(f"{new_posts_count}개의 새 글 알림을 전송했습니다.")

if __name__ == "__main__":
    asyncio.run(main())
