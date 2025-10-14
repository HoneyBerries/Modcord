import os
import torch
from transformers import AutoModelForCausalLM, Qwen3VLForConditionalGeneration, AutoTokenizer, BitsAndBytesConfig

model_name = "Qwen/Qwen3-VL-4B-Thinking"

# load the tokenizer and the model
model = Qwen3VLForConditionalGeneration.from_pretrained(
    model_name,
    dtype=torch.bfloat16,
    device_map="cuda",
    quantization_config=BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True
    )
)
tokenizer = AutoTokenizer.from_pretrained(model_name)

directory = "/mnt/d/Model Folder/modcord_custom_models/qwen3-vl-4b-thinking-nf4"
os.makedirs(directory, exist_ok=True)

# Save with safe_serialization=True (default) for quantized models
model.save_pretrained(directory)
tokenizer.save_pretrained(directory)

print(f"Model and tokenizer saved to {directory}")