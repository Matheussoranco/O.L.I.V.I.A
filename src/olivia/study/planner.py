"""Study planning — a week-by-week curriculum with an offline scaffold.

The scaffold follows a standard pedagogy arc (foundations → core → practice →
review/capstone) so even without a model the plan is a usable starting frame.
"""

from __future__ import annotations

import logging

from olivia.core.records import StudyPlan
from olivia.llm.client import LLMClient, get_client
from olivia.llm.prompts import TUTOR_SYSTEM
from olivia.llm.structured import ask_json

logger = logging.getLogger(__name__)


def _scaffold_milestones(topic: str, weeks: int) -> list[dict]:
    milestones: list[dict] = []
    for week in range(1, weeks + 1):
        if week == 1:
            title = f"Foundations of {topic}"
            practice = "Summarise each concept in one plain sentence."
            objectives = [
                f"Map the key vocabulary of {topic}",
                f"Identify the core problem {topic} addresses",
            ]
        elif week == weeks:
            title = "Review and capstone"
            practice = "Complete a small end-to-end project and self-grade it."
            objectives = [
                "Review all flashcards due this week",
                f"Teach {topic} to someone else (Feynman check)",
            ]
        elif week % 2 == 0:
            title = f"Core concepts of {topic} (part {week // 2})"
            practice = "Work 5+ exercises without notes."
            objectives = [
                f"Master the next block of {topic} theory",
                "Connect new concepts to week 1 foundations",
            ]
        else:
            title = f"Applied practice ({topic})"
            practice = "Apply this week's ideas to one realistic problem."
            objectives = [
                "Apply recent concepts to a concrete problem",
                "Log open questions for tutor sessions",
            ]
        milestones.append(
            {"week": week, "title": title, "objectives": objectives, "practice": practice}
        )
    return milestones


def make_study_plan(
    topic: str,
    goal: str = "",
    weeks: int = 4,
    hours_per_week: float = 5.0,
    client: LLMClient | None = None,
) -> StudyPlan:
    """Build a ``weeks``-long study plan for ``topic``."""
    client = client or get_client()
    weeks = max(1, int(weeks))

    if client.available:
        prompt = (
            f"Design a {weeks}-week study plan for: {topic}\n"
            f"Learner's goal: {goal or 'general mastery'}\n"
            f"Budget: {hours_per_week} hours/week.\n\n"
            "Respond as JSON: "
            '{"prerequisites": [str], "milestones": [{"week": int, "title": str, '
            '"objectives": [2-4 str], "practice": str}] with exactly one entry per week, '
            '"resources": [str]}. Sequence for spaced review: revisit earlier weeks.'
        )
        payload = ask_json(client, prompt, system=TUTOR_SYSTEM, max_tokens=2500)
        if isinstance(payload, dict) and isinstance(payload.get("milestones"), list):
            milestones = [
                {
                    "week": int(m.get("week", i)),
                    "title": str(m.get("title", f"Week {i}")),
                    "objectives": [str(o) for o in m.get("objectives", []) if str(o).strip()],
                    "practice": str(m.get("practice", "")),
                }
                for i, m in enumerate(payload["milestones"], 1)
                if isinstance(m, dict)
            ]
            if milestones:
                return StudyPlan(
                    topic=topic,
                    goal=goal,
                    prerequisites=[str(p) for p in payload.get("prerequisites", [])],
                    milestones=milestones,
                    resources=[str(r) for r in payload.get("resources", [])],
                    hours_per_week=hours_per_week,
                    weeks=len(milestones),
                )

    return StudyPlan(
        topic=topic,
        goal=goal,
        milestones=_scaffold_milestones(topic, weeks),
        resources=[f"Search: {topic} textbook", f"Search: {topic} course"],
        hours_per_week=hours_per_week,
        weeks=weeks,
    )


def plan_to_markdown(plan: StudyPlan) -> str:
    """Render a StudyPlan as readable markdown."""
    lines = [f"# Study plan: {plan.topic}", ""]
    if plan.goal:
        lines += [f"**Goal:** {plan.goal}", ""]
    lines.append(f"**Schedule:** {plan.weeks} weeks × {plan.hours_per_week:g} h/week")
    if plan.prerequisites:
        lines += ["", "**Prerequisites:** " + ", ".join(plan.prerequisites)]
    for m in plan.milestones:
        lines += ["", f"## Week {m.get('week', '?')} — {m.get('title', '')}"]
        lines += [f"- {o}" for o in m.get("objectives", [])]
        if m.get("practice"):
            lines.append(f"- **Practice:** {m['practice']}")
    if plan.resources:
        lines += ["", "## Resources"] + [f"- {r}" for r in plan.resources]
    return "\n".join(lines)
