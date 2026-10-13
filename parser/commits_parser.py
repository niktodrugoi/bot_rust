import logging
from bs4 import BeautifulSoup
import aiohttp
from datetime import datetime, timedelta

from config import SITE_URL
from storage.database import is_processed

logger = logging.getLogger(__name__)

async def parse_new_commits() -> list:
    async with aiohttp.ClientSession() as session:
        async with session.get(SITE_URL) as response:
            if response.status != 200:
                logger.error(f"Не удалось загрузить сайт: {response.status}")
                return []
            html = await response.text()

    soup = BeautifulSoup(html, 'html.parser')
    commits = []

    commit_blocks = soup.find_all('div', class_='commit columns')

    logger.info(f"Найдено блоков commit.columns: {len(commit_blocks)}")

    now = datetime.utcnow()  # текущее время UTC для расчёта "ago"

    for block in commit_blocks[:30]:
        like_id = block.get('like-id')
        if not like_id:
            continue

        commit_id = like_id

        if await is_processed(commit_id):
            continue

        # Автор — максимально надёжный поиск
        author = "Unknown"
        author_tag = block.find('a', href=lambda h: h and ('/user/' in h or '/player/' in h))
        if author_tag:
            author = author_tag.get_text(strip=True)
        else:
            author_div = block.find(['div', 'span'], class_=lambda x: x and 'author' in x.lower())
            if author_div:
                author = author_div.get_text(strip=True)
            else:
                avatar = block.find('div', class_='avatar')
                if avatar:
                    next_text = avatar.find_next(string=True, recursive=False)
                    if next_text and next_text.strip():
                        author = next_text.strip()
                    else:
                        parent_text = avatar.find_parent().get_text(strip=True).split('\n')[0].strip()
                        if parent_text:
                            author = parent_text

        if author == "Unknown" or not author:
            text_candidates = block.find_all(string=True)
            for t in text_candidates:
                t = t.strip()
                if t and len(t) > 3 and 'ago' not in t.lower() and '#' not in t:
                    author = t
                    break

        # Текст коммита
        message_tag = block.find('div', class_='commits-message')
        text = message_tag.get_text(strip=True) if message_tag else ""
        if not text:
            text_tag = block.find(string=lambda t: t and len(t.strip()) > 10 and 'ago' not in t.lower() and author not in t)
            text = text_tag.strip() if text_tag else "No message"

        # Дата — приоритет 1: datetime атрибут
        date_str = "Неизвестно"
        time_tag = block.find('time')
        if time_tag and 'datetime' in time_tag.attrs:
            iso_time = time_tag['datetime']
            try:
                dt = datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
                date_str = dt.strftime("%H:%M %d.%m.%Y")
                logger.debug(f"Дата из datetime: {date_str}")
            except Exception as e:
                logger.warning(f"Ошибка парсинга datetime {iso_time}: {e}")
                date_str = time_tag.get_text(strip=True) or "Неизвестно"

        # Приоритет 2: текст "X Minutes Ago"
        if date_str == "Неизвестно":
            time_text = None
            time_text_tag = block.find(string=lambda t: 'ago' in t.lower() if t else False)
            if time_text_tag:
                time_text = time_text_tag.strip()

            if time_text:
                try:
                    parts = time_text.lower().split()
                    num = int(parts[0])
                    unit = parts[1]

                    if 'minute' in unit:
                        delta = timedelta(minutes=num)
                    elif 'hour' in unit:
                        delta = timedelta(hours=num)
                    elif 'day' in unit:
                        delta = timedelta(days=num)
                    elif 'week' in unit:
                        delta = timedelta(weeks=num)
                    else:
                        delta = timedelta(0)

                    dt = now - delta
                    date_str = dt.strftime("%H:%M %d.%m.%Y")
                    logger.debug(f"Дата из 'ago': {date_str} ({time_text})")
                except Exception as e:
                    logger.warning(f"Ошибка расчёта из 'ago' '{time_text}': {e}")
                    date_str = time_text

        # Ссылка — правильный формат как на сайте
        link_tag = block.find('a', href=lambda h: h and '#' in h)
        if link_tag and 'href' in link_tag.attrs:
            href = link_tag['href']
            link = "https://commits.facepunch.com" + href
        else:
            link = f"https://commits.facepunch.com/r/rust_reboot/main#{commit_id}"

        commits.append({
            'author': author,
            'text': text,
            'date': date_str,
            'link': link
        })

    logger.info(f"Успешно распарсено новых коммитов: {len(commits)}")
    return commits