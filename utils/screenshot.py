import os
import time
import asyncio
import logging
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


async def make_commit_screenshot(url: str, commit_id: str) -> str | None:
    if not commit_id:
        logger.error("[SCREENSHOT] commit_id не указан")
        return None

    file_path = f"screenshots/commit_{commit_id}_{int(time.time() * 1000)}.png"
    os.makedirs("screenshots", exist_ok=True)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                timeout=60000
            )

            page = await browser.new_page(
                viewport={"width": 1280, "height": 1400},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )

            full_url = f"{url}#{commit_id}"
            logger.info(f"[SCREENSHOT] Открываем: {full_url}")

            # 1️⃣ SPA → ждём сетевую тишину
            await page.goto(full_url, wait_until="networkidle", timeout=60000)

            # 2️⃣ Гарантируем, что коммиты вообще появились
            await page.wait_for_selector("div.commit", timeout=30000)

            # 3️⃣ ТЕПЕРЬ ищем нужный коммит
            commit_selector = f"div.commit.columns[like-id='{commit_id}']"
            commit_block = await page.wait_for_selector(
                commit_selector,
                timeout=30000
            )

            # 4️⃣ Скролл к коммиту
            await commit_block.scroll_into_view_if_needed()
            await asyncio.sleep(1)

            # 5️⃣ Скриншот только блока
            screenshot_bytes = await commit_block.screenshot(type="png")

            await browser.close()

            if screenshot_bytes:
                with open(file_path, "wb") as f:
                    f.write(screenshot_bytes)

                logger.info(f"[SCREENSHOT] Сохранён: {file_path}")
                return file_path

            return None

    except Exception as e:
        logger.error(
            f"[SCREENSHOT] Ошибка для {url}#{commit_id}: {e}",
            exc_info=True
        )
        return None
