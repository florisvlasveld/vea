# 📅 Daily Brief

Generate a personalized executive daily briefing with a single command-line tool. Pulls in signals from your Google Calendar, Gmail, Todoist, local Markdown notes, and even Slack – then condenses it all using AI into a readable summary.

## 🔧 Setup

### 1. Google APIs

Download your OAuth credentials from the [Google Cloud Console](https://console.cloud.google.com/apis/credentials), and save the file as:

```bash
credentials/client_secret.json
```

### 2. Authorize access (first time only)

You only need to do this once per environment.

```bash
daily-brief auth calendar gmail
```

> This will open a browser window for Google OAuth. Tokens are saved in `.credentials/`.

### 3. Configure environment

Copy `.env.example` to `.env` and fill in the values you need:

- `OPENAI_API_KEY`
- `TODOIST_TOKEN`
- `SLACK_TOKEN`
- `BIO`
- Et cetera.

### 4. Install the CLI

You can use either `pipx` or a virtual environment.

**Using pipx (recommended):**
```bash
pipx install --editable .
```

**Using a virtualenv:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 🚀 Usage

⚠️ Note: Depending on how much data is being processed (calendar events, emails, tasks, notes, Slack messages), generating your daily brief may take several minutes to complete. Some models may not be able to handle the amount of input data.

```bash
daily-brief generate \
  --journal-dir ~/Logseq/journals \
  --extra-dir ~/Logseq/pages \
  --date 2025-05-26 \
  --save-path ~/DailyBrief/ \
  --project-name "My Todoist Project" \
  --calendar-blacklist "Lunch, Focus time" \
  --debug
```

### Key options

- `--journal-dir`: Directory with Markdown journal files (named like `YYYY-MM-DD.md`)
- `--extra-dir`: Directory with extra `.md` files (e.g. notes, projects)
- `--project-name`: Filter tasks by Todoist project
- `--calendar-blacklist`: Additional substrings to filter out calendar events (adds to .env)
- `--model`: Use a specific LLM (e.g., `o4-mini`, `claude-3-7-sonnet-latest`, or `gemini-2.5-pro-preview-05-06`)
- `--quiet`: Suppress printing output to the console
- `--debug`: Outputs debug information to the console

Run `daily-brief generate --help` to view all available options.

## 🤖 AI Summary Engine

You can choose between OpenAI, Anthropic (Claude), or Google Gemini models. The tool builds a structured prompt with:

- Calendar events
- Emails (inbox, sent, and extra labels)
- Todoist tasks
- Slack messages
- Journal entries
- Additional notes

Then it asks your model of choice to create a concise, structured daily brief.

## 🧙 A note from the author

This tool, including this README, was 100% vibe-coded with [ChatGPT-4o](https://openai.com/chatgpt). Any bugs are probably just hallucinated features. 😄