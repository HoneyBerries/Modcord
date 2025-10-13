import os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

model_name = "Qwen/Qwen3-4B-Thinking-2507"

# load the tokenizer and the model
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype=torch.bfloat16,  # Changed from dtype to torch_dtype
    device_map="cpu",
    quantization_config=BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True
    )
)

directory = "/mnt/d/Model Folder/modcord_custom_models/qwen3-4b-thinking-nf4"
os.makedirs(directory, exist_ok=True)

# Save with safe_serialization=True (default) for quantized models
model.save_pretrained(directory)
tokenizer.save_pretrained(directory)

print(f"Model and tokenizer saved to {directory}")