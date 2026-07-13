"""O.L.I.V.I.A. command-line interface.

``olivia ask | research | study … | tutor | lab | mcp-serve | info`` — thin
wrappers over the cognitive graph; all real logic lives in the packages.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

app = typer.Typer(
    name="olivia",
    help="O.L.I.V.I.A. — an AI agent for study, learning, and scientific discovery.",
    no_args_is_help=True,
    add_completion=False,
)
study_app = typer.Typer(help="Study tools: plans, flashcards, quizzes, spaced review.")
app.add_typer(study_app, name="study")

console = Console()


@app.command()
def ask(question: str) -> None:
    """Answer a question through the Mixture-of-Experts."""
    from olivia.core.graph import run_cycle

    state = run_cycle(question, mode="ask")
    console.print(Markdown(state.get("answer", "")))
    console.print(f"[dim]expert: {state.get('answer_expert', '?')}[/dim]")


@app.command()
def research(
    question: str,
    output: str = typer.Option("", "--output", "-o", help="Write the report markdown here."),
) -> None:
    """Run a full scientific discovery cycle."""
    from pathlib import Path

    from olivia.core.graph import run_cycle

    with console.status("running research cycle…"):
        state = run_cycle(question, mode="research")
    report = state.get("report")
    if report is None:
        console.print("[red]research cycle produced no report[/red]")
        raise typer.Exit(1)
    console.print(Markdown(report.report_markdown))
    if output:
        Path(output).write_text(report.report_markdown, encoding="utf-8")
        console.print(f"[dim]report written to {output}[/dim]")


@study_app.command("plan")
def study_plan(
    topic: str,
    goal: str = typer.Option("", help="What mastery should look like."),
    weeks: int = typer.Option(4, min=1),
    hours: float = typer.Option(5.0, help="Hours per week."),
) -> None:
    """Create a week-by-week study plan."""
    from olivia.study import make_study_plan, plan_to_markdown

    plan = make_study_plan(topic, goal=goal, weeks=weeks, hours_per_week=hours)
    console.print(Markdown(plan_to_markdown(plan)))


@study_app.command("cards")
def study_cards(
    topic: str,
    n: int = typer.Option(10, "-n", min=1),
    content_file: str = typer.Option("", help="Ground cards in this text file."),
) -> None:
    """Generate flashcards and add them to the topic's SM-2 deck."""
    from pathlib import Path

    from olivia.study import Deck, generate_flashcards

    content = Path(content_file).read_text(encoding="utf-8") if content_file else ""
    cards = generate_flashcards(topic, content=content, n=n)
    if not cards:
        console.print(
            "[yellow]No cards generated (need an LLM backend or --content-file).[/yellow]"
        )
        raise typer.Exit(1)
    deck = Deck(topic)
    added = deck.add(cards)
    console.print(f"Added {added} new cards to deck '{topic}' ({len(deck.cards)} total).")
    console.print(f"[dim]{deck.path}[/dim]")


@study_app.command("quiz")
def study_quiz(
    topic: str,
    n: int = typer.Option(5, "-n", min=1),
    content_file: str = typer.Option("", help="Ground the quiz in this text file."),
) -> None:
    """Take an interactive quiz on a topic."""
    from pathlib import Path

    from olivia.study import generate_quiz, grade_quiz

    content = Path(content_file).read_text(encoding="utf-8") if content_file else ""
    questions = generate_quiz(topic, content=content, n=n)
    if not questions:
        console.print("[yellow]No quiz generated (need an LLM backend or --content-file).[/yellow]")
        raise typer.Exit(1)

    answers: list[str] = []
    for i, q in enumerate(questions, 1):
        console.print(f"\n[bold]Q{i}.[/bold] {q.prompt}")
        for j, option in enumerate(q.options):
            console.print(f"  {chr(ord('a') + j)}) {option}")
        answers.append(typer.prompt("your answer"))

    graded = grade_quiz(questions, answers)
    console.print(
        f"\n[bold]Score: {graded['score']}/{graded['graded']} graded "
        f"({graded['percent']}%)[/bold] — {graded['total']} questions total"
    )
    for i, result in enumerate(graded["results"], 1):
        mark = {True: "[green]✓[/green]", False: "[red]✗[/red]", None: "[yellow]?[/yellow]"}[
            result["correct"]
        ]
        console.print(f"{mark} Q{i}: expected — {result['expected']}")
        if result["explanation"]:
            console.print(f"   [dim]{result['explanation']}[/dim]")


@study_app.command("review")
def study_review(topic: str) -> None:
    """Spaced-repetition review of the cards due today (SM-2)."""
    from olivia.study import Deck

    deck = Deck(topic)
    due = deck.due()
    if not due:
        console.print(f"No cards due in '{topic}' ({len(deck.cards)} cards in deck).")
        return
    console.print(f"{len(due)} cards due. Grade yourself 0 (blackout) … 5 (perfect).")
    for card in due:
        console.print(f"\n[bold]{card.front}[/bold]")
        typer.prompt("(enter to reveal)", default="", show_default=False)
        console.print(f"[green]{card.back}[/green]")
        quality = typer.prompt("quality 0-5", type=int)
        updated = deck.review(card.id, quality)
        if updated:
            console.print(f"[dim]next review in {updated.interval_days:g} day(s)[/dim]")


@app.command()
def tutor(topic: str) -> None:
    """Interactive Socratic tutoring session (Ctrl-C to end)."""
    from olivia.study import TutorSession

    session = TutorSession(topic)
    console.print(f"[bold]Tutor session: {topic}[/bold] (Ctrl-C to end)")
    console.print(Markdown(session.suggest_question()))
    try:
        while True:
            message = typer.prompt("you")
            console.print(Markdown(session.respond(message)))
    except (KeyboardInterrupt, typer.Abort):
        console.print("\n[dim]session ended[/dim]")


@app.command()
def lab(
    question: str,
    rounds: int = typer.Option(1, min=1, help="Draft→critique iterations."),
) -> None:
    """Multi-agent seminar: researcher drafts, critic attacks, writer synthesises."""
    from olivia.agents import ResearchLab

    with console.status("the lab is in session…"):
        result = ResearchLab().investigate(question, rounds=rounds)
    if result["error"]:
        console.print(f"[red]{result['error']}[/red] — an LLM backend is required.")
        raise typer.Exit(1)
    console.print(Markdown(f"## Synthesis\n\n{result['synthesis']}"))
    console.print(Markdown(f"## Critique that shaped it\n\n{result['critique']}"))


@app.command("mcp-serve")
def mcp_serve() -> None:
    """Run the MCP stdio server (for Claude Code / Claude Desktop)."""
    from olivia.mcp import serve

    serve()


@app.command()
def info() -> None:
    """Show backend and configuration status."""
    from olivia.config import settings
    from olivia.llm.client import get_client
    from olivia.tools import build_default_registry

    client = get_client()
    table = Table(title="O.L.I.V.I.A. status", show_header=False)
    table.add_row("LLM provider", settings.llm.provider)
    table.add_row("Active backend", client.name)
    table.add_row("Backend available", str(client.available))
    table.add_row("Default model", settings.llm.model)
    table.add_row("Data dir", str(settings.data_dir()))
    table.add_row("Tools", ", ".join(build_default_registry().names()))
    console.print(table)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
