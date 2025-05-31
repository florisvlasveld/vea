"""
Summarization utilities: generate the daily brief by calling AI models.
"""

import os
import time
import logging
from datetime import date
from pathlib import Path
from typing import List, Dict, Optional, Union

import openai
import anthropic
import google.generativeai as genai

from .output_utils import truncate_prompt

logger = logging.getLogger(__name__)

APP_ROOT = Path(__file__).resolve().parents[2]
PROMPT_TEMPLATE_PATH = APP_ROOT / "prompts" / "default.prompt"


def load_prompt_template() -> str:
    """Load the detailed prompt template from file."""
    with open(PROMPT_TEMPLATE_PATH, encoding="utf-8") as f:
        return f.read()


def render_prompt(
    template: str,
    *,
    date: Union[date, str],
    bio: str,
    calendars: str,
    tasks: str,
    emails: str,
    journals: str,
    extras: str,
    slack: str = ""
) -> str:
    """Fill in the prompt template with structured data."""
    return template.format(
        date=str(date),
        bio=bio,
        calendars=calendars,
        tasks=tasks,
        emails=emails,
        journals=journals,
        extras=extras,
        slack=slack
    )


def summarize(
    model: str,
    date: date,
    emails: List,
    calendars: List,
    tasks: List,
    journals: List,
    extras: List,
    slack: Optional[Dict[str, List[Dict[str, str]]]] = None,
    bio: str = "",
    quiet: bool = False,
    debug: bool = False,
) -> str:
    """Summarize the provided data using the specified AI model (OpenAI, Claude, or Gemini)."""

    openai.api_key = os.getenv("OPENAI_API_KEY", os.getenv("OPENAI_KEY", ""))
    anthropic.api_key = os.getenv("ANTHROPIC_API_KEY", "")
    genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))

    prompt_template = load_prompt_template()
    prompt = render_prompt(
        prompt_template,
        date=date,
        bio=bio,
        calendars=str(calendars),
        tasks=str(tasks),
        emails=str(emails),
        journals=str(journals),
        extras=str(extras),
        slack=str(slack) if slack else ""
    )

    if debug:
        logger.debug("========== BEGIN PROMPT ==========")
        logger.debug(prompt)
        logger.debug("=========== END PROMPT ===========")

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
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                return result.content[0].text.strip()
            except Exception as e:
                wait = 2 ** attempt
                logger.warning(f"Anthropic request failed (attempt {attempt + 1}): {e}; retrying in {wait}s")
                time.sleep(wait)
        raise RuntimeError("Failed to get a response from Claude after multiple attempts.")

    else:
        try:
            client = openai.OpenAI()

            # Restrictive models (e.g., o4-mini, gpt-4o) only allow default sampling config
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
            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error("OpenAI request failed: %s", e)
            raise