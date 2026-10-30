"""Read-only Member 1 -> Member 2 integration status from *local Git refs*.

No network, camera, tokens, backend imports, API calls or file mutations.
The observer reports only static interface evidence; a route's existence can
NEVER establish authentication, idempotency, real Meta calls or legal approval.

Run after a separate authorized `git fetch origin --prune`. Stale refs are
possible; this command never claims to fetch latest remote state itself.
"""
import ast
import json
from pathlib import Path
import re
import subprocess
from typing import Callable

MEMBER2_REF_PATTERN = re.compile(
    r"^origin/member2/feature/[A-Za-z0-9][A-Za-z0-9_-]{0,79}$", re.ASCII,
)
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
ALLOWED_METHODS = frozenset({"get", "post", "put", "patch", "delete"})
BACKEND_MAIN_PATH = "services/api/app/main.py"


def static_fastapi_routes(source: str) -> tuple[tuple[str, str], ...]:
    """Inspect only literal FastAPI decorators; dynamic routers are unverified."""
    tree = ast.parse(source)
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            target = decorator.func
            if not isinstance(target, ast.Attribute) or target.attr not in ALLOWED_METHODS:
                continue
            if not isinstance(target.value, ast.Name) or target.value.id != "app":
                continue
            if (not decorator.args
                    or not isinstance(decorator.args[0], ast.Constant)
                    or type(decorator.args[0].value) is not str):
                continue
            path = decorator.args[0].value
            if path.startswith("/") and len(path) <= 160:
                found.add((target.attr.upper(), path))
    return tuple(sorted(found))


def inspect_backend_routes(source: str) -> dict:
    routes = static_fastapi_routes(source)
    demo = ("POST", "/api/v1/incidents/demo") in routes
    candidate_route = any(
        method == "POST" and re.search(r"(?:candidate|ingest)", path, re.IGNORECASE)
        for method, path in routes
    )
    return {
        "route_analysis_scope": "literal_app_decorators_in_backend_main_only",
        "literal_routes_seen": len(routes),
        "demo_incident_post_detected": demo,
        "candidate_ingestion_post_detected": candidate_route,
        # Detecting a route is never evidence it is safe for real ingestion.
        "authenticated_ingestion_verified": False,
        "idempotent_ingestion_verified": False,
        "real_meta_provider_verified": False,
        "real_live_integration_verified": False,
        "candidate_ingestion_status": (
            "candidate_named_route_present_require_security_review"
            if candidate_route else "no_candidate_named_post_route_in_main"
        ),
    }


def collect_member2_status(git: Callable[..., str]) -> dict:
    """Consume only an injected/local read-only git CLI; no remote operations."""
    lines = git(
        "for-each-ref", "--sort=-committerdate", "--format=%(refname:short)",
        "refs/remotes/origin/member2/feature",
    ).splitlines()
    refs = tuple(ref.strip() for ref in lines
                 if MEMBER2_REF_PATTERN.fullmatch(ref.strip()))[:12]
    if not refs:
        return {
            "schema_version": "viil.member1.member2_status.v1",
            "source": "local_git_refs_only_not_live_remote",
            "member2_branch_found": False,
            "branch": None,
            "sha": None,
            "commit_date": None,
            "backend_route_review": None,
            "manual_review_required": True,
        }
    ref = refs[0]
    sha = git("rev-parse", "--verify", ref)
    if SHA_PATTERN.fullmatch(sha.strip()) is None:
        raise ValueError("Invalid local git revision")
    date = git("log", "-1", "--format=%cI", ref).strip()
    if len(date) > 64 or not re.fullmatch(r"[0-9T:+-]{19,64}", date):
        raise ValueError("Invalid local git commit date")
    try:
        source = git("show", f"{ref}:{BACKEND_MAIN_PATH}")
        review = inspect_backend_routes(source)
    except (ValueError, SyntaxError):
        review = None
    return {
        "schema_version": "viil.member1.member2_status.v1",
        "source": "local_git_refs_only_not_live_remote",
        "member2_branch_found": True,
        "branch": ref,
        "sha": sha.strip(),
        "commit_date": date,
        "backend_route_review": review,
        "manual_review_required": True,
    }


def local_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args], check=False, text=True,
        capture_output=True, timeout=12,
    )
    if completed.returncode != 0:
        # Git stderr may contain private remotes, paths, or tokens.
        raise ValueError("Unable to inspect local Git refs (redacted)")
    if len(completed.stdout) > 512 * 1024:
        raise ValueError("Local Git result exceeds size cap")
    return completed.stdout.strip()


def main() -> int:
    root = Path(__file__).resolve().parents[3]
    try:
        result = collect_member2_status(
            lambda *args: local_git(root, *args)
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        result = {
            "schema_version": "viil.member1.member2_status.v1",
            "source": "local_git_refs_only_not_live_remote",
            "member2_branch_found": False,
            "branch": None,
            "sha": None,
            "commit_date": None,
            "backend_route_review": None,
            "manual_review_required": True,
            "inspection_error": "local_git_unavailable_redacted",
        }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["member2_branch_found"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
