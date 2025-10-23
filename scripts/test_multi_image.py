import gc
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
MAX_MODEL_LEN = 8192
LIMIT_MM = {"image": 8, "video": 0}
MAX_TOKENS = 4096
TOP_P = 0.9
TOP_K = 40
TEMPERATURE = 0.7

# === IMAGE SOURCES (extend freely) ===
IMAGE_A_URL = "https://honeyberries.net/assets/backgrounds/minecraft-server-background.webp"
IMAGE_B_URL = "https://honeyberries.net/assets/backgrounds/discord-ai-agent-background.webp"

IMAGE_URLS = {
    k: v for k, v in locals().items()
    if k.startswith("IMAGE_") and k.endswith("_URL")
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


def build_json_schema(image_keys):
    """Builds a JSON schema dynamically for all images (optional)."""
    base_img_schema = {
        "type": "object",
        "properties": {
            "description": {"type": "string"},
            "main_subject": {"type": "string"},
            "colors": {"type": "array", "items": {"type": "string"}},
            "purpose": {"type": "string"},
        },
        "required": ["description", "main_subject", "colors", "purpose"],
    }
    schema = {
        "type": "object",
        "properties": {key.lower(): base_img_schema for key in image_keys},
        "required": [key.lower() for key in image_keys],
    }
    return schema


def make_conversation_for_all_images(image_names):
    """A conversation that requests a single JSON for all images."""
    contents = [{"type": "text", "text":
                 f"Analyze these {len(image_names)} images ({', '.join(image_names)}).\n"
                 f"Return one JSON object with keys {list(image_names)}.\n"
                 "Each must include: description, main_subject, colors, and purpose."
                 }]
    return contents


def make_conversation_for_single_image(image_name):
    """A conversation that requests analysis for a single image."""
    contents = [{"type": "text", "text":
                 f"Analyze this image ({image_name}).\n"
                 f"Return one JSON object with key '{image_name}'.\n"
                 "The object must include: description, main_subject, colors, and purpose."
                 }]
    return contents


def main():
    setup_env()

    # Download images
    images = {}
    for name, url in IMAGE_URLS.items():
        try:
            images[name] = download_rgb(url)
        except Exception as e:
            print(f"[WARN] failed to download {name} ({url}): {e}")

    if not images:
        print("[ERROR] No images downloaded — exiting.")
        return

    print(f"[INIT] Loaded {len(images)} images.")

    # Optional: build xgrammar schema (uncomment to enforce)
    schema = build_json_schema(images.keys())
    grammar_obj = Grammar.from_json_schema(schema, strict_mode=True)
    structured_output_params = StructuredOutputsParams(grammar=str(grammar_obj))
    # Note: to enable structured outputs, set sampling_params.structured_outputs=structured_output_params

    # Initialize LLM
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

    # Build conversations (batches)
    conversations = []      # each element is a list of messages (one conversation)
    conv_names = []         # readable names to map batch index -> description
    conv_images = []        # which images were attached to each conversation (list of image keys)

    # Batch 0: one conversation for ALL images
    all_contents = make_conversation_for_all_images(list(images.keys()))
    # system + user messages
    messages_all = [
        {"role": "system", "content":
            "You are a helpful assistant. When asked for JSON, output valid JSON only — "
            "no commentary, no code fences, no text before or after. Follow the schema exactly."
         },
        {"role": "user", "content": all_contents},
    ]
    # attach images after the user message
    for name, img in images.items():
        messages_all[1]["content"].append({"type": "image_pil", "image_pil": img})

    conversations.append(messages_all)
    conv_names.append("ALL_IMAGES")
    conv_images.append(list(images.keys()))

    # Batches 1..N: one conversation per image
    for name, img in images.items():
        contents = make_conversation_for_single_image(name)
        messages = [
            {"role": "system", "content":
                "You are a helpful assistant. When asked for JSON, output valid JSON only — "
                "no commentary, no code fences, no text before or after. Follow the schema exactly."
             },
            {"role": "user", "content": contents},
        ]
        # attach only that image
        messages[1]["content"].append({"type": "image_pil", "image_pil": img})

        conversations.append(messages)
        conv_names.append(f"IMAGE_{name}")
        conv_images.append([name])

    # sampling params — one per conversation (same settings here, but you can vary per batch)
    sampling_params_list = []
    for _ in conversations:
        sp = SamplingParams(
            max_tokens=MAX_TOKENS,
            top_p=TOP_P,
            top_k=TOP_K,
            temperature=TEMPERATURE,
            # Uncomment to enforce schema via xgrammar:
            # structured_outputs=structured_output_params,
        )
        sampling_params_list.append(sp)

    print("[CALL] Calling llm.chat(...) with batched conversations (one call).")
    all_batches = []
    try:
        # vLLM supports passing a list of conversations to `chat` to process as a batch.
        # return_last_only=False to retain multi-output responses if present.
        for batch_out in llm.chat(
            messages=conversations,
            sampling_params=sampling_params_list,
            use_tqdm=True,
        ):
            # each iteration yields a RequestOutput for one batch element
            all_batches.append(batch_out)

    except Exception as e:
        print("[ERROR] llm.chat failed:", repr(e))
        raise

    if not all_batches:
        print("[WARN] no batch outputs received")
        return

    # Process & print every batch output
    for batch_idx, batch in enumerate(all_batches):
        conv_name = conv_names[batch_idx] if batch_idx < len(conv_names) else f"BATCH_{batch_idx}"
        images_in_batch = conv_images[batch_idx] if batch_idx < len(conv_images) else []
        print(f"\n=== BATCH {batch_idx} — {conv_name} — images: {images_in_batch} ===")

        if not getattr(batch, "outputs", None):
            print(f"[BATCH {batch_idx}] has no outputs")
            continue

        for out_idx, output in enumerate(batch.outputs):
            raw = output.text.strip()
            print(f"\n[BATCH {batch_idx} OUTPUT {out_idx}] RAW OUTPUT:\n{raw}\n")
            # Attempt to parse JSON (most likely what you want)
            try:
                parsed = json.loads(raw)
                print(f"[BATCH {batch_idx} OUTPUT {out_idx}] PARSED JSON:\n{json.dumps(parsed, indent=2)}")
            except Exception as e:
                print(f"[BATCH {batch_idx} OUTPUT {out_idx}] failed to parse JSON:", e)

    del llm
    gc.collect()
    print("\n[FIN] Done.")


if __name__ == "__main__":
    main()
