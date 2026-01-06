from __future__ import annotations

import json
from pathlib import Path

import typer
import uvicorn
from dotenv import load_dotenv

from store_watcher.ui import create_app

from .core import MULTIPLE_URLS_ERROR, normalize_single_url, run_watcher

# NEW: use the db layer directly
from .db.items import load_items_dict, save_items

app = typer.Typer(help="Watch store pages and alert on new/restocked items.")


@app.command("watch")
def watch(
    site: str = typer.Option("disneystore", help="Adapter/site to use (sfcc/disneystore)"),
    url: str = typer.Option(None, help="Target URL (overrides TARGET_URL env)"),
    every: int = typer.Option(300, "--every", "-e", help="Check interval in seconds"),
    restock: int = typer.Option(24, "--restock", "-r", help="Restock window in hours"),
    include_re: str = typer.Option("", help="Python regex to include URLs"),
    exclude_re: str = typer.Option("", help="Python regex to exclude URLs"),
    once: bool = typer.Option(False, help="Run a single tick then exit"),
    env: str | None = typer.Option(None, "--env", help="Path to a .env file to load"),
) -> None:
    try:
        single_url = normalize_single_url(url)
    except ValueError:
        raise typer.BadParameter(MULTIPLE_URLS_ERROR)

    run_watcher(
        site=site,
        url_override=single_url or None,
        interval=every,
        restock_hours=restock,
        include_re=include_re or None,
        exclude_re=exclude_re or None,
        once=once,
        dotenv_path=env,
    )


@app.command("state")
def state_cmd(
    sqlite_path: str = typer.Option("state.db", help="Path to SQLite DB (STATE_DB)"),
    action: str = typer.Argument("show", help="show | clear"),
) -> None:
    """
    Inspect or clear items stored in SQLite.
    """
    # Ensure db path exists (read) / use for clear
    dbp = Path(sqlite_path)

    if action == "show":
        # Temporarily point the loader to this db path
        # The db.items helpers read the path directly, so we pass it through save/load functions
        # Here we just want to load and count:
        items = load_items_dict(dbp)
        typer.echo(f"Items: {len(items)}")
        for key, info in list(items.items())[:20]:
            status = info.get("status")
            since = info.get("status_since")
            url = info.get("url")
            typer.echo(f"- {key}: status={status} since={since}")
            if url:
                typer.echo(f"    url={url}")
        if len(items) > 20:
            typer.echo(f"... ({len(items)-20} more)")
    elif action == "clear":
        if dbp.exists():
            dbp.unlink()
            typer.echo("SQLite DB removed.")
        else:
            typer.echo("No SQLite DB found.")
    else:
        raise typer.BadParameter("action must be 'show' or 'clear'")


@app.command("migrate")
def migrate_json_to_sqlite(
    json_path: str = typer.Option("seen_items.json", help="Path to legacy JSON items"),
    sqlite_path: str = typer.Option("state.db", help="Destination SQLite file"),
) -> None:
    """
    Migrate a JSON items dict directly into SQLite.
    Expects the JSON to already be a mapping of:
      { key: { url, first_seen, status, status_since, [name], [host], [image] } }
    """
    jp = Path(json_path)
    if not jp.exists():
        typer.echo(f"JSON not found: {json_path}")
        raise typer.Exit(code=1)

    try:
        data = json.loads(jp.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            typer.echo("JSON must be an object mapping keys to item records.")
            raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Failed to read JSON: {e}")
        raise typer.Exit(code=1)

    dbp = Path(sqlite_path)
    save_items(data, dbp)
    typer.echo(f"Migrated {len(data)} records -> {sqlite_path}")


@app.command("ui")
def ui(
    host: str = typer.Option("127.0.0.1", help="Bind address"),
    port: int = typer.Option(8000, help="Port"),
    env: str | None = typer.Option(None, "--env", help="Path to a .env file to load for the UI"),
    reload: bool = typer.Option(False, help="Auto-reload on code changes (dev)"),
) -> None:
    load_dotenv(dotenv_path=env)
    app = create_app(dotenv_path=env)
    uvicorn.run(app, host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
