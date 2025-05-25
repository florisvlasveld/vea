from datetime import datetime, date
from pathlib import Path
import os
import time
import traceback
import openai
import google.generativeai as genai
from rich.traceback import install
import logging
import anthropic

install()
logger = logging.getLogger(__name__)

def parse_date(date_str: str | None) -> date:
    if date_str:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    return datetime.now().date()

def resolve_output_path(path_str: str | None, d: date) -> Path:
    path_str = path_str or os.environ.get("SAVE_PATH")
    if path_str is None:
        return Path.home() / "DailyBrief" / f"{d.isoformat()}.md"

    path = Path(path_str)
    if path.is_dir():
        return path / f"{d.isoformat()}.md"

    return path

def handle_exception(e: Exception):
    logger.error("Exception occurred", exc_info=e)
    traceback.print_exc()
    raise typer.Exit(code=1)

def enable_debug_logging():
    logging.basicConfig(level=logging.DEBUG)
    logger.debug("Debug logging enabled")

def truncate_section(content: list | str, max_chars: int = 10000) -> str:
    if isinstance(content, list):
        # Convert each item to string (especially for dicts)
        text = "\n".join(str(item) for item in content)
    else:
        text = str(content)
    return text[:max_chars] + ("..." if len(text) > max_chars else "")

def summarize(
    model: str,
    date: str,
    emails: list,
    calendars: list,
    tasks: list,
    journals: list,
    extras: list,
    slack: dict = None,
    bio: str = "",
    quiet: bool = False,
) -> str:

