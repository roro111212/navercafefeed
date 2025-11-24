import requests
from bs4 import BeautifulSoup

# User provided cookie
COOKIE = "NID_AUT=JvMeGfVQcCNCQiae6ye5yIDkZg1QXNEDRq6bLXBidDPaF7iyG/3umBs4gSBC4P8y; NID_SES=AAAB1wYPdQ3hitcTHrn7/ruwijcS6zWSxr7ugOhYCVtOHAKzpUgaQolGWVQcWPoJ0RvqzwtNsaY1x9tSNZWgFHZoeQHjndd9XLFZLL8odXrXH/i9RuNzpmJS3Pp2FEl8ahqiu0qNPjSVEc94T3zdpdWe9JX7vPM8VFT6q6wSbzebMTeZarx+zFWbir5kXjnVLTwguzVR5+5z/s55kiQswDm/TPKccqn7v0pj2E6JdD25Sc46mAhqXp75QY1hoWqzIKswjI6jCEJJswFbK7S3FEUlU9rprBhk3tiWGUj/J/DBnNMwUERT8ahwEsFSvKAjKbXRqpqMhVtRe4TLGAss+8FO3iZFim0OR9DOQnkGUWHNhYtFbzfNzV32E4U/Gja9ghDG79+LnBkzQWgI2JRqnR5BMuC7KtJa04rR4h3FTptq1KQawS34ead0FCtSSIbvCMZMoNK7JTdvPLI1qkegQrESziVfAszVBbY21GymTGxpywQwTHoyi0hNpdU/SbbHYFpn7QCPBQSXtrrbIPLVO2g6uoah6HDkwQnp9eBYwdLUt79GwQtZ0eKnupupKfWVjZLqY2wbvrRsjaR64D/5JdS69HZ9yt1izz3NHQT5/xi0WGay8o2I9JJWRJn2O+wjNG1Caw=="

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Cookie': COOKIE
}

url = "https://section.cafe.naver.com/ca-fe/home/feed"

try:
    response = requests.get(url, headers=headers)
    print(f"Status Code: {response.status_code}")
    
    soup = BeautifulSoup(response.text, 'html.parser')
    items = soup.select("div.feed_item")
    print(f"Found {len(items)} items.")
    
    if len(items) == 0:
        print("HTML Content Preview:")
        print(response.text[:500])
        
except Exception as e:
    print(f"Error: {e}")
