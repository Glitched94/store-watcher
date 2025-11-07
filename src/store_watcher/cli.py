from __future__ import annotations

import os
from pathlib import Path

import typer
import uvicorn

from .core import run_watcher
from .state import load_state as load_any
from .state import save_state as save_any
from .ui import create_app

app = typer.Typer(help="Watch store pages and alert on new/restocked items.")


@app.command("watch")
def watch(
    site: str = typer.Option("disneystore", help="Adapter/site to use (sfcc/disneystore)"),
    url: str = typer.Option(None, help="Override single URL"),
    urls: str = typer.Option(None, help="Comma or newline separated list of URLs"),
    every: int = typer.Option(300, "--every", "-e", help="Check interval in seconds"),
    restock: int = typer.Option(24, "--restock", "-r", help="Restock window in hours"),
    include_re: str = typer.Option("", help="Python regex to include URLs"),
    exclude_re: str = typer.Option("", help="Python regex to exclude URLs"),
    once: bool = typer.Option(False, help="Run a single tick then exit"),
    env: str | None = typer.Option(None, "--env", help="Path to a .env file to load"),
):
    run_watcher(
        site=site,
        url_override=urls or url,  # pass whichever is set; core will split
        interval=every,
        restock_hours=restock,
        include_re=include_re or None,
        exclude_re=exclude_re or None,
        once=once,
        dotenv_path=env,
    )


@app.command("state")
def state_cmd(
    path: str = typer.Option("seen_items.json", help="Path to state JSON"),
    action: str = typer.Argument("show", help="show | clear"),
):
    """
    Inspect or clear the local state file.
    """
    p = Path(path)
    if action == "show":
        state = load_any(p)
        typer.echo(f"Items: {len(state)}")
        for code, info in list(state.items())[:20]:
            status = info.get("status")
            since = info.get("status_since")
            url = info.get("url")
            typer.echo(f"- {code}: status={status} since={since}")
            if url:
                typer.echo(f"    url={url}")
        if len(state) > 20:
            typer.echo(f"... ({len(state)-20} more)")
    elif action == "clear":
        if p.exists():
            p.unlink()
            typer.echo("State cleared.")
        else:
            typer.echo("No state file found.")
    else:
        raise typer.BadParameter("action must be 'show' or 'clear'")


@app.command("migrate")
def migrate_json_to_sqlite(
    json_path: str = typer.Option("seen_items.json", help="Path to legacy JSON state"),
    sqlite_path: str = typer.Option("state.db", help="Destination SQLite file"),
):
    """
    Migrate a JSON state file into SQLite. This respects your existing migrations
    (legacy list/dict -> status machine) during load.
    """
    os.environ["STATE_DB"] = sqlite_path  # force save to SQLite
    state = {}
    jp = Path(json_path)
    if jp.exists():
        # temporarily force JSON load by unsetting STATE_DB for the read
        prev = os.environ.pop("STATE_DB", None)
        try:
            state = load_any(jp)
        finally:
            if prev is not None:
                os.environ["STATE_DB"] = prev
    else:
        raise typer.Exit(f"JSON not found: {json_path}")

    save_any(state)  # goes to SQLite because STATE_DB is set
    typer.echo(f"Migrated {len(state)} records -> {sqlite_path}")


@app.command("ui")
def ui(
    host: str = typer.Option("127.0.0.1", help="Bind address"),
    port: int = typer.Option(8000, help="Port"),
    env: str | None = typer.Option(None, "--env", help="Path to a .env file to load for the UI"),
    reload: bool = typer.Option(False, help="Auto-reload on code changes (dev)"),
):
    app = create_app(dotenv_path=env)
    uvicorn.run(app, host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
