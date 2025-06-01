# Vea

Generate a personalized executive daily briefing with a single command-line tool. Pulls in signals from your Google Calendar, Gmail, Todoist, local Markdown notes, and Slack – then condenses it all using AI into a readable summary.


## Setup

### 1. Google APIs

Download your OAuth credentials from the [Google Cloud Console](https://console.cloud.google.com/apis/credentials), and save the file as:

```bash
credentials/client_secret.json
```

### 2. Authorize access (first time only)

You only need to do this once per environment.

```bash
vea auth calendar gmail
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


## Usage

⚠️ Note: Depending on how much data is being processed (calendar events, emails, tasks, notes, Slack messages), generating your daily brief may take several minutes or even significantly longer to complete. Some models may not be able to handle the amount of input data.

```bash
vea daily \
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

Run `vea daily --help` to view all available options.

### AI Summary Engine

You can choose between OpenAI, Anthropic (Claude), or Google Gemini models. The tool builds a structured prompt with:

- Calendar events
- Emails (inbox, sent, and extra labels)
- Todoist tasks
- Slack messages
- Journal entries
- Additional notes

Then it asks your model of choice to create a concise, structured daily brief.

### Vea Instructions in Today’s Journal

You can give special instructions to the AI by writing a note to `Vea` in **today’s journal entry**.

Add a bullet starting with `Vea` or `[[Vea]]` in your Markdown journal file:

```markdown
- [[Vea]] Include a short list of team birthdays this week
```

These instructions are:
- Only processed if they appear in **today’s journal file**.
- Ignored in all other journal entries.
- Treated as **binding** — the AI will attempt to follow them, e.g.:
  - Add custom insights.
  - Emphasize specific events or people.
  - Include extra sections or summaries.

> Example use cases:
> - “Vea, remind me to be diplomatic in the meeting with John.”
> - “Vea, include a summary of the [[Monthly Report]].”

🪄 This is a powerful way to tailor your daily brief without changing any code.


## Slack Integration

To include relevant messages from Slack in your daily brief, you'll need to create and install a Slack App that can access channel history.

### 1. Create a Slack App

Go to: [https://api.slack.com/apps](https://api.slack.com/apps)

- Click **"Create New App"**
- Choose **"From scratch"**
- Give it a name like `Daily Brief Assistant`
- Select your Slack workspace

### 2. Add OAuth Scopes

Navigate to **OAuth & Permissions** in the left-hand menu and under **Scopes → User Token Scopes**, add the following:

```
channels:history
channels:read
groups:history
groups:read
im:history
im:read
mpim:history
mpim:read
users:read
```

These scopes allow the app to:
- Read messages from public, private, and direct channels
- Identify users (to show who said what)

> ⚠️ You may need to re-authorize the app if you change scopes later.

### 3. Install the App to your workspace

In **OAuth & Permissions**, scroll to the top and click **"Install App to Workspace"**.

This will generate a **Bot Token**, which you’ll use as `SLACK_TOKEN` in your `.env` file.

> ⚠️ Keep this token secret — it provides read access to your Slack data.

### 4. Configure your `.env` file

Add this to your `.env`:
```env
SLACK_TOKEN=xoxb-your-bot-token
```

### 5. Enable Slack loading

By default, Slack loading is enabled when you run `vea daily`. If you want to skip it:

```bash
vea daily --include-slack False
```


## A note from the author

This tool, including this README, was 100% vibe-coded with ChatGPT 4o. Any bugs are probably just hallucinated features.