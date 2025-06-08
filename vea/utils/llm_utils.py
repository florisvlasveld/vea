import os
import time
import logging
from typing import Optional

import openai
import anthropic
import google.generativeai as genai

from .output_utils import truncate_prompt

logger = logging.getLogger(__name__)


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
                response = chat.send_message(
                    prompt,
                    generation_config={"temperature": 0.3, "max_output_tokens": 16384},
                )
                usage = getattr(response, "usage_metadata", None)
                if usage:
                    prompt_tokens = getattr(usage, "prompt_token_count", None)
                    completion_tokens = getattr(usage, "candidates_token_count", None)
                    total_tokens = getattr(usage, "total_token_count", None)
                    logger.info(
                        "Gemini tokens used: prompt=%s, response=%s, total=%s",
                        prompt_tokens,
                        completion_tokens,
                        total_tokens if total_tokens is not None else ((prompt_tokens or 0) + (completion_tokens or 0)),
                    )

                return response.text.strip()
            except Exception as e:
                wait = 2 ** attempt
                logger.warning(
                    f"Gemini request failed (attempt {attempt + 1}): {e}; retrying in {wait}s"
                )
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
                    messages=[{"role": "user", "content": prompt}],
                )

                usage = getattr(result, "usage", None)
                if usage:
                    prompt_tokens = getattr(usage, "input_tokens", None)
                    completion_tokens = getattr(usage, "output_tokens", None)
                    total_tokens = (
                        (prompt_tokens or 0) + (completion_tokens or 0)
                        if prompt_tokens is not None and completion_tokens is not None
                        else None
                    )
                    logger.info(
                        "Claude tokens used: prompt=%s, response=%s, total=%s",
                        prompt_tokens,
                        completion_tokens,
                        total_tokens,
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

            kwargs = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
            }

            if not is_restrictive:
                kwargs["temperature"] = 0.3
                kwargs["max_tokens"] = 16384

            response = client.chat.completions.create(**kwargs)

            usage = getattr(response, "usage", None)
            if usage:
                logger.info(
                    "OpenAI tokens used: prompt=%s, completion=%s, total=%s",
                    getattr(usage, "prompt_tokens", None),
                    getattr(usage, "completion_tokens", None),
                    getattr(usage, "total_tokens", None),
                )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error("OpenAI request failed: %s", e)
            raise
