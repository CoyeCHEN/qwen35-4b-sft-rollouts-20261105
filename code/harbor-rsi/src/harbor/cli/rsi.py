"""Campaign gates compose native Harbor execution; no second launcher."""

import json

import typer

rsi_app = typer.Typer(no_args_is_help=True)


@rsi_app.callback()
def rsi():
    """RSI extensions to the native Harbor CLI."""


@rsi_app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def campaign(ctx: typer.Context):
    """Prepare, validate, freeze, run and inspect native Campaigns."""
    from harbor.extensions.rsi import readiness

    try:
        readiness.main(ctx.args)
    except (ValueError, OSError) as error:
        typer.echo(
            json.dumps({"status": "BLOCKED", "error": readiness.scrub(str(error))}),
            err=True,
        )
        raise typer.Exit(2) from None
