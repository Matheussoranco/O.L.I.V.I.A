"""Native ARS-Codex router integration."""

from olivia.academic_research import manifest, route_request, skill_root, workflow_text


def test_ars_manifest_and_all_workflow_routes_are_available():
    assert manifest()["adapter_version"] == "0.1.28"
    for alias in ("research", "paper", "review", "pipeline", "experiment"):
        route = route_request("request", workflow=alias)
        assert route.recipe.is_file()
        assert len(workflow_text(route)) > 100


def test_ars_router_infers_review_and_defaults_to_deep_research():
    assert route_request("review this manuscript").workflow == "academic-paper-reviewer"
    assert route_request("find evidence about spaced practice").workflow == "deep-research"
    assert skill_root().is_dir()
