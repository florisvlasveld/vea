import typer
from dotenv import load_dotenv

from ..loaders import gcal, gmail, journals, extras, todoist, slack as slack_loader

from . import auth, daily, weekly, prepare_event
from .utils import _find_upcoming_events

app = typer.Typer(help="Vea: Generate a personalized daily briefing or weekly summary.")

load_dotenv()

if hasattr(app, "add_typer"):
    # Typer available: register sub-apps normally
    app.add_typer(auth.app, name="auth")
    app.add_typer(daily.app, name="daily")
    app.add_typer(weekly.app, name="weekly")
    app.add_typer(prepare_event.app, name="prepare-event")
else:  # Fallback for minimal Typer stubs in tests
    app.command("auth")(auth.auth_command)
    app.command("daily")(daily.generate)
    app.command("weekly")(weekly.generate_weekly_summary)
    app.command("prepare-event")(prepare_event.prepare_event)

__all__ = [
    "app",
    "gcal",
    "gmail",
    "journals",
    "extras",
    "todoist",
    "slack_loader",
    "_find_upcoming_events",
]
