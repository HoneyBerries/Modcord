"""
AI service for the bot.
"""

import asyncio
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

from ..config.logger import get_logger
from ..config.config import config
from ..models.action import ActionType
from ..utils.helpers import parse_action

logger = get_logger(__name__)

class AIService:
    """
    Service for handling AI model loading, inference, and batch processing.
    """
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.base_system_prompt = config.system_prompt
        self.inference_queue = asyncio.Queue()
        self._worker_task = None
        self._load_model()

    def _load_model(self):
        """
        Loads the AI model and tokenizer.
        """
        if self.model is None or self.tokenizer is None:
            model_id = "meta-llama/Llama-3.2-3B-Instruct"
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16
            )
            self.model = AutoModelForCausalLM.from_pretrained(
                model_id,
                quantization_config=bnb_config,
                device_map="auto",
                trust_remote_code=True
            ).eval()
            self.tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
            logger.info(f"AI model loaded on device: {self.model.device}")

    def start(self):
        """
        Starts the inference worker.
        """
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._inference_worker())
            logger.info("AI inference worker started.")

    def get_system_prompt(self, server_rules: str = "") -> str:
        """
        Generates the system prompt with server rules.
        """
        return self.base_system_prompt.format(SERVER_RULES=server_rules)

    async def get_appropriate_action(self, current_message: str, history: list[dict], username: str, server_rules: str = "") -> tuple[ActionType, str]:
        """
        Determines the appropriate moderation action for a message.
        """
        if not current_message or not current_message.strip():
            return ActionType.NULL, "empty message"

        system_prompt = self.get_system_prompt(server_rules)
        system_msg = {"role": "system", "content": system_prompt}
        user_msg = {"role": "user", "content": f"User {username} says: {current_message}"}

        formatted_history = []
        if history:
            for msg in reversed(history[-48:]):
                content = msg.get("content", "")
                if not isinstance(content, str) or not content.strip():
                    continue
                if msg.get("username"):
                    content = f"User {msg['username']} says: {content}"
                formatted_history.insert(0, {"role": msg.get("role", "user"), "content": content})

        messages = [system_msg] + formatted_history + [user_msg]

        assistant_response = await self.submit_inference(messages)
        return parse_action(assistant_response)

    async def submit_inference(self, messages: list[dict]) -> str:
        """
        Submits an inference request to the batch processing queue.
        """
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._inference_worker())

        future = asyncio.get_event_loop().create_future()
        await self.inference_queue.put((messages, future))
        return await future

    async def _inference_worker(self):
        """
        Worker that processes inference requests in batches.
        """
        while True:
            batch = []
            try:
                first_item = await self.inference_queue.get()
                batch.append(first_item)

                end_time = asyncio.get_event_loop().time() + 5.0
                while asyncio.get_event_loop().time() < end_time:
                    try:
                        item = await asyncio.wait_for(self.inference_queue.get(), timeout=0.1)
                        batch.append(item)
                    except asyncio.TimeoutError:
                        continue

                batch_messages = [item[0] for item in batch]
                batch_futures = [item[1] for item in batch]

                logger.info(f"Processing batch of {len(batch)} requests")

                try:
                    results = self._run_inference_batch(batch_messages)
                    for result, future in zip(results, batch_futures):
                        if not future.cancelled():
                            future.set_result(result)
                except Exception as e:
                    logger.error(f"Error processing batch: {e}", exc_info=True)
                    for future in batch_futures:
                        if not future.cancelled():
                            future.set_result("null: batch processing error")

                for _ in batch:
                    self.inference_queue.task_done()

            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
                if batch:
                    for _, future in batch:
                        if not future.cancelled():
                            future.set_result("null: worker error")
                    for _ in batch:
                        self.inference_queue.task_done()

    def _run_inference_batch(self, batch_messages: list[list[dict]]) -> list[str]:
        """
        Runs a batch of inference requests.
        """
        try:
            input_ids_list = []
            prompt_lengths = []

            for messages in batch_messages:
                ids = self.tokenizer.apply_chat_template(
                    messages,
                    tokenize=True,
                    add_generation_prompt=True,
                    return_tensors="pt"
                )
                input_ids_list.append(ids)
                prompt_lengths.append(ids.shape[1])

            input_ids = torch.cat(input_ids_list, dim=0).to(self.model.device)
            attention_mask = torch.ones_like(input_ids).to(self.model.device)

            with torch.no_grad():
                outputs = self.model.generate(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    max_new_tokens=128,
                    temperature=0.01,
                    top_p=0.9,
                    repetition_penalty=1.1,
                    do_sample=True,
                    pad_token_id=self.tokenizer.pad_token_id,
                    eos_token_id=self.tokenizer.eos_token_id,
                )

            responses = []
            for i, output in enumerate(outputs):
                new_tokens = output[prompt_lengths[i]:]
                response = self.tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
                responses.append(response)

            return responses
        except torch.cuda.OutOfMemoryError as e:
            logger.critical("GPU ran out of memory during batch processing", exc_info=True)
            return ["null: GPU memory error"] * len(batch_messages)
        except Exception as e:
            logger.error(f"Error in batch processing: {e}", exc_info=True)
            return ["null: batch processing error"] * len(batch_messages)

def get_ai_service():
    """
    Returns an instance of the AI service.
    """
    return AIService()
