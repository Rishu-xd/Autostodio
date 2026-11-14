"""Command-Line Interface for AutoStudio."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_VIDEO_QUALITY,
    validate_api_key,
)
from core.artifact_manager import ArtifactManager
from core.orchestrator import Orchestrator, OrchestratorError
from core.state_manager import StateManager
from schemas.project import ProjectConfig, ProjectStatus

console = Console(legacy_windows=False)


def print_banner():
    banner = Text()
    banner.append("[AutoStudio] ", style="bold cyan")
    banner.append("— Autonomous AI Video Production Studio", style="dim")
    console.print(Panel(banner, border_style="cyan", padding=(0, 1)))


def handle_create(args):
    """Handle project creation."""
    orchestrator = Orchestrator()
    config = ProjectConfig(
        topic=args.topic,
        video_title=args.title or "",
        target_audience=args.audience,
        video_duration=float(args.duration),
        visual_style=args.style,
        rendering_quality=args.quality,
        animation_complexity=args.complexity,
    )

    meta = orchestrator.create_project(topic=args.topic, config=config)

    console.print(f"[bold green][OK] Project created successfully![/bold green]")
    console.print(f"[cyan]Project ID :[/cyan] [bold white]{meta.project_id}[/bold white]")
    console.print(f"[cyan]Topic      :[/cyan] {meta.topic}")
    console.print(f"[cyan]Duration   :[/cyan] {meta.config.video_duration}s")
    console.print(f"[cyan]Style      :[/cyan] {meta.config.visual_style}")
    console.print(f"[cyan]Quality    :[/cyan] {meta.config.rendering_quality}")

    if args.run:
        console.print("\n[bold yellow]>> Automatically starting production pipeline...[/bold yellow]\n")
        handle_run_with_id(meta.project_id)
    else:
        console.print(f"\nTo launch the production pipeline, run:")
        console.print(f"  [bold yellow]python main.py run {meta.project_id}[/bold yellow]")


def handle_run_with_id(project_id: str):
    """Execute pipeline for a given project ID."""
    if not validate_api_key():
        console.print(
            "[bold red][ERROR] GEMINI_API_KEY is not set or is empty.[/bold red]\n"
            "Please create a [bold white].env[/bold white] file or set the GEMINI_API_KEY environment variable.\n"
            "See [cyan].env.example[/cyan] for details."
        )
        sys.exit(1)

    orchestrator = Orchestrator()

    def on_progress(stage: str, msg: str):
        console.print(f"[{stage.upper()}] {msg}", style="cyan")

    try:
        console.print(f"[bold green]>> Running pipeline for project:[/bold green] [white]{project_id}[/white]\n")
        res = orchestrator.run_pipeline(project_id, progress_callback=on_progress)
        console.print("\n[bold green][SUCCESS] Video Production Completed Successfully![/bold green]")
        if res.output_video_path:
            console.print(f"[bold cyan]Final Video MP4:[/bold cyan] [underline]{res.output_video_path}[/underline]")
    except Exception as e:
        console.print(f"\n[bold red][ERROR] Production Pipeline Failed:[/bold red] {e}")
        console.print(f"To resume from the last successful stage, run:")
        console.print(f"  [bold yellow]python main.py resume {project_id}[/bold yellow]")
        sys.exit(1)


def handle_run(args):
    handle_run_with_id(args.project_id)


def handle_resume(args):
    console.print(f"[bold cyan][RESUME] Resuming project:[/bold cyan] {args.project_id}")
    handle_run_with_id(args.project_id)


def handle_preview(args):
    """Render a fast preview."""
    orchestrator = Orchestrator()
    console.print(f"[bold yellow][PREVIEW] Rendering preview for:[/bold yellow] {args.project_id}...")
    try:
        res = orchestrator.render_preview(args.project_id)
        if res.success:
            console.print(f"[bold green][OK] Preview rendered successfully![/bold green]")
            console.print(f"Output: [cyan]{res.video_path}[/cyan] (in {res.duration_seconds:.1f}s)")
        else:
            console.print(f"[bold red][ERROR] Preview rendering failed:[/bold red] {res.error_message}")
            if res.log_path:
                console.print(f"Log: {res.log_path}")
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


def handle_render(args):
    """Render final video."""
    orchestrator = Orchestrator()
    console.print(f"[bold yellow][RENDER] Rendering final video for:[/bold yellow] {args.project_id}...")
    try:
        res = orchestrator.render_final(args.project_id, quality=args.quality)
        if res.success:
            console.print(f"[bold green][OK] Final video rendered successfully![/bold green]")
            console.print(f"Output: [cyan]{res.video_path}[/cyan] (in {res.duration_seconds:.1f}s)")
        else:
            console.print(f"[bold red][ERROR] Rendering failed:[/bold red] {res.error_message}")
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


def handle_review(args):
    """Show video inspection and review."""
    artifacts = ArtifactManager(args.project_id)
    review = artifacts.load_video_review()
    if not review:
        console.print(f"[yellow]No video review found for project '{args.project_id}'. Has it been rendered?[/yellow]")
        return

    console.print(Panel(
        f"[bold]Overall Score:[/bold] {review.overall_score}/100\n"
        f"[bold]Quality Rating:[/bold] {review.visual_quality_rating}/10\n"
        f"[bold]Approval Status:[/bold] {review.approval_status.upper()}\n\n"
        f"[bold]Summary:[/bold] {review.summary}",
        title=f"Video Review: {args.project_id}",
        border_style="cyan"
    ))

    if review.issues:
        table = Table(title="Visual Issues Detected")
        table.add_column("Category", style="cyan")
        table.add_column("Severity", style="magenta")
        table.add_column("Problem", style="white")
        table.add_column("Suggested Fix", style="green")
        for issue in review.issues:
            table.add_row(issue.category, issue.severity, issue.problem, issue.suggested_fix)
        console.print(table)


def handle_list(args):
    """List all projects in SQLite."""
    state = StateManager()
    projects = state.list_projects()
    if not projects:
        console.print("[yellow]No AutoStudio projects found. Create one with `python main.py create <topic>`.[/yellow]")
        return

    table = Table(title="AutoStudio Projects", header_style="bold cyan")
    table.add_column("Project ID", style="bold white")
    table.add_column("Title / Topic", style="white")
    table.add_column("Status", style="cyan")
    table.add_column("Current Stage", style="yellow")
    table.add_column("Est. Cost", style="green")
    table.add_column("Created", style="dim")

    for p in projects:
        status_color = "green" if p.status == ProjectStatus.COMPLETED else ("red" if p.status == ProjectStatus.FAILED else "yellow")
        table.add_row(
            p.project_id,
            p.title[:35],
            f"[{status_color}]{p.status.value}[/{status_color}]",
            p.current_stage,
            f"${p.token_usage.estimated_cost_usd:.4f}",
            p.created_at[:19].replace("T", " "),
        )

    console.print(table)


def handle_status(args):
    """Show detailed project status and stage history."""
    state = StateManager()
    p = state.get_project(args.project_id)
    if not p:
        console.print(f"[bold red]Project '{args.project_id}' not found.[/bold red]")
        return

    artifacts = ArtifactManager(args.project_id)

    status_color = "green" if p.status == ProjectStatus.COMPLETED else ("red" if p.status == ProjectStatus.FAILED else "yellow")
    info = (
        f"[bold cyan]ID:[/bold cyan] {p.project_id}\n"
        f"[bold cyan]Title:[/bold cyan] {p.title}\n"
        f"[bold cyan]Topic:[/bold cyan] {p.topic}\n"
        f"[bold cyan]Status:[/bold cyan] [{status_color}]{p.status.value}[/{status_color}]\n"
        f"[bold cyan]Current Stage:[/bold cyan] {p.current_stage}\n"
        f"[bold cyan]Visual Style:[/bold cyan] {p.config.visual_style}\n"
        f"[bold cyan]Target Duration:[/bold cyan] {p.config.video_duration}s\n"
        f"[bold cyan]Tokens Used:[/bold cyan] {p.token_usage.total_tokens} (${p.token_usage.estimated_cost_usd:.4f} USD)\n"
        f"[bold cyan]Output Video:[/bold cyan] {p.output_video_path or 'Not rendered yet'}"
    )
    console.print(Panel(info, title=f"Project Status: {p.project_id}", border_style="cyan"))

    # Stage execution history
    if p.history:
        table = Table(title="Execution History", header_style="bold magenta")
        table.add_column("Stage", style="cyan")
        table.add_column("Status", style="white")
        table.add_column("Attempt", justify="center")
        table.add_column("Duration", justify="right")
        table.add_column("Started At", style="dim")
        table.add_column("Error", style="red")

        for h in p.history:
            table.add_row(
                h.stage_name,
                h.status,
                str(h.attempt),
                f"{h.duration_seconds:.1f}s" if h.duration_seconds else "-",
                h.started_at[:19].replace("T", " "),
                h.error or "-",
            )
        console.print(table)


def handle_configure(args):
    """Configure project settings."""
    state = StateManager()
    p = state.get_project(args.project_id)
    if not p:
        console.print(f"[bold red]Project '{args.project_id}' not found.[/bold red]")
        return

    updated = False
    if args.title:
        p.config.video_title = args.title
        p.title = args.title
        updated = True
    if args.duration:
        p.config.video_duration = float(args.duration)
        updated = True
    if args.style:
        p.config.visual_style = args.style
        updated = True
    if args.quality:
        p.config.rendering_quality = args.quality
        updated = True
    if args.audience:
        p.config.target_audience = args.audience
        updated = True

    if updated:
        # Re-save metadata in database and artifact manager
        artifacts = ArtifactManager(args.project_id)
        state.update_project_status(p.project_id, p.status, p.current_stage)
        # Update config in DB directly
        with state._get_connection() as conn:
            conn.execute(
                "UPDATE projects SET title = ?, config_json = ? WHERE project_id = ?",
                (p.title, p.config.model_dump_json(), p.project_id),
            )
            conn.commit()
        artifacts.save_metadata(p)
        console.print(f"[bold green][OK] Project configuration updated for {args.project_id}[/bold green]")
    else:
        console.print("[yellow]No configuration changes provided.[/yellow]")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autostudio",
        description="AutoStudio: Autonomous AI Video Production Studio",
    )
    parser.add_argument("--debug", action="store_true", help="Show full debug tracebacks on error")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    create_parser = subparsers.add_parser("create", help="Create a new video project")
    create_parser.add_argument("topic", type=str, help="Subject or concept to explain")
    create_parser.add_argument("--title", type=str, default="", help="Custom video title")
    create_parser.add_argument("--duration", type=float, default=60.0, help="Target duration in seconds")
    create_parser.add_argument("--audience", type=str, default="curious learners and technical enthusiasts", help="Target audience")
    create_parser.add_argument(
        "--style",
        type=str,
        default="Dark Technical",
        choices=["Dark Technical", "Minimal Scientific", "Mathematical Whiteboard", "Modern Educational", "Cinematic Abstract"],
        help="Visual aesthetic theme",
    )
    create_parser.add_argument(
        "--quality",
        type=str,
        default=DEFAULT_VIDEO_QUALITY,
        choices=["low", "medium", "high"],
        help="Rendering quality",
    )
    create_parser.add_argument("--complexity", type=str, default="medium", choices=["low", "medium", "high"])
    create_parser.add_argument("--run", action="store_true", help="Start production immediately after creating")
    create_parser.set_defaults(func=handle_create)

    # run
    run_parser = subparsers.add_parser("run", help="Run the full pipeline for a project")
    run_parser.add_argument("project_id", type=str, help="Project ID")
    run_parser.set_defaults(func=handle_run)

    # resume
    resume_parser = subparsers.add_parser("resume", help="Resume an interrupted project")
    resume_parser.add_argument("project_id", type=str, help="Project ID")
    resume_parser.set_defaults(func=handle_resume)

    # preview
    prev_parser = subparsers.add_parser("preview", help="Render a quick low-res preview")
    prev_parser.add_argument("project_id", type=str, help="Project ID")
    prev_parser.set_defaults(func=handle_preview)

    # render
    render_parser = subparsers.add_parser("render", help="Render the video")
    render_parser.add_argument("project_id", type=str, help="Project ID")
    render_parser.add_argument("--quality", type=str, choices=["low", "medium", "high"], default=None)
    render_parser.set_defaults(func=handle_render)

    # review
    review_parser = subparsers.add_parser("review", help="Inspect video review for a project")
    review_parser.add_argument("project_id", type=str, help="Project ID")
    review_parser.set_defaults(func=handle_review)

    # list
    list_parser = subparsers.add_parser("list", help="List all projects")
    list_parser.set_defaults(func=handle_list)

    # status
    status_parser = subparsers.add_parser("status", help="Show project status and execution history")
    status_parser.add_argument("project_id", type=str, help="Project ID")
    status_parser.set_defaults(func=handle_status)

    # configure
    cfg_parser = subparsers.add_parser("configure", help="Update project settings")
    cfg_parser.add_argument("project_id", type=str, help="Project ID")
    cfg_parser.add_argument("--title", type=str, default=None)
    cfg_parser.add_argument("--duration", type=float, default=None)
    cfg_parser.add_argument("--style", type=str, default=None)
    cfg_parser.add_argument("--quality", type=str, default=None)
    cfg_parser.add_argument("--audience", type=str, default=None)
    cfg_parser.set_defaults(func=handle_configure)

    return parser


def cli():
    print_banner()
    parser = build_parser()
    args = parser.parse_args()

    try:
        args.func(args)
    except Exception as e:
        if args.debug:
            raise
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
