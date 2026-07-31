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
def solve(
    problem: str,
    subject: str = typer.Option("auto", help="math | chemistry | physics | units | auto."),
) -> None:
    """Solve a STEM problem step by step (GPAI-style worked solution)."""
    from olivia.study import solution_to_markdown, solve_problem

    solution = solve_problem(problem, subject=subject)
    console.print(Markdown(solution_to_markdown(solution)))
    if solution.method == "none":
        raise typer.Exit(1)


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


@study_app.command("worksheet")
def study_worksheet(
    topic: str,
    n: int = typer.Option(5, "-n", min=1),
    difficulty: str = typer.Option("medium", help="easy | medium | hard."),
    seed: int = typer.Option(0, help="Seed for the offline problem generator."),
    output: str = typer.Option("", "--output", "-o", help="Write the worksheet here."),
) -> None:
    """Generate a practice worksheet with a worked-solution answer key."""
    from pathlib import Path

    from olivia.study import generate_worksheet, worksheet_to_markdown

    solutions = generate_worksheet(topic, n=n, difficulty=difficulty, seed=seed)
    if not solutions:
        console.print(
            "[yellow]No worksheet generated (need an LLM backend, or a maths topic "
            "like 'linear equations', 'quadratics', 'derivatives').[/yellow]"
        )
        raise typer.Exit(1)
    markdown = worksheet_to_markdown(solutions, topic=topic)
    console.print(Markdown(markdown))
    if output:
        Path(output).write_text(markdown, encoding="utf-8")
        console.print(f"[dim]worksheet written to {output}[/dim]")


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


@app.command()
def experts(
    action: str = typer.Argument("list", help="'list' or 'route'."),
    question: str = typer.Argument("", help="Question to route (for 'route')."),
) -> None:
    """List the Mixture-of-Experts panel, or show how a question would route.

    Example::

        olivia experts list
        olivia experts route "why does entropy increase?"
    """
    from olivia.experts import get_experts, route

    act = (action or "list").strip().lower()

    if act == "list":
        table = Table(title="Experts", show_header=True)
        table.add_column("name")
        table.add_column("description")
        for expert in get_experts():
            table.add_row(expert.name, expert.description)
        console.print(table)
        return

    if act == "route":
        if not question:
            console.print("[red]'route' needs a question.[/red]")
            raise typer.Exit(2)
        ranked = route(question)
        if not ranked:
            console.print("[dim]no expert scored above zero[/dim]")
            return
        table = Table(title=f"Routing: {question}", show_header=True)
        table.add_column("expert")
        table.add_column("score", justify="right")
        for expert, score in ranked:
            table.add_row(expert.name, f"{score:.3f}")
        console.print(table)
        return

    console.print(f"[red]Unknown action: {action}[/red] — try 'list' or 'route'.")
    raise typer.Exit(2)


@app.command()
def tools(
    action: str = typer.Argument("list", help="'list', 'show <name>', or 'run <name>'."),
    name: str = typer.Argument("", help="Tool name for 'show' / 'run'."),
    args: str = typer.Option("{}", "--args", help="JSON object of arguments for 'run'."),
) -> None:
    """Inspect and invoke the science tool registry.

    Example::

        olivia tools list
        olivia tools show sample_size
        olivia tools run convert_units --args '{"value": 1, "frm": "eV", "to": "J"}'
    """
    import json as _json

    from olivia.tools import build_default_registry

    registry = build_default_registry()
    act = (action or "list").strip().lower()

    if act == "list":
        table = Table(title="Tools", show_header=True)
        table.add_column("name")
        table.add_column("risk", justify="right")
        table.add_column("description")
        for tool in registry.list():
            table.add_row(tool.name, str(tool.risk), (tool.description or "").split("\n")[0])
        console.print(table)
        return

    if not name:
        console.print(f"[red]'{act}' needs a tool name.[/red]")
        raise typer.Exit(2)

    tool = registry.get(name)
    if tool is None:
        console.print(f"[red]No such tool: {name}[/red]")
        raise typer.Exit(2)

    if act == "show":
        console.print(f"[bold]{tool.name}[/bold]")
        console.print(tool.description or "")
        console.print(_json.dumps(tool.parameters, indent=2))
        return

    if act == "run":
        try:
            parsed = _json.loads(args)
        except _json.JSONDecodeError as exc:
            console.print(f"[red]--args is not valid JSON: {exc}[/red]")
            raise typer.Exit(2) from exc
        result = registry.execute(name, parsed)
        console.print(_json.dumps(result, indent=2, default=str))
        return

    console.print(f"[red]Unknown action: {action}[/red] — try 'list', 'show', or 'run'.")
    raise typer.Exit(2)


