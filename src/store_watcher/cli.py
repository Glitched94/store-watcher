from __future__ import annotations
import typer
from .core import run_watcher
from .state import load_state, save_state
from pathlib import Path

app = typer.Typer(help="Watch store pages and alert on new/restocked items.")

@app.command("watch")
def watch(
    site: str = typer.Option("disneystore", help="Adapter/site to use"),
    url: str = typer.Option(None, help="Override target URL (otherwise from .env/TARGET_URL)"),
    every: int = typer.Option(300, "--every", "-e", help="Check interval in seconds"),
    restock: int = typer.Option(24, "--restock", "-r", help="Restock window in hours"),
    include_re: str = typer.Option("", help="Python regex to include URLs"),
    exclude_re: str = typer.Option("", help="Python regex to exclude URLs"),
    once: bool = typer.Option(False, help="Run a single tick then exit"),
):
    """
    Run the watcher loop (or a single tick with --once).
    """
    run_watcher(
        site=site,
        url_override=url,
        interval=every,
        restock_hours=restock,
        include_re=include_re or None,
        exclude_re=exclude_re or None,
        once=once,
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
        state = load_state(p)
        typer.echo(f"Items: {len(state)}")
        for code, info in list(state.items())[:20]:
            typer.echo(f"- {code}: status={info.get('status')} since={info.get('status_since')} url={info.get('url')}")
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

if __name__ == "__main__":
    app()
