"""Native bridge to the vendored Academic Research Suite (ARS-Codex).

The bridge is intentionally a router, not a second research implementation:
it resolves a request to one of the five audited ARS workflows and exposes the
local prompt recipe for an explicitly chosen workflow.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkflowRoute:
    """A deterministic route into the vendored ARS workflow recipes."""

    workflow: str
    mode: str
    recipe: Path
    reason: str


_WORKFLOWS = {
    "deep-research",
    "academic-paper",
    "academic-paper-reviewer",
    "academic-pipeline",
    "experiment-agent",
}
_ALIASES = {
    "research": "deep-research",
    "deep-research": "deep-research",
    "paper": "academic-paper",
    "academic-paper": "academic-paper",
    "review": "academic-paper-reviewer",
    "reviewer": "academic-paper-reviewer",
    "academic-paper-reviewer": "academic-paper-reviewer",
    "pipeline": "academic-pipeline",
    "academic-pipeline": "academic-pipeline",
    "experiment": "experiment-agent",
    "experiment-agent": "experiment-agent",
}


def skill_root() -> Path:
    """Return the repository-vendored ARS skill root."""
    return Path(__file__).resolve().parents[2] / "skills" / "academic-research-suite"


def manifest() -> dict:
    """Load the vendored manifest and fail clearly if the integration is absent."""
    path = skill_root() / "manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"ARS-Codex manifest unavailable: {path}") from exc
    if not isinstance(data, dict) or data.get("name") != "academic-research-suite":
        raise RuntimeError("invalid ARS-Codex manifest")
    return data


def _workflow_path(workflow: str) -> Path:
    path = skill_root() / "ars" / workflow / "WORKFLOW.md"
    if workflow not in _WORKFLOWS or not path.is_file():
        raise RuntimeError(f"ARS-Codex workflow unavailable: {workflow}")
    return path


def route_request(request: str, workflow: str | None = None) -> WorkflowRoute:
    """Route an explicit alias or infer a conservative workflow from the request."""
    text = request.strip()
    requested = (workflow or "").strip().lower()
    if requested:
        selected = _ALIASES.get(requested)
        if selected is None:
            raise ValueError(f"unknown ARS workflow: {workflow}")
        return WorkflowRoute(selected, "explicit", _workflow_path(selected), "explicit workflow")

    low = text.casefold()
    if re.search(r"\b(review|reviewer|referee|peer review)\b", low):
        selected, reason = "academic-paper-reviewer", "review language detected"
    elif re.search(r"\b(experiment|replicate|reproduc|statistical|analysis plan)\b", low):
        selected, reason = "experiment-agent", "experiment or reproducibility language detected"
    elif re.search(r"\b(pipeline|end[- ]to[- ]end|full study)\b", low):
        selected, reason = "academic-pipeline", "end-to-end workflow language detected"
    elif re.search(r"\b(paper|manuscript|abstract|citation|outline)\b", low):
        selected, reason = "academic-paper", "paper-authoring language detected"
    else:
        selected, reason = "deep-research", "default evidence-first research route"
    return WorkflowRoute(selected, "inferred", _workflow_path(selected), reason)


def workflow_text(route: WorkflowRoute) -> str:
    """Read a workflow recipe only after the caller has selected its route."""
    return route.recipe.read_text(encoding="utf-8")
