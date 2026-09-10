"""Проверка подключения к API: список моделей + тестовый запрос.
Запуск: python check_api.py            (модель из MODEL)
        python check_api.py grok-4.5   (конкретная модель)
"""
import asyncio
import sys

import aiohttp

from config import settings


async def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else settings.model
    headers = {"Authorization": f"Bearer {settings.api_key}"}
    async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=90)) as s:
        print(f"API: {settings.api_base_url}")
        async with s.get(settings.api_base_url + "/models") as r:
            data = await r.json(content_type=None) if r.status == 200 else await r.text()
            if r.status == 200 and isinstance(data, dict):
                ids = sorted(m.get("id", "?") for m in data.get("data", []))
                print(f"Доступно моделей: {len(ids)}")
                for i in ids:
                    print("  ", i)
            else:
                print(f"/models -> HTTP {r.status}: {str(data)[:300]}")

        print(f"\nТестовый запрос к {model}...")
        payload = {"model": model, "max_tokens": 200,
                   "messages": [{"role": "user", "content": "Одним предложением: на что влияет рейтинг ACC в Madden?"}]}
        async with s.post(settings.api_base_url + "/chat/completions", json=payload) as r:
            data = await r.json(content_type=None)
            if r.status == 200:
                print("OK:", data["choices"][0]["message"].get("content"))
                print("usage:", data.get("usage"))
            else:
                print(f"HTTP {r.status}: {str(data)[:500]}")


if __name__ == "__main__":
    asyncio.run(main())
