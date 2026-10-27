"""Muse Spark call that turns the scene prompt into a spoken instruction.

Docs: https://dev.meta.ai/docs/quickstart
"""

import os

from sam import BASE_URL, is_mock

MODEL = "muse-spark-1.3"

MOCK_INSTRUCTION = "Chair close on your left. Person ahead. Door to your right."


async def spoken_instruction(prompt: dict) -> str:
    """Send a {"system", "user"} prompt to Muse Spark and return its reply.

    In mock mode, returns MOCK_INSTRUCTION without calling the API.
    """
    if is_mock():
        return MOCK_INSTRUCTION

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.environ["MODEL_API_KEY"], base_url=BASE_URL)
    response = await client.responses.create(
        model=MODEL,
        input=[
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": prompt["user"]},
        ],
    )
    return response.output_text.strip()
