import os
import time
import logging
from typing import Optional

import openai
import anthropic
import google.generativeai as genai

from .output_utils import truncate_prompt

logger = logging.getLogger(__name__)


def is_chat_model(model: str) -> bool:
    """Return True if the OpenAI model should use the chat endpoint."""
    if not model:
        return True

    m = model.lower()

    # Fine-tuned chat models start with "ft:" followed by the base model name
    if m.startswith("ft:"):
        m = m.split(":", 1)[1]

    chat_prefixes = ("gpt-", "o4-")
    chat_exact = {"gpt-4", "gpt-4o", "gpt-3.5-turbo", "gpt-3.5-turbo-16k"}

    return m.startswith(chat_prefixes) or m in chat_exact


def run_llm_prompt(prompt: str, model: Optional[str] = None, *, quiet: bool = False) -> str:

    if quiet:
        logger.debug("Sending collected data to %s...", model)
    else:
        logger.info("Sending collected data to %s...", model)

    openai.api_key = os.getenv("OPENAI_API_KEY", os.getenv("OPENAI_KEY", ""))
    anthropic.api_key = os.getenv("ANTHROPIC_API_KEY", "")
    genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))

    model = model or os.getenv("MODEL", "gpt-4")

    if model.startswith("gemini-"):
        model_obj = genai.GenerativeModel(model)
        chat = model_obj.start_chat(history=[])
        for attempt in range(5):
            try:
                response = chat.send_message(prompt, generation_config={"temperature": 0.3, "max_output_tokens": 16384})
                return response.text.strip()
            except Exception as e:
                wait = 2 ** attempt
                logger.warning(f"Gemini request failed (attempt {attempt + 1}): {e}; retrying in {wait}s")
                time.sleep(wait)
        raise RuntimeError("Failed to get a response from Gemini after multiple attempts.")

    elif model.lower().startswith("claude"):
        client = anthropic.Anthropic()
        prompt = truncate_prompt(prompt, max_tokens=180000)
        for attempt in range(3):
            try:
                result = client.messages.create(
                    model=model,
                    max_tokens=16384,
                    temperature=0.3,
                    messages=[{"role": "user", "content": prompt}]
                )
                return result.content[0].text.strip()
            except Exception as e:
                wait = 2 ** attempt
                logger.warning(f"Claude request failed (attempt {attempt + 1}): {e}; retrying in {wait}s")
                time.sleep(wait)
        raise RuntimeError("Failed to get a response from Claude after multiple attempts.")

    else:
        try:
            client = openai.OpenAI()

            restrictive_models = ("o", "gpt-4o")
            is_restrictive = model.startswith(restrictive_models)

            if is_chat_model(model):
                endpoint = "chat"
                kwargs = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                }
            else:
                endpoint = "completion"
                kwargs = {
                    "model": model,
                    "prompt": prompt,
                }

            if not is_restrictive:
                kwargs["temperature"] = 0.3
                kwargs["max_tokens"] = 16384

            if endpoint == "chat":
                logger.debug("Using chat completions endpoint")
                response = client.chat.completions.create(**kwargs)
                return response.choices[0].message.content.strip()
            else:
                logger.debug("Using completions endpoint")
                response = client.completions.create(**kwargs)
                return response.choices[0].text.strip()

        except Exception as e:
            logger.error("OpenAI request failed: %s", e)
            raise
