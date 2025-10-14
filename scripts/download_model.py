import os
import torch
from transformers import AutoModelForCausalLM, Qwen3VLForConditionalGeneration, AutoTokenizer, BitsAndBytesConfig, AutoProcessor

model_name = "Qwen/Qwen3-VL-8B-Thinking"

# load the tokenizer, model, and processor
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
processor = AutoProcessor.from_pretrained(model_name)

directory = "/mnt/d/Model Folder/modcord_custom_models/qwen3-vl-8b-thinking-nf4"
os.makedirs(directory, exist_ok=True)

# Save with safe_serialization=True (default) for quantized models
print(f"Saving model, tokenizer, and processor to {directory}...")
model.save_pretrained(directory)
tokenizer.save_pretrained(directory)
processor.save_pretrained(directory)

print(f"Model, tokenizer, and processor saved to {directory}")