import os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, AutoProcessor, BitsAndBytesConfig, Qwen3VLForConditionalGeneration

model_name = "Qwen/Qwen3-VL-4B-Instruct"

# Load the model with MXFP4 quantization
model = Qwen3VLForConditionalGeneration.from_pretrained(
    model_name,
    quantization_config=BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="mxfp4",  # Specify MXFP4 quantization
        bnb_4bit_use_double_quant=True
    ),
    device_map="cpu",
    dtype=torch.bfloat16  # Use bfloat16 for model weights
)

# Load the tokenizer and processor
tokenizer = AutoTokenizer.from_pretrained(model_name)
processor = AutoProcessor.from_pretrained(model_name)

# Define the directory to save the model
directory = "/mnt/d/Model Folder/modcord_custom_models/qwen3-vl-4b-instruct-mxfp4"
os.makedirs(directory, exist_ok=True)

# Save the model, tokenizer, and processor
print(f"Saving model, tokenizer, and processor to {directory}...")
model.save_pretrained(directory)
tokenizer.save_pretrained(directory)
processor.save_pretrained(directory)

print(f"Model, tokenizer, and processor saved to {directory}")
