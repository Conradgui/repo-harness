"""Auto Issue Fix public API facade.

The implementation is split by responsibility: configuration, GitHub access,
workspace operations, review gates, evidence rendering, runner orchestration,
and guided REPL handling. This module keeps the historical import surface stable.
"""

from __future__ import annotations

from .config import (
    AUTO_ISSUE_FIX_MODES,
    AUTO_REVIEW_MODES,
    AUTO_REVIEW_STAGES,
    AUTO_REVIEW_VERDICTS,
    GITHUB_BLOCKED_ERROR_PATTERNS,
    PUBLIC_PR_BODY_FORBIDDEN_TERMS,
    SECRET_PATTERNS,
    AutoIssueFixConfig,
    AutoIssueFixIssue,
    AutoIssueFixReviewGate,
    AutoIssueFixRunRecord,
    CommandResult,
    LiveRunContext,
)
from .evidence import (
    build_preview_review_gates,
    build_run_metrics,
    default_evidence_dir,
    default_run_id,
    default_workdir,
    portable_path,
    render_evidence_templates,
    review_gates_block_reason,
    write_evidence,
    write_evidence_file,
    write_json_evidence,
)
from .github_backend import GhCliBackend
from .guided_repl import (
    build_auto_issue_fix_arg_parser,
    config_from_args,
    guided_auto_issue_fix_argv,
    handle_auto_issue_fix_command,
    handle_auto_issue_fix_repl_command,
    run_auto_issue_fix_argv,
)
from .reviewer import build_rule_review_gates, discover_issue, score_issue
from .runner import (
    maybe_confirm_review_gate,
    run_auto_issue_fix,
    run_live_auto_issue_fix,
    run_repoharness_fix_turn,
)
from .security import (
    classify_github_error,
    issue_from_gh_payload,
    maintainer_trust_block_reason,
    normalize_repo,
    redact_text,
    require_ok,
    run_command,
)
from .workspace import (
    changed_paths,
    git_diff,
    infer_test_commands,
    run_shell_command,
    run_test_commands,
    scan_diff_gate,
)

__all__ = [
    "AUTO_ISSUE_FIX_MODES",
    "AUTO_REVIEW_MODES",
    "AUTO_REVIEW_STAGES",
    "AUTO_REVIEW_VERDICTS",
    "GITHUB_BLOCKED_ERROR_PATTERNS",
    "PUBLIC_PR_BODY_FORBIDDEN_TERMS",
    "SECRET_PATTERNS",
    "AutoIssueFixConfig",
    "AutoIssueFixIssue",
    "AutoIssueFixReviewGate",
    "AutoIssueFixRunRecord",
    "CommandResult",
    "GhCliBackend",
    "LiveRunContext",
    "build_auto_issue_fix_arg_parser",
    "build_preview_review_gates",
    "build_rule_review_gates",
    "build_run_metrics",
    "changed_paths",
    "classify_github_error",
    "config_from_args",
    "default_evidence_dir",
    "default_run_id",
    "default_workdir",
    "discover_issue",
    "git_diff",
    "guided_auto_issue_fix_argv",
    "handle_auto_issue_fix_command",
    "handle_auto_issue_fix_repl_command",
    "infer_test_commands",
    "issue_from_gh_payload",
    "maintainer_trust_block_reason",
    "maybe_confirm_review_gate",
    "normalize_repo",
    "portable_path",
    "redact_text",
    "render_evidence_templates",
    "require_ok",
    "review_gates_block_reason",
    "run_auto_issue_fix",
    "run_auto_issue_fix_argv",
    "run_command",
    "run_live_auto_issue_fix",
    "run_repoharness_fix_turn",
    "run_shell_command",
    "run_test_commands",
    "scan_diff_gate",
    "score_issue",
    "write_evidence",
    "write_evidence_file",
    "write_json_evidence",
]
