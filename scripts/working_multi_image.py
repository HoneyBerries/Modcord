# sync_chat_single_prompt_fixed.py
"""
Sync version using vLLM LLM.chat() with one prompt and three images.
"""

import os
import json
from io import BytesIO

import requests
from PIL import Image
from vllm import LLM, SamplingParams

# === CONFIG ===
MODEL_ID = "/mnt/d/AI_MODELS/modcord_custom_models/qwen3-vl-4b-instruct-nf4"
GPU_MEMORY_UTIL = 0.85
DTYPE = "bfloat16"
MAX_MODEL_LEN = 8192
LIMIT_MM = {"image": 8, "video": 0}
MAX_TOKENS = 1024
TOP_P = 0.9
TOP_K = 40
TEMPERATURE = 0.7

IMAGE_C_URL = "https://honeyberries.net/assets/backgrounds/home-banner.webp"
IMAGE_A_URL = "https://honeyberries.net/assets/backgrounds/minecraft-server-background.webp"
IMAGE_B_URL = "https://honeyberries.net/assets/backgrounds/discord-ai-agent-background.webp"

def setup_env():
    os.environ.setdefault("TORCH_COMPILE_CACHE_DIR", "./torch_compile_cache")

def download_rgb(url: str) -> Image.Image:
    print(f"[DOWNLOAD] {url}")
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    img = Image.open(BytesIO(r.content)).convert("RGB")
    print(f"[DOWNLOAD] got size={img.size}")
    return img

def parse_json_strict(raw: str):
    raw = raw.strip()
    try:
        return json.loads(raw)
    except Exception:
        import re
        m = re.search(r"\{.*\}", raw, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise

def main():
    setup_env()
    image_a = download_rgb(IMAGE_A_URL)
    image_b = download_rgb(IMAGE_B_URL)
    image_c = download_rgb(IMAGE_C_URL)

    print("[INIT] creating LLM for chat …")
    llm = LLM(
        model=MODEL_ID,
        dtype=DTYPE,
        gpu_memory_utilization=GPU_MEMORY_UTIL,
        trust_remote_code=True,
        max_model_len=MAX_MODEL_LEN,
        limit_mm_per_prompt=LIMIT_MM,
        tensor_parallel_size=1,
        skip_mm_profiling=True,
    )

    sampling_params = SamplingParams(temperature=TEMPERATURE, max_tokens=MAX_TOKENS, top_p=TOP_P, top_k=TOP_K)

    messages = [
        {"role": "system", "content": "Hello! You are a friendly and helpful assistant. When a user specifically asks for JSON, please make sure to reply with valid JSON only—no extra commentary. Otherwise, feel free to respond in a clear and conversational way."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text":
                 "I will show Three images, image A, image B, and image C.\n"
                 "Return exactly one JSON object with keys 'image_A', 'image_B', and 'image_C', starting with image_A.\n"
                 "Each value must be an object with fields: description, main_subject, colors, purpose.\n"
                 "Return valid JSON only — no extra commentary."},
                {"type": "image_pil", "image_pil": image_a},
                {"type": "image_pil", "image_pil": image_b},
                {"type": "image_pil", "image_pil": image_c},
            ],
        },
    ]

    print("[CALL] calling llm.chat(...) — single prompt with three images")
    last = None
    try:
        for out in llm.chat(messages, sampling_params=sampling_params):
            last = out
    except Exception as e:
        print("[ERROR] chat failed:", repr(e))
        raise

    if not last or not getattr(last, "outputs", None):
        print("[WARN] no output received")
        return

    raw = last.outputs[0].text.strip()
    print("\n[MODEL RAW OUTPUT]\n", raw)

    try:
        parsed = parse_json_strict(raw)
        print("\n[PARSED JSON]\n", json.dumps(parsed, indent=2))
    except Exception as e:
        print("[ERROR] failed to parse JSON from model output:", e)
        return {"raw": raw}

if __name__ == "__main__":
    main()
