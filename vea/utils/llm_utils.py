import os
import time
import logging
from typing import Optional

import openai
import anthropic
import google.generativeai as genai

from .output_utils import truncate_prompt

logger = logging.getLogger(__name__)


def is_completion_model(model: str) -> bool:
    """Return True if ``model`` uses the OpenAI completions endpoint."""

    completion_prefixes = (
        "o1-",
        "o2-",
        "o3-",
        "o4-",
        "text-",
        "babbage-",
        "curie-",
        "ada-",
        "davinci-",
    )
    return any(model.startswith(p) for p in completion_prefixes) or "-instruct" in model


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

            # Determine whether to use the chat or completion endpoint
            is_completion = is_completion_model(model)

            if is_completion:
                kwargs = {
                    "model": model,
                    "prompt": prompt,
                }
                if not is_restrictive:
                    kwargs["temperature"] = 0.3
                    kwargs["max_tokens"] = 16384
                response = client.completions.create(**kwargs)
                return response.choices[0].text.strip()

            kwargs = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
            }

            if not is_restrictive:
                kwargs["temperature"] = 0.3
                kwargs["max_tokens"] = 16384

            response = client.chat.completions.create(**kwargs)
            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error("OpenAI request failed: %s", e)
            raise
