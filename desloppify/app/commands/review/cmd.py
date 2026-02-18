"""review command: prepare or import subjective code review findings."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

from desloppify.intelligence import narrative as narrative_mod
from desloppify.intelligence import review as review_mod
from desloppify import state as state_mod
from desloppify.intelligence.integrity import subjective as subjective_integrity_mod
from desloppify.languages import runtime as lang_runtime_mod
from desloppify.utils import PROJECT_ROOT, colorize, log, rel, safe_write_text
from desloppify.engine.policy.zones import FileZoneMap
from desloppify.app.commands.review import batch_core as batch_core_mod
from desloppify.app.commands.review import batches as review_batches_mod
from desloppify.app.commands.review import import_cmd as review_import_mod
from desloppify.app.commands.review import import_helpers as import_helpers_mod
from desloppify.app.commands.review import prepare as review_prepare_mod
from desloppify.app.commands.review import runner_helpers as runner_helpers_mod
from desloppify.app.commands.review import runtime as review_runtime_mod
from desloppify.app.commands.helpers.lang import resolve_lang
from desloppify.app.commands.helpers.query import write_query
from desloppify.app.commands.helpers.runtime import command_runtime
from desloppify.app.commands.helpers.score import target_strict_score_from_config
from desloppify.app.commands.scan import scan_reporting_dimensions as reporting_dimensions_mod

REVIEW_PACKET_DIR = PROJECT_ROOT / ".desloppify" / "review_packets"
SUBAGENT_RUNS_DIR = PROJECT_ROOT / ".desloppify" / "subagents" / "runs"
CODEX_BATCH_TIMEOUT_SECONDS = 20 * 60
FOLLOWUP_SCAN_TIMEOUT_SECONDS = 45 * 60
MAX_BATCH_FINDINGS = 10
ABSTRACTION_SUB_AXES = (
    "abstraction_leverage",
    "indirection_cost",
    "interface_honesty",
)
ABSTRACTION_COMPONENT_NAMES = {
    "abstraction_leverage": "Abstraction Leverage",
    "indirection_cost": "Indirection Cost",
    "interface_honesty": "Interface Honesty",
}

LOGGER = logging.getLogger(__name__)
_write_query = write_query

def cmd_review(args) -> None:
    """Prepare or import subjective code review findings."""
    runtime = command_runtime(args)
    sp = runtime.state_path
    state = runtime.state
    lang = resolve_lang(args)

    if not lang:
        print(
            colorize("  Error: could not detect language. Use --lang.", "red"),
            file=sys.stderr,
        )
        sys.exit(1)

    if getattr(args, "run_batches", False):
        _do_run_batches(
            args,
            state,
            lang,
            sp,
            config=runtime.config,
        )
        return

    import_file = getattr(args, "import_file", None)
    holistic = True

    if import_file:
        _do_import(
            import_file,
            state,
            lang,
            sp,
            holistic=holistic,
            config=runtime.config,
        )
    else:
        _do_prepare(args, state, lang, sp, config=runtime.config, holistic=holistic)


def _subjective_at_target_dimensions(
    state_or_dim_scores: dict,
    dim_scores: dict | None = None,
    *,
    target: float,
) -> list[dict]:
    """Return scorecard-aligned subjective rows that sit on the target threshold."""
    return review_import_mod.subjective_at_target_dimensions(
        state_or_dim_scores,
        dim_scores,
        target=target,
        scorecard_subjective_entries_fn=reporting_dimensions_mod.scorecard_subjective_entries,
        matches_target_score_fn=subjective_integrity_mod.matches_target_score,
    )


def _do_prepare(args, state, lang, _state_path, *, config: dict, holistic=True):
    """Prepare mode: holistic-only review packet in query.json."""
    return review_prepare_mod.do_prepare(
        args,
        state,
        lang,
        _state_path,
        config=config,
        holistic=bool(holistic),
        setup_lang_fn=_setup_lang,
        narrative_mod=narrative_mod,
        review_mod=review_mod,
        write_query_fn=write_query,
        colorize_fn=colorize,
        log_fn=log,
    )


def _run_stamp() -> str:
    return runner_helpers_mod.run_stamp()


def _write_packet_snapshot(packet: dict, *, stamp: str) -> tuple[Path, Path]:
    """Persist immutable and blind packet snapshots for runner workflows."""
    blind_path = PROJECT_ROOT / ".desloppify" / "review_packet_blind.json"
    return runner_helpers_mod.write_packet_snapshot(
        packet,
        stamp=stamp,
        review_packet_dir=REVIEW_PACKET_DIR,
        blind_path=blind_path,
        safe_write_text_fn=safe_write_text,
    )


def _parse_batch_selection(raw: str | None, batch_count: int) -> list[int]:
    """Parse optional 1-based CSV list of batches."""
    return batch_core_mod.parse_batch_selection(raw, batch_count)


def _extract_json_payload(raw: str) -> dict | None:
    """Best-effort extraction of first JSON object from agent output text."""
    return batch_core_mod.extract_json_payload(raw, log_fn=log)


def _normalize_batch_result(
    payload: dict,
    allowed_dims: set[str],
) -> tuple[dict[str, float], list[dict], dict[str, dict], dict[str, float]]:
    """Validate and normalize one batch payload."""
    return batch_core_mod.normalize_batch_result(
        payload,
        allowed_dims,
        max_batch_findings=MAX_BATCH_FINDINGS,
        abstraction_sub_axes=ABSTRACTION_SUB_AXES,
    )


def _assessment_weight(
    *,
    dimension: str,
    score: float,
    findings: list[dict],
    dimension_notes: dict[str, dict],
) -> float:
    """Evidence-weighted assessment score weight with a neutral floor."""
    return batch_core_mod.assessment_weight(
        dimension=dimension,
        score=score,
        findings=findings,
        dimension_notes=dimension_notes,
    )


def _merge_batch_results(batch_results: list[object]) -> dict[str, object]:
    """Deterministically merge assessments/findings across batch outputs."""
    normalized_results: list[dict] = []
    for result in batch_results:
        if hasattr(result, "to_dict") and callable(result.to_dict):
            payload = result.to_dict()
            if isinstance(payload, dict):
                normalized_results.append(payload)
                continue
        if isinstance(result, dict):
            normalized_results.append(result)
    return batch_core_mod.merge_batch_results(
        normalized_results,
        abstraction_sub_axes=ABSTRACTION_SUB_AXES,
        abstraction_component_names=ABSTRACTION_COMPONENT_NAMES,
    )


def _build_batch_prompt(
    *,
    repo_root: Path,
    packet_path: Path,
    batch_index: int,
    batch: dict,
) -> str:
    """Render one subagent prompt for a holistic investigation batch."""
    return batch_core_mod.build_batch_prompt(
        repo_root=repo_root,
        packet_path=packet_path,
        batch_index=batch_index,
        batch=batch,
    )


def _codex_batch_command(
    *, prompt: str, repo_root: Path, output_file: Path
) -> list[str]:
    return runner_helpers_mod.codex_batch_command(
        prompt=prompt,
        repo_root=repo_root,
        output_file=output_file,
    )


def _run_codex_batch(
    *,
    prompt: str,
    repo_root: Path,
    output_file: Path,
    log_file: Path,
) -> int:
    """Execute one codex exec batch and return exit code."""
    return runner_helpers_mod.run_codex_batch(
        prompt=prompt,
        repo_root=repo_root,
        output_file=output_file,
        log_file=log_file,
        deps=runner_helpers_mod.CodexBatchRunnerDeps(
            timeout_seconds=CODEX_BATCH_TIMEOUT_SECONDS,
            subprocess_run=subprocess.run,
            timeout_error=subprocess.TimeoutExpired,
            safe_write_text_fn=safe_write_text,
        ),
    )


def _load_or_prepare_packet(
    args,
    *,
    state: dict,
    lang,
    config: dict,
    stamp: str,
) -> tuple[dict, Path]:
    """Load packet override or prepare a fresh packet snapshot."""
    packet_override = getattr(args, "packet", None)
    if packet_override:
        packet_path = Path(packet_override)
        if not packet_path.exists():
            print(
                colorize(f"  Error: packet not found: {packet_override}", "red"),
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            packet = json.loads(packet_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(colorize(f"  Error reading packet: {exc}", "red"), file=sys.stderr)
            sys.exit(1)
        return packet, packet_path

    path = Path(args.path)
    dims_str = getattr(args, "dimensions", None)
    dimensions = dims_str.split(",") if dims_str else None
    lang_run, found_files = _setup_lang(lang, path, config)
    lang_name = lang_run.name
    narrative = narrative_mod.compute_narrative(state, lang=lang_name, command="review")

    packet = review_mod.prepare_holistic_review(
        path,
        lang_run,
        state,
        dimensions=dimensions,
        files=found_files or None,
    )
    packet["narrative"] = narrative
    packet["next_command"] = "desloppify review --run-batches --runner codex --parallel"
    write_query(packet)
    packet_path, blind_path = _write_packet_snapshot(packet, stamp=stamp)
    print(colorize(f"  Immutable packet: {packet_path}", "dim"))
    print(colorize(f"  Blind packet: {blind_path}", "dim"))
    return packet, packet_path


def _selected_batch_indexes(args, *, batch_count: int) -> list[int]:
    return runner_helpers_mod.selected_batch_indexes(
        raw_selection=getattr(args, "only_batches", None),
        batch_count=batch_count,
        parse_fn=_parse_batch_selection,
        colorize_fn=colorize,
    )


def _run_followup_scan(*, lang_name: str, scan_path: str) -> int:
    return runner_helpers_mod.run_followup_scan(
        lang_name=lang_name,
        scan_path=scan_path,
        deps=runner_helpers_mod.FollowupScanDeps(
            project_root=PROJECT_ROOT,
            timeout_seconds=FOLLOWUP_SCAN_TIMEOUT_SECONDS,
            python_executable=sys.executable,
            subprocess_run=subprocess.run,
            timeout_error=subprocess.TimeoutExpired,
            colorize_fn=colorize,
        ),
    )


def _do_run_batches(args, state, lang, sp, config: dict | None = None) -> None:
    """Run holistic investigation batches with a local subagent runner."""

    def _prepare_run_artifacts(*, stamp, selected_indexes, batches, packet_path, run_root, repo_root):
        return runner_helpers_mod.prepare_run_artifacts(
            stamp=stamp,
            selected_indexes=selected_indexes,
            batches=batches,
            packet_path=packet_path,
            run_root=run_root,
            repo_root=repo_root,
            build_prompt_fn=_build_batch_prompt,
            safe_write_text_fn=safe_write_text,
            colorize_fn=colorize,
        )

    def _collect_batch_results(*, selected_indexes, failures, output_files, allowed_dims):
        return runner_helpers_mod.collect_batch_results(
            selected_indexes=selected_indexes,
            failures=failures,
            output_files=output_files,
            allowed_dims=allowed_dims,
            extract_payload_fn=_extract_json_payload,
            normalize_result_fn=_normalize_batch_result,
        )

    return review_batches_mod.do_run_batches(
        args,
        state,
        lang,
        sp,
        config=config,
        run_stamp_fn=_run_stamp,
        load_or_prepare_packet_fn=_load_or_prepare_packet,
        selected_batch_indexes_fn=_selected_batch_indexes,
        prepare_run_artifacts_fn=_prepare_run_artifacts,
        run_codex_batch_fn=_run_codex_batch,
        execute_batches_fn=runner_helpers_mod.execute_batches,
        collect_batch_results_fn=_collect_batch_results,
        print_failures_and_exit_fn=runner_helpers_mod.print_failures_and_exit,
        merge_batch_results_fn=_merge_batch_results,
        do_import_fn=_do_import,
        run_followup_scan_fn=_run_followup_scan,
        safe_write_text_fn=safe_write_text,
        colorize_fn=colorize,
        project_root=PROJECT_ROOT,
        subagent_runs_dir=SUBAGENT_RUNS_DIR,
    )


def _do_import(
    import_file,
    state,
    lang,
    sp,
    holistic=True,
    config: dict | None = None,
    *,
    assessment_override: bool = False,
    assessment_note: str | None = None,
):
    """Import mode: ingest agent-produced findings."""
    _ = (assessment_override, assessment_note)
    return review_import_mod.do_import(
        import_file,
        state,
        lang,
        sp,
        holistic=bool(holistic),
        config=config,
        load_import_findings_data_fn=_load_import_findings_data,
        import_holistic_findings_fn=review_mod.import_holistic_findings,
        save_state_fn=state_mod.save_state,
        compute_narrative_fn=narrative_mod.compute_narrative,
        print_skipped_validation_details_fn=_print_skipped_validation_details,
        print_assessments_summary_fn=_print_assessments_summary,
        print_open_review_summary_fn=_print_open_review_summary,
        print_review_import_scores_and_integrity_fn=_print_review_import_scores_and_integrity,
        write_query_fn=write_query,
        colorize_fn=colorize,
        log_fn=log,
    )


def _load_import_findings_data(import_file: str) -> dict:
    """Load and normalize review import payload to object format."""
    return import_helpers_mod.load_import_findings_data(
        import_file,
        colorize_fn=colorize,
    )


def _print_skipped_validation_details(diff: dict) -> None:
    """Print validation warnings for skipped imported findings."""
    import_helpers_mod.print_skipped_validation_details(diff, colorize_fn=colorize)


def _print_assessments_summary(state: dict) -> None:
    """Print holistic subjective assessment summary when present."""
    import_helpers_mod.print_assessments_summary(state, colorize_fn=colorize)


def _print_open_review_summary(state: dict) -> str:
    """Print current open review finding count and return the next suggested command."""
    return import_helpers_mod.print_open_review_summary(state, colorize_fn=colorize)


def _print_review_import_scores_and_integrity(state: dict, config: dict) -> list[dict]:
    """Print score snapshot plus subjective integrity warnings."""
    return import_helpers_mod.print_review_import_scores_and_integrity(
        state,
        config,
        state_mod=state_mod,
        target_strict_score_from_config_fn=target_strict_score_from_config,
        subjective_at_target_fn=_subjective_at_target_dimensions,
        subjective_rerun_command_fn=reporting_dimensions_mod.subjective_rerun_command,
        colorize_fn=colorize,
    )


def _setup_lang(lang, path: Path, config: dict):
    """Build LangRun with zone map + dep graph and return (run, files)."""
    return review_runtime_mod.setup_lang(
        lang,
        path,
        config,
        make_lang_run_fn=lang_runtime_mod.make_lang_run,
        file_zone_map_cls=FileZoneMap,
        rel_fn=rel,
        log_fn=log,
    )
