# Should trigger: concurrency.blocking_in_async
import asyncio
import time

async def fetch_data():
    time.sleep(5)  # blocking call in async function
    return "data"