@app.command()
def notebook(
    action: str = typer.Argument("list", help="'list', 'search <query>', 'add', or 'path'."),
    query: str = typer.Argument("", help="Search query, or the text to add."),
    kind: str = typer.Option("", "--kind", "-k", help="Filter/label by entry kind."),
    tags: str = typer.Option("", "--tags", help="Comma-separated tags (for 'add')."),
    limit: int = typer.Option(20, "--limit", "-n", help="Max entries to show."),
) -> None:
    """Read and append to the research notebook (long-term memory).

    Example::

        olivia notebook list
        olivia notebook search "diffusion" --kind hypothesis
        olivia notebook add "recheck the 2019 replication" --kind todo
    """
    from olivia.memory.notebook import Notebook

    nb = Notebook()
    act = (action or "list").strip().lower()

    if act == "path":
        console.print(str(nb.path))
        return

    if act == "add":
        if not query:
            console.print("[red]'add' needs some text.[/red]")
            raise typer.Exit(2)
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        entry = nb.add(kind or "note", query, tags=tag_list)
        console.print(f"[dim]added {entry['id']} ({entry['kind']})[/dim]")
        return

    if act in {"list", "search"}:
        if act == "search":
            if not query:
                console.print("[red]'search' needs a query.[/red]")
                raise typer.Exit(2)
            found = nb.search(query, kind=kind or None, limit=limit)
        else:
            found = nb.entries(kind or None)

        if not found:
            console.print("[dim]notebook is empty[/dim]")
            return

        table = Table(show_header=True)
        table.add_column("ts")
        table.add_column("kind")
        table.add_column("content")
        for entry in found[-limit:]:
            content = entry.get("content", "").replace("\n", " ")
            table.add_row(
                entry.get("ts", ""),
                entry.get("kind", ""),
                content[:90] + ("…" if len(content) > 90 else ""),
            )
        console.print(table)
        console.print(f"[dim]{len(found)} entries — {nb.path}[/dim]")
        return

    console.print(f"[red]Unknown action: {action}[/red] — try 'list', 'search', 'add', or 'path'.")
    raise typer.Exit(2)


@app.command()
def agents(
    action: str = typer.Argument("list", help="'list' or 'show <role>'."),
    role: str = typer.Argument("", help="Role name for 'show'."),
) -> None:
    """List the sub-agent roles the research lab can staff.

    Example::

        olivia agents list
        olivia agents show critic
    """
    from olivia.agents.roles import ROLES

    act = (action or "list").strip().lower()

    if act == "list":
        table = Table(title="Sub-agent roles", show_header=True)
        table.add_column("role")
        table.add_column("tools")
        table.add_column("max turns", justify="right")
        for spec in ROLES.values():
            tool_desc = "all" if spec.tool_names is None else (", ".join(spec.tool_names) or "none")
            table.add_row(spec.name, tool_desc, str(spec.max_turns))
        console.print(table)
        return

    if act == "show":
        if not role:
            console.print("[red]'show' needs a role name.[/red]")
            raise typer.Exit(2)
        spec = ROLES.get(role)
        if spec is None:
            console.print(f"[red]No such role: {role}[/red] — try: {', '.join(ROLES)}")
            raise typer.Exit(2)
        tool_desc = "all" if spec.tool_names is None else (", ".join(spec.tool_names) or "none")
        console.print(f"[bold]{spec.name}[/bold]  tools={tool_desc}  max_turns={spec.max_turns}")
        console.print(spec.system_prompt)
        return

    console.print(f"[red]Unknown action: {action}[/red] — try 'list' or 'show'.")
    raise typer.Exit(2)


