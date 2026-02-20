API_URL = "https://api.inference.wandb.ai/v1"
API_KEY = "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"

from typing import List
from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionContentPartImageParam,
)
import asyncio

client = AsyncOpenAI(
    api_key=API_KEY,
    base_url=API_URL,
)

messages: List[ChatCompletionMessageParam] = [
    ChatCompletionSystemMessageParam(
        role="system",
        content="You are a helpful assistant whose job is to compare images."
    ),
    ChatCompletionUserMessageParam(
        role="user",
        content=[
            ChatCompletionContentPartTextParam(
                type="text",
                text="Here are two images. Describe the content of each image in order of which you see them and then compare them."
            ),
            # Label for Image B
            ChatCompletionContentPartTextParam(
                type="text",
                text="Image B (see the image below):"
            ),
            ChatCompletionContentPartImageParam(
                type="image_url",
                image_url={
                    "url": "https://cdn.mos.cms.futurecdn.net/57jQMDN5MZLYfV8ps8HuZQ.jpg"
                }
            ),
            # Label for Image A
            ChatCompletionContentPartTextParam(
                type="text",
                text="Image A (see the image below):"
            ),
            ChatCompletionContentPartImageParam(
                type="image_url",
                image_url={
                    "url": "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?fm=jpg&q=60&w=3000&auto=format&fit=crop&ixlib=rb-4.1.0&ixid=M3wxMjA3fDB8MHxzZWFyY2h8Mnx8b2NlYW4lMjBiZWFjaHxlbnwwfHwwfHx8MA%3D%3D"
                }
            ),
            ChatCompletionContentPartTextParam(
                type="text",
                text="Image C (see the image below):"
            ),
            ChatCompletionContentPartImageParam(
                type="image_url",
                image_url={
                    "url": "https://images.pexels.com/photos/16171064/pexels-photo-16171064/free-photo-of-close-up-of-a-bird-perching-on-a-flower.jpeg"
                }
            ),
        ],
    ),
]

async def main():
    response = await client.chat.completions.create(
        model="moonshotai/Kimi-K2.5",
        messages=[
        {'role': 'system', 'content': 'You are Kimi, an AI assistant created by Moonshot AI.'},
        {
            'role': 'user',
            'content': [
                {'type': 'text', 'text': 'which one is bigger, 9.11 or 9.9? think carefully.'}
            ],
        },
    ],
        extra_body={'thinking': {'type': 'disabled'}, 'chat_template_kwargs': {"thinking": False}},
    )

    print(response.choices[0].message.reasoning_content)
    print("________________________________________\n\n")
    print(response.choices[0].message.content)

asyncio.run(main())