# Styling:
# - Use bold sparingly and only where already instructed.

    prompt = f"""
You are Vea, a Chief of Staff to a senior leader. Your job is to help them make better decisions, prepare well, and save time.

The leader is described as follows:

> {bio}

Today is **{date}**. Based on the provided data, generate a daily briefing with the following structure. 

_Important note: If you come across a mention of `Vea` or `[[Vea]]` in the journal entry for {date}, treat the text that follows as an additional instruction from the leader._

---

# Preparation Notes ({date})

1. **Events**
   - List calendar events for {date}, including start times. Do **not** include event descriptions.
   - Show the event time in bold (e.g., **09:00:**, or **All-day:**) followed by the event title in normal font.
   - Only mention timezones if events occur in different timezones where the time differs.
   - Include all-day events at the top of the list.
   - Skip events that have no title.
   - Show the leader's attendance status **only if it is 'tentative'**.
   - Do **not** include participant lists.

2. **Tasks**
   - Start with tasks from the structured list.
   - Also extract any **clear, actionable tasks** that the leader is responsible for from **emails** in `inbox`. **Exclude emails in `sent`**.
     - These include follow-ups, reviews, decisions, or requests that imply the leader needs to act.
     - Only include tasks that are explicit or strongly implied to require the leader’s direct action (e.g., decisions, reviews, follow-ups). Ignore vague mentions or information-only emails.
     - If a task is already in the structured list, **do not duplicate it**.
     - Do **not** extract tasks from Journal entries and the Additional Information.
     - Use your judgment to assign a **short, clear title** and a **priority** (as a number: 1 = highest, 4 = lowest).
   - Group all tasks into three categories:
     - **Due Today**
     - **Overdue** (also show how many days overdue, in italics)
     - **Extracted from Email** (if any, otherwise skip)
   - For each task, include:
     - Priority (as a number: 1 = highest, 4 = lowest)
     - Title
   - Sort tasks in all categories by priority (from highest to lowest).
   - Render each task as a Markdown checkbox (e.g., `- [ ]`) followed by the task text.
     - Format as: `- [ ] **Priority X:** Task title`

3. **Actionable Insights for Today’s Events and Tasks**
   - For each calendar event and each task **due today** (skip overdue tasks), generate **the most useful 1 to 4 actionable insights**, depending on what is genuinely helpful. 
     - Only include an insight if it adds meaningful value — do not pad the list just to reach four items.
   - Each insight should help the leader **prepare, decide, communicate, or act more effectively**, offering **specific, time-sensitive advice**. Focus on what is **decision-relevant, interpersonally important, or politically/emotionally sensitive** — avoid high-level summaries or generic observations.
   - Prioritize guidance, reminders, and risks relevant to:
     - relationships (e.g., sensitivities or history with participants)
     - open decisions or follow-ups
     - strategic priorities
     - recent developments or changes
   - Derive insights from content in Journals, Emails, Slack Messages, and Additional Information.
   - When generating insights, treat each [[...]] reference as pointing to a specific file from the Additional Information section, based on the alias-resolved mapping already applied.
   - Give more weight to **recent and marked entries** (`#notice`, `#alert`, `#observation`, `#important`).
   - Pay attention to items that **match the title or context** of the event/task (including approximate matches).
   - If two or more people have similar names, only use information for the one with an exact match.
   - Following **each insight, cite its **source(s)** in *italics*. For **journal** and **additional information** sources, wrap the filename in **backticks** (e.g., `2025_05_01`).
   - Do not generate insights for events with the title "🥪 Lunch".

---

**Style Guidelines:**
- Use a clear, friendly, and concise tone.
- Use Markdown **bulleted lists** instead of numbered lists for all insights. 
   - Always use a hyphen (-) as the bullet marker, followed by **exactly one space** before the text of the insight. For example: `- This is a correctly formatted insight.` Do not use asterisks (*) or other characters for these bullet points.
   - **Do not insert blank lines between bullet points**. Bullet items must appear one after another with no empty line in between.
- Do **not** include `markdown` as the first word in the output.
- Do not add any closing remarks, summaries, sign-offs, or additional commentary. The output must end immediately after the last required section.

---

### Collected Data:


== Calendar Events ==
Each calendar event is a dictionary with the following fields:
- `summary`: the title of the event  
- `start`: the ISO timestamp or date (if all-day)  
- `end`: the ISO timestamp or date (if all-day)  
- `start_time_zone`: the timezone of the start time  
- `end_time_zone`: the timezone of the end time  
- `attendees`: a list of dictionaries with attendee `name` and `email`  
- `my_status`: the leader's attendance status (e.g., 'accepted', 'tentative')
- `description`: optional additional notes from the calendar invite — use this **only** to generate insights in section 3.  

{calendars}


== Tasks ==
Each task is a dictionary with the following fields:
- `content`: the task title  
- `description`: optional longer task text  
- `due`: the due date (YYYY-MM-DD)  
- `project_id`: identifier for the project the task belongs to  
- `priority`: integer from 1 (highest) to 4 (lowest)

{tasks}


== Emails ==
- Emails are structured with `subject`, `from` (sender), `date`, and `body`. Only plain text content is included.
- In the JSON structure below, emails are in dinstinct categories, such as `inbox` and `sent`.
- You may extract actionable tasks from these emails for inclusion in the Tasks section, if they are clearly addressed to the leader and require action. Emails in `sent` are **not** relevant for task extraction.

{emails}


== Journals ==
- Journal entries are provided as structured data with `filename` and `content`. Use both where relevant. 
- Filenames indicate date and use the format `YYYY_MM_DD.md`.
- Journals follow the Logseq outliner format with indentation used to indicate hierarchy. Child bullets are nested under parent topics using consistent indentation. Treat deeper levels as subpoints or elaboration.
- If the journal entry for {date} contains a line that begins with `Vea` or `[[Vea]]`, treat it as a **binding instruction** written directly to you. These instructions may request:
    - additional sections or content to include
    - specific emphasis or formatting
    - insights based on certain data
- These instructions **must be followed**, unless impossible due to missing data. When following such an instruction:
    - If the instruction asks for a separate section or list, render it with its own subheading or bullet group **after section 3 (Insights)**, unless a more contextually appropriate placement is obvious.
    - Use clear formatting so the requested content stands out.

{journals}


== Additional Information ==
- Additional notes are provided as structured data with `filename` and `content`. Use both where relevant. 
- Additional notes follow the Logseq outliner format with indentation used to indicate hierarchy. Child bullets are nested under parent topics using consistent indentation. Treat deeper levels as subpoints or elaboration.
- Some journal entries include references like `[[Example]]`. These have already been resolved using a canonical alias map. For example, `[[Sample]]` or `[[Voorbeeld]]` would both resolve to `[[Example]]` if `alias:: sample, voorbeeld` was found in the `Example.md` file. You do **not** need to perform alias resolution yourself.
- Some files in Additional Information contain **Hogan personality profile data** in inline JSON format. These are individual assessments and may include values like `adjustment`, `Interpersonal Sensitivity`, `Learning Approach`, etc. 
    - This data is only present if the file contains a bullet exactly matching `[[Hogan]] assessment data in JSON format:`. The actual Hogan profile JSON data is nested under that bullet.
    - If a person’s file does *not* include this bullet, you must assume no Hogan data is available and you must not generate any insight based on Hogan profile data for that person.
    - If a person involved in the event or task **does have** Hogan profile JSON data in their file, use this to fine-tune the generated insights. 
    - **In particular**, if an event or task appears to be a **1-on-1 meeting** (e.g., the title contains `1:1`, `1-on-1`, or `one-on-one`) and Hogan profile data **is** available for the other person, **always add one additional insight** based on their Hogan profile. This should be rendered as an **additional bullet point** following the regular insights for that specific event or task.
        - This insight should be personality-informed guidance on how the leader can best communicate, influence, or collaborate with the person.
        - Focus on interpersonal sensitivity, emotional tone, likely reactions, or potential derailers.
- Some files in Additional Information may include inline CSV data (e.g., plain-text tables). If the data appears relevant to a task or event, interpret the table and extract any useful insights.


{extras}


== Slack Messages ==
Slack messages are grouped by channel name or DM identifier. Each message includes:
- `user`: the display name of the sender
- `timestamp`: ISO timestamp
- `text`: plain text content of the message

{slack}

---

Now generate the daily briefing as specified above.
"""

    if not quiet:
        logger.debug("Sending prompt to model:")
        logger.debug(prompt)

    if model.startswith("gpt-") or model.startswith("o"):
        openai.api_key = os.getenv("OPENAI_API_KEY")
        client = openai.OpenAI()
        if model.startswith("gpt-"):
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are Vea, a helpful Chief of Staff / Executive Assistant that generates daily briefings for a professional user."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                # max_tokens=16000,
            )
        elif model.startswith("o"):
            response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are Vea, a helpful Chief of Staff / Executive Assistant that generates daily briefings for a professional user."},
                {"role": "user", "content": prompt},
            ],
            # max_tokens=16000,
        )

        # Debug token usage
        logger.debug(f"Prompt tokens: {response.usage.prompt_tokens}")
        logger.debug(f"Completion tokens: {response.usage.completion_tokens}")
        logger.debug(f"Total tokens: {response.usage.total_tokens}")

        return response.choices[0].message.content.strip()

    elif model.startswith("gemini-"):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model_obj = genai.GenerativeModel(model)
        chat = model_obj.start_chat(history=[])

        for attempt in range(5):
            try:
                response = chat.send_message(prompt, generation_config={
                    "temperature": 0.3,
                    "max_output_tokens": 16000,
                })
                return response.text.strip()
            except Exception as e:
                wait = 2 ** attempt
                logger.warning(f"Gemini request failed (attempt {attempt + 1}): {e}, retrying in {wait}s")
                time.sleep(wait)

        raise RuntimeError("Failed to get a response from Gemini after multiple attempts")

    elif model.startswith("claude-"):
        # Configure Anthropic client
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        if not anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        
        client = anthropic.Anthropic(api_key=anthropic_api_key)
        
        # Set system prompt for Claude
        system_prompt = "You are Vea, a helpful Chief of Staff / Executive Assistant that generates daily briefings for a professional user."
        
        # Log input token estimate if not quiet
        if not quiet:
            estimated_tokens = len(prompt.split()) * 1.3  # Rough estimate of tokens
            logger.debug(f"Estimated input tokens: {estimated_tokens:.0f}")
            if estimated_tokens > 100000:
                logger.warning(f"Input may be too large ({estimated_tokens:.0f} estimated tokens). Claude models typically have a 100K token context window.")
        
        for attempt in range(5):
            try:
                # Create the message with stream=True
                response = client.messages.create(
                    model=model,
                    system=system_prompt,
                    max_tokens=16000,  # Increase max tokens to the maximum allowed
                    temperature=0.3,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    stream=True,  # Enable streaming
                    timeout=900,   # Set a longer timeout (15 minutes)
                )
                
                # Process the streaming response
                full_response = ""
                for chunk in response:
                    if chunk.type == "content_block_delta" and hasattr(chunk.delta, "text"):
                        text_chunk = chunk.delta.text
                        full_response += text_chunk
                        if not quiet and len(full_response) % 1000 == 0:
                            logger.debug(f"Received {len(full_response)} characters so far...")
                
                # Try to log token usage if available on the last chunk
                if hasattr(chunk, "usage") and chunk.usage:
                    logger.debug(f"Input tokens: {chunk.usage.input_tokens}")
                    logger.debug(f"Output tokens: {chunk.usage.output_tokens}")
                    logger.debug(f"Total tokens: {chunk.usage.input_tokens + chunk.usage.output_tokens}")
                
                # Check if response seems truncated
                if not quiet and len(full_response) < 2000:
                    logger.warning(f"Response seems unusually short ({len(full_response)} characters). This might indicate truncation or a problem with the model's processing.")
                
                return full_response
            
            except Exception as e:
                wait = 2 ** attempt
                logger.warning(f"Anthropic request failed (attempt {attempt + 1}): {e}, retrying in {wait}s")
                time.sleep(wait)
                
        raise RuntimeError("Failed to get a response from Anthropic Claude after multiple attempts")

    else:
        raise ValueError(f"Unsupported model: {model}")