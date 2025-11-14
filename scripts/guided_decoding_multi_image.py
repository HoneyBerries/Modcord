import os
import json
from io import BytesIO
import requests
from PIL import Image
from vllm import LLM, SamplingParams
from vllm.sampling_params import StructuredOutputsParams
from xgrammar.grammar import Grammar

# === CONFIG ===
MODEL_ID = "/mnt/d/AI_MODELS/modcord_custom_models/qwen3-vl-4b-instruct-nf4"
GPU_MEMORY_UTIL = 0.85
DTYPE = "bfloat16"
MAX_MODEL_LEN = 16384
LIMIT_MM = {"image": 8, "video": 0}
MAX_TOKENS = 4096
TOP_P = 0.9
TOP_K = 40
TEMPERATURE = 0.7

IMAGE_C_URL = "https://honeyberries.net/assets/backgrounds/home-banner.webp"
IMAGE_A_URL = "https://honeyberries.net/assets/backgrounds/minecraft-server-background.webp"
IMAGE_B_URL = "https://honeyberries.net/assets/backgrounds/discord-ai-agent-background.webp"
IMAGE_D_URL = "https://cdn.discordapp.com/attachments/1425535604594311179/1430606604964991027/image.png?ex=68fa63ba&is=68f9123a&hm=0507209141e777ec0f2b7cbc11f6697be3e1aa6b7cd3530d2a463ab60c5d8dbc&"
IMAGE_E_URL = "https://cdn.discordapp.com/attachments/1429715710946578472/1430680820015956089/Untitled.png?ex=68faa8d8&is=68f95758&hm=4bb3821e103b5bb7d9fe805b466af54a7cbf6580c72361a079ec3151fe30f0fd&"

# === Guided Decoding Schema ===
GUIDED_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "image_A": {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "main_subject": {"type": "string"},
                "colors": {"type": "array", "items": {"type": "string"}},
                "purpose": {"type": "string"}
            },
            "required": ["description", "main_subject", "colors", "purpose"]
        },
        "image_B": {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "main_subject": {"type": "string"},
                "colors": {"type": "array", "items": {"type": "string"}},
                "purpose": {"type": "string"}
            },
            "required": ["description", "main_subject", "colors", "purpose"]
        },
        "image_C": {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "main_subject": {"type": "string"},
                "colors": {"type": "array", "items": {"type": "string"}},
                "purpose": {"type": "string"}
            },
            "required": ["description", "main_subject", "colors", "purpose"]
        },
        "image_D": {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "main_subject": {"type": "string"},
                "colors": {"type": "array", "items": {"type": "string"}},
                "purpose": {"type": "string"}
            },
            "required": ["description", "main_subject", "colors", "purpose"]
        },
        "image_E": {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "main_subject": {"type": "string"},
                "colors": {"type": "array", "items": {"type": "string"}},
                "purpose": {"type": "string"}
            },
            "required": ["description", "main_subject", "colors", "purpose"]
        }
    }
}

def setup_env():
    os.environ.setdefault("TORCH_COMPILE_CACHE_DIR", "./torch_compile_cache")
    os.environ.setdefault("VLLM_TORCH_PROFILER_WITH_PROFILE_MEMORY", "")

def download_rgb(url: str) -> Image.Image:
    print(f"[DOWNLOAD] {url}")
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    img = Image.open(BytesIO(r.content)).convert("RGB")
    print(f"[DOWNLOAD] got size={img.size}")
    return img

def main():
    setup_env()
    image_a = download_rgb(IMAGE_A_URL)
    image_b = download_rgb(IMAGE_B_URL)
    image_c = download_rgb(IMAGE_C_URL)
    image_d = download_rgb(IMAGE_D_URL)
    image_e = download_rgb(IMAGE_E_URL)

    print("[INIT] creating LLM for chat (xgrammar structured outputs enabled) …")

    # Build grammar from JSON schema
    grammar_obj = Grammar.from_json_schema(GUIDED_JSON_SCHEMA, strict_mode=True)
    structured_output_params = StructuredOutputsParams(
        grammar=str(grammar_obj),
    )

    # Initialize synchronous LLM directly
    llm = LLM(
        model=MODEL_ID,
        dtype=DTYPE,
        gpu_memory_utilization=GPU_MEMORY_UTIL,
        max_model_len=MAX_MODEL_LEN,
        tensor_parallel_size=1,
        trust_remote_code=True,
        limit_mm_per_prompt=LIMIT_MM,
        skip_mm_profiling=True,
    )

    sampling_params = SamplingParams(
        max_tokens=MAX_TOKENS,
        top_p=TOP_P,
        top_k=TOP_K,
        temperature=TEMPERATURE,
        #structured_outputs=structured_output_params
    )

    messages = [
        {"role": "system", "content": (
            "You are a helpful assistant. When asked for JSON, output valid JSON only — "
            "no commentary, no code fences, no text before or after. Follow the schema exactly."
        )},
        {
            "role": "user",
            "content": [
                {"type": "text", "text":
                 "Analyze these five images (Image_A, Image_B, Image_C, Image_D, Image_E) and describe them.\n"
                 "Return exactly one JSON object with keys 'image_A', 'image_B', 'image_C', 'image_D', and 'image_E'.\n"
                 "Each must include: description, main_subject, colors, purpose."},
                {"type": "image_pil", "image_pil": image_a},
                {"type": "image_pil", "image_pil": image_b},
                {"type": "image_pil", "image_pil": image_c},
                {"type": "image_pil", "image_pil": image_d},
                {"type": "image_pil", "image_pil": image_e},
            ],
        },
    ]

    print("[CALL] calling llm.chat(...) with guided decoding (xgrammar backend)")
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
        parsed = json.loads(raw)
        print("\n[PARSED JSON]\n", json.dumps(parsed, indent=2))
    except Exception as e:
        print("[ERROR] failed to parse JSON:", e)
        print("\n[RAW OUTPUT FOLLOWS]\n", raw)

if __name__ == "__main__":
    main()
