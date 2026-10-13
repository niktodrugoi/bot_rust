import logging
import aiohttp
import json

from config import OLLAMA_URL, OLLAMA_MODEL, OLLAMA_PROMPT

logger = logging.getLogger(__name__)


async def generate_analysis(commit_text: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": f"{OLLAMA_PROMPT}\nCommit: {commit_text}",
        "stream": False
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(OLLAMA_URL, data=json.dumps(payload)) as response:
            if response.status != 200:
                raise Exception(f"Ollama API error: {response.status}")
            result = await response.json()

    analysis = result.get('response', "No analysis generated")
    logger.info("Ollama response received")
    return analysis