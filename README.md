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
  --extras-dir ~/Logseq/pages \
  --date 2025-05-26 \
  --save-path ~/DailyBrief/ \
  --todoist-project "My Todoist Project" \
  --calendar-blacklist "Lunch, Focus time" \
  --skip-past-events \
  --save-markdown
```

### Daily command options

Below is a complete list of options for `vea daily` (run `vea daily --help` to see this at any time):

- `--date` – Date to generate the brief for (defaults to today)
- `--journal-dir` – Directory with Markdown journal files (named like `YYYY-MM-DD.md`)
- `--journal-days` – Number of past journal days to include (default: 21)
- `--extras-dir` – Directory with extra `.md` files (e.g. notes, projects)
- `--gmail-labels` – Additional Gmail labels to include besides inbox and sent mail
- `--todoist-project` – Filter tasks by Todoist project
- `--my-email` – Your email address (used to ignore declined events)
- `--include-slack / --no-include-slack` – Include recent Slack messages (default: true)
- `--calendar-blacklist` – Comma-separated substrings to filter out calendar events (overrides `CALENDAR_EVENT_BLACKLIST`)
- `--skip-past-events` – Ignore calendar events that have already started today
- `--save-markdown / --no-save-markdown` – Write the summary to a Markdown file (default: true)
- `--save-pdf` – Save the summary as a PDF
- `--save-path` – Custom file path or directory for the output
- `--prompt-file` – Path to a custom prompt file
- `--model` – LLM to use for summarization (e.g. `o4-mini`, `claude-3-7-sonnet-latest`, `gemini-2.5-pro-preview-05-06`)
- `--skip-path-checks` – Skip validation of input/output paths
- `--debug` – Enable debug logging
- `--quiet` – Suppress printing the summary to stdout

### Weekly summaries

You can also generate a weekly summary (a so-called “weekly heartbeat”) using:

```bash
vea weekly --week=22 --journal-dir ~/Logseq/journals --extras-dir ~/Logseq/pages --save-markdown
```

The `weekly` command supports input like `2025-W22`, `2025-22`, just `22` (current year assumed), or a date such as `2025-05-28`.

This will produce a concise, narrative-style summary of the week’s activities, based on your journal and extras entries. The output can be saved as a Markdown and/or PDF file.

### Weekly command options

Run `vea weekly --help` to see all options. The main ones are:

- `--week` – Week to summarize (e.g. `2025-W22`, `2025-22`, `22`, or a date)
- `--journal-dir` – Directory containing journal files
- `--journal-days` – Number of past journal days to load for context (default: 21)
- `--extras-dir` – Directory with additional `.md` notes to include
- `--save-markdown` – Write the weekly summary to a Markdown file
- `--save-pdf` – Save the summary as a PDF
- `--save-path` – Custom output directory or file path
- `--prompt-file` – Path to a custom prompt file
- `--model` – LLM used for summarization
- `--skip-path-checks` – Skip validation of input/output paths
- `--debug` – Enable debug logging
- `--quiet` – Suppress output to stdout

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

You can give special instructions to the AI for the daily briefing by writing a note to `Vea` in **today’s journal entry**.

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

This is a powerful way to tailor your daily brief without changing any code.


## Slack Integration

To include relevant messages from Slack in your daily briefing, you'll need to create and install a Slack App that can access channel history.

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