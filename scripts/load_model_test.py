import os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, AutoProcessor, BitsAndBytesConfig, Qwen3VLForConditionalGeneration

model_name = "/mnt/d/AI_MODELS/modcord_custom_models/qwen3-30b-a3b-instruct-nf4"

model = AutoModelForCausalLM.from_pretrained(
    model_name,
    device_map="cuda",
    dtype=torch.bfloat16  # Use bfloat16 for KV cache
)

# Load the tokenizer and processor
tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)

sys_prompt = """You are a helpful assistant that provides detailed and informative answers to user queries.
When responding, ensure that your answers are clear and easy to understand.
Use examples where appropriate to illustrate your points.
Always maintain a polite and respectful tone in your responses.
If you do not know the answer to a question, respond with 'I'm sorry, I don't have that information.'"""


prompt = "Explain the theory of relativity in simple terms."

messages = [
    {"role": "system", "content": sys_prompt},
    {"role": "user", "content": prompt}
]

def generate(model, tokenizer, prompt):
    input_ids = tokenizer(prompt, return_tensors="pt").input_ids.to(model.device)
    with torch.no_grad():
        output = model.generate(input_ids, max_new_tokens=4096)
    return tokenizer.decode(output[0], skip_special_tokens=True)