@app.command()
def learn(
    action: str = typer.Argument("stats", help="'stats' or 'rank <task_kind>'."),
    task_kind: str = typer.Argument("", help="Task kind for 'rank'."),
) -> None:
    """Show what the meta-learner has learned about strategy win-rates.

    Example::

        olivia learn stats
        olivia learn rank research
    """
    from olivia.meta.learner import get_meta_learner

    learner = get_meta_learner()
    act = (action or "stats").strip().lower()

    if act == "stats":
        stats = learner.stats()
        if not stats:
            console.print("[dim]no recorded outcomes yet[/dim]")
            return
        # stats() returns {"total": int, "by_task": {kind: {strategy: {...}}}};
        # flatten it so the numbers are comparable at a glance.
        by_task = stats.get("by_task", {})
        if not by_task:
            console.print(f"[dim]no recorded outcomes yet (total={stats.get('total', 0)})[/dim]")
            return
        table = Table(title="Meta-learner win rates", show_header=True)
        table.add_column("task kind")
        table.add_column("strategy")
        table.add_column("n", justify="right")
        table.add_column("wins", justify="right")
        table.add_column("win rate", justify="right")
        for kind_name, strategies in sorted(by_task.items()):
            for strategy, rec in sorted(strategies.items()):
                table.add_row(
                    kind_name,
                    strategy,
                    str(rec.get("n", "")),
                    str(rec.get("wins", "")),
                    f"{rec.get('win_rate', 0.0):.0%}",
                )
        console.print(table)
        console.print(f"[dim]{stats.get('total', 0)} recorded outcomes[/dim]")
        return

    if act == "rank":
        if not task_kind:
            console.print("[red]'rank' needs a task kind.[/red]")
            raise typer.Exit(2)
        from olivia.experts import get_experts

        names = [e.name for e in get_experts()]
        ranked = learner.rank_strategies(task_kind, names)
        table = Table(title=f"Strategies for {task_kind}", show_header=True)
        table.add_column("strategy")
        table.add_column("win rate", justify="right")
        for strategy in ranked:
            table.add_row(strategy, f"{learner.win_rate(task_kind, strategy):.0%}")
        console.print(table)
        return

    console.print(f"[red]Unknown action: {action}[/red] — try 'stats' or 'rank'.")
    raise typer.Exit(2)


@app.command()
def config(
    action: str = typer.Argument("show", help="'show', 'get <dotted.key>', or 'paths'."),
    key: str = typer.Argument("", help="Dotted key for 'get' (e.g. llm.model)."),
) -> None:
    """Inspect the effective configuration.

    Read-only by design: settings resolve per-process from the environment and
    ``.env``, so a write here would not survive the process.

    Example::

        olivia config show
        olivia config get llm.model
    """
    import json as _json

    from olivia.config import settings

    act = (action or "show").strip().lower()

    if act == "paths":
        table = Table(title="Paths", show_header=False)
        table.add_row("home_dir", str(settings.home_dir))
        table.add_row("data_dir", str(settings.data_dir()))
        console.print(table)
        return

    data = settings.model_dump(mode="json")

    def _redact(obj: object, path: str = "") -> object:
        if isinstance(obj, dict):
            return {k: _redact(v, f"{path}.{k}" if path else k) for k, v in obj.items()}
        if isinstance(obj, str) and obj and ("api_key" in path or "token" in path):
            return f"<set: {len(obj)} chars>"
        return obj

    data = _redact(data)

    if act == "get":
        if not key:
            console.print("[red]'get' needs a dotted key, e.g. llm.model[/red]")
            raise typer.Exit(2)
        node: object = data
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                console.print(f"[red]No such setting: {key}[/red]")
                raise typer.Exit(2)
            node = node[part]
        console.print(
            _json.dumps(node, indent=2) if isinstance(node, (dict, list)) else str(node)
        )
        return

    if act == "show":
        console.print(_json.dumps(data, indent=2, default=str))
        return

    console.print(f"[red]Unknown action: {action}[/red] — try 'show', 'get', or 'paths'.")
    raise typer.Exit(2)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
