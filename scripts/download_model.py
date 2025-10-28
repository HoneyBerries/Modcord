import os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, AutoProcessor, BitsAndBytesConfig, Qwen3VLForConditionalGeneration

model_name = "Qwen/Qwen3-30B-A3B-Instruct-2507"

# Load the model with NF4 quantization
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    quantization_config=BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True
    ),
    device_map="cuda",
    dtype=torch.bfloat16  # Use bfloat16 for KV cache
)

# Load the tokenizer and processor
tokenizer = AutoTokenizer.from_pretrained(model_name)
#processor = AutoProcessor.from_pretrained(model_name)

# Define the directory to save the model
directory = "/mnt/d/AI_MODELS/modcord_custom_models/qwen3-30b-a3b-instruct-nf4"
os.makedirs(directory, exist_ok=True)

# Save the model, tokenizer, and processor
print(f"Saving model, tokenizer, and processor to {directory}...")
model.save_pretrained(directory)
tokenizer.save_pretrained(directory)
#processor.save_pretrained(directory)

print(f"Model, tokenizer, and processor saved to {directory}")
