import typer
from dotenv import load_dotenv, find_dotenv

from ..loaders import gcal, gmail, journals, extras, todoist, slack as slack_loader

from . import auth, daily, weekly, prepare_event, check_for_tasks, indexing
from .utils import _find_upcoming_events, _find_current_events

app = typer.Typer(help="Vea: Generate personalized briefings and checklists.")

load_dotenv(find_dotenv(usecwd=True))

if hasattr(app, "add_typer"):
    # Typer is installed: mount sub-apps using their default command names
    app.add_typer(auth.app)
    app.add_typer(daily.app)
    app.add_typer(weekly.app)
    app.add_typer(prepare_event.app)
    app.add_typer(check_for_tasks.app)
    app.add_typer(indexing.app)
else:  # Fallback for minimal Typer stubs in tests
    app.command("auth")(auth.auth_command)
    app.command("daily")(daily.generate)
    app.command("weekly")(weekly.generate_weekly_summary)
    app.command("prepare-event")(prepare_event.prepare_event)
    app.command("check-for-tasks")(check_for_tasks.check_for_tasks)
    app.command("index-journals")(indexing.index_journals)
    app.command("index-emails")(indexing.index_emails)

__all__ = [
    "app",
    "gcal",
    "gmail",
    "journals",
    "extras",
    "todoist",
    "slack_loader",
    "indexing",
    "_find_upcoming_events",
    "_find_current_events",
]
