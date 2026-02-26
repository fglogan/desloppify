"""Runner orchestration helpers shared by review batch workflows."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import threading
from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_BLIND_PACKET_DROP_KEYS = {
    "narrative",
    "next_command",
    "score_snapshot",
    "strict_target",
    "strict_target_progress",
    "subjective_at_target",
}

_BLIND_CONFIG_SCORE_HINT_KEYS = {
    "target_strict_score",
    "strict_target_score",
    "target_score",
    "strict_score",
    "objective_score",
    "overall_score",
    "verified_strict_score",
}

_TRANSIENT_RUNNER_PHRASES = (
    "stream disconnected before completion",
    "error sending request for url",
    "connection reset by peer",
    "connection reset",
    "connection aborted",
    "temporarily unavailable",
    "network is unreachable",
    "connection refused",
    "timed out while",
    "no last agent message; wrote empty content",
)
_CODEX_BACKEND_PATH_HINT = "/backend-api/codex/responses"
_CODEX_BACKEND_HOST_HINT = "chatgpt.com"


@dataclass(frozen=True)
class CodexBatchRunnerDeps:
    timeout_seconds: int
    subprocess_run: object
    timeout_error: type[BaseException]
    safe_write_text_fn: object
    use_popen_runner: bool = False
    subprocess_popen: object | None = None
    live_log_interval_seconds: float = 5.0
    stall_after_output_seconds: int = 90
    max_retries: int = 0
    retry_backoff_seconds: float = 0.0
    sleep_fn: object = time.sleep


@dataclass(frozen=True)
class FollowupScanDeps:
    project_root: Path
    timeout_seconds: int
    python_executable: str
    subprocess_run: object
    timeout_error: type[BaseException]
    colorize_fn: object


@dataclass(frozen=True)
class BatchResult:
    """Typed normalized batch payload passed to merge/import stages."""

    batch_index: int
    assessments: dict[str, float]
    dimension_notes: dict[str, dict]
    findings: list[dict]
    quality: dict[str, float]

    def to_dict(self) -> dict[str, object]:
        return {
            "batch_index": self.batch_index,
            "assessments": self.assessments,
            "dimension_notes": self.dimension_notes,
            "findings": self.findings,
            "quality": self.quality,
        }


@dataclass
class _RunnerState:
    """Mutable state shared between threads during a batch run."""

    stdout_chunks: list[str] = field(default_factory=list)
    stderr_chunks: list[str] = field(default_factory=list)
    runner_note: str = ""
    last_stream_activity: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)
    stop_event: threading.Event = field(default_factory=threading.Event)


@dataclass(frozen=True)
class _AttemptContext:
    """Immutable per-attempt context bundling values that closures captured."""

    header: str
    started_at_iso: str
    started_monotonic: float
    output_file: Path
    log_file: Path
    log_sections: list[str]
    safe_write_text_fn: object


@dataclass
class _ExecutionResult:
    """Unified return from both execution paths."""

    code: int
    stdout_text: str
    stderr_text: str
    timed_out: bool = False
    recovered_from_stall: bool = False
    early_return: int | None = None


def run_stamp() -> str:
    """Stable UTC run stamp for artifact paths."""
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def codex_batch_command(*, prompt: str, repo_root: Path, output_file: Path) -> list[str]:
    """Build one codex exec command line for a batch prompt."""
    effort = os.environ.get("DESLOPPIFY_CODEX_REASONING_EFFORT", "low").strip().lower()
    if effort not in {"low", "medium", "high", "xhigh"}:
        effort = "low"
    return [
        "codex",
        "exec",
        "--ephemeral",
        "-C",
        str(repo_root),
        "-s",
        "workspace-write",
        "-c",
        'approval_policy="never"',
        "-c",
        f'model_reasoning_effort="{effort}"',
        "-o",
        str(output_file),
        prompt,
    ]


def _output_file_status_text(output_file: Path) -> str:
    """Describe output file state for live log snapshots."""
    if not output_file.exists():
        return f"{output_file} (missing)"
    try:
        stat = output_file.stat()
    except OSError as exc:
        return f"{output_file} (exists; stat failed: {exc})"
    modified_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(
        timespec="seconds"
    )
    return (
        f"{output_file} (exists; bytes={stat.st_size}; "
        f"modified={modified_at})"
    )


def _output_file_has_json_payload(output_file: Path) -> bool:
    """Return True when the output file contains a valid JSON object."""
    if not output_file.exists():
        return False
    try:
        payload = json.loads(output_file.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict)


def _terminate_process(process: subprocess.Popen[str]) -> None:
    """Terminate (then kill) a subprocess that may still be running."""
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=3)
        return
    except Exception:
        pass
    try:
        process.kill()
        process.wait(timeout=3)
    except Exception:
        return


def _drain_stream(stream, sink: list[str], state: _RunnerState) -> None:
    """Read lines from *stream* into *sink*, updating activity timestamp."""
    if stream is None:
        return
    try:
        for chunk in iter(stream.readline, ""):
            if not chunk:
                break
            with state.lock:
                sink.append(chunk)
                state.last_stream_activity = time.monotonic()
    except Exception as exc:  # pragma: no cover - defensive boundary
        with state.lock:
            sink.append(f"\n[stream read error: {exc}]\n")
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _write_live_snapshot(state: _RunnerState, ctx: _AttemptContext) -> None:
    """Write a point-in-time log snapshot while the runner is active."""
    elapsed_seconds = int(max(0.0, time.monotonic() - ctx.started_monotonic))
    with state.lock:
        stdout_preview = "".join(state.stdout_chunks)
        stderr_preview = "".join(state.stderr_chunks)
        note = state.runner_note
    note_block = f"\nRUNNER NOTE: {note}" if note else ""
    ctx.safe_write_text_fn(
        ctx.log_file,
        "\n\n".join(
            ctx.log_sections
            + [
                (
                    f"{ctx.header}\n\n"
                    "STATUS: running\n"
                    f"STARTED AT: {ctx.started_at_iso}\n"
                    f"ELAPSED: {elapsed_seconds}s\n"
                    f"OUTPUT FILE: {_output_file_status_text(ctx.output_file)}"
                    f"{note_block}\n\n"
                    f"STDOUT (live):\n{stdout_preview}\n\n"
                    f"STDERR (live):\n{stderr_preview}\n"
                )
            ]
        ),
    )


def _start_live_writer(
    state: _RunnerState, ctx: _AttemptContext, interval: float,
) -> threading.Thread:
    """Spawn a daemon thread that periodically writes live log snapshots."""
    def _loop() -> None:
        while not state.stop_event.wait(interval):
            _write_live_snapshot(state, ctx)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    return thread


def _check_stall(
    output_file: Path,
    prev_sig: tuple[int, int] | None,
    prev_stable: float | None,
    now: float,
    last_activity: float,
    threshold: int,
) -> tuple[bool, tuple[int, int] | None, float | None]:
    """Check for output file stall. Returns (stalled, new_sig, new_stable_since)."""
    try:
        stat = output_file.stat()
        current_signature: tuple[int, int] | None = (int(stat.st_size), int(stat.st_mtime))
    except OSError:
        current_signature = None
    if current_signature is None:
        return False, None, None
    if current_signature != prev_sig:
        return False, current_signature, now
    if prev_stable is None:
        return False, prev_sig, prev_stable
    output_age = now - prev_stable
    stream_idle = now - last_activity
    if output_age >= threshold and stream_idle >= threshold:
        return True, prev_sig, prev_stable
    return False, prev_sig, prev_stable


def _run_via_popen(
    cmd: list[str],
    deps: CodexBatchRunnerDeps,
    state: _RunnerState,
    ctx: _AttemptContext,
    interval: float,
    stall_seconds: int,
) -> _ExecutionResult:
    """Execute batch via Popen with live streaming and stall recovery."""
    writer_thread = _start_live_writer(state, ctx, interval)
    try:
        process = deps.subprocess_popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        state.stop_event.set()
        writer_thread.join(timeout=2)
        ctx.log_sections.append(f"{ctx.header}\n\nRUNNER ERROR:\n{exc}\n")
        ctx.safe_write_text_fn(ctx.log_file, "\n\n".join(ctx.log_sections))
        return _ExecutionResult(code=127, stdout_text="", stderr_text="", early_return=127)
    except Exception as exc:  # pragma: no cover - defensive boundary
        state.stop_event.set()
        writer_thread.join(timeout=2)
        ctx.log_sections.append(f"{ctx.header}\n\nUNEXPECTED RUNNER ERROR:\n{exc}\n")
        ctx.safe_write_text_fn(ctx.log_file, "\n\n".join(ctx.log_sections))
        return _ExecutionResult(code=1, stdout_text="", stderr_text="", early_return=1)

    stdout_thread = threading.Thread(
        target=_drain_stream,
        args=(process.stdout, state.stdout_chunks, state),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_drain_stream,
        args=(process.stderr, state.stderr_chunks, state),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    timed_out = False
    recovered_from_stall = False
    output_signature: tuple[int, int] | None = None
    output_stable_since: float | None = None

    while process.poll() is None:
        now_monotonic = time.monotonic()
        elapsed = int(max(0.0, now_monotonic - ctx.started_monotonic))
        if elapsed >= deps.timeout_seconds:
            with state.lock:
                state.runner_note = f"timeout after {deps.timeout_seconds}s"
            timed_out = True
            _terminate_process(process)
            break
        if stall_seconds > 0:
            with state.lock:
                last_activity = state.last_stream_activity
            stalled, output_signature, output_stable_since = _check_stall(
                ctx.output_file,
                output_signature,
                output_stable_since,
                now_monotonic,
                last_activity,
                stall_seconds,
            )
            if stalled:
                with state.lock:
                    state.runner_note = (
                        f"stall recovery triggered after {stall_seconds}s "
                        "with stable output file"
                    )
                recovered_from_stall = _output_file_has_json_payload(ctx.output_file)
                _terminate_process(process)
                break
        deps.sleep_fn(min(interval, 1.0))

    if process.poll() is None:
        _terminate_process(process)
    stdout_thread.join(timeout=2)
    stderr_thread.join(timeout=2)
    state.stop_event.set()
    writer_thread.join(timeout=2)
    _write_live_snapshot(state, ctx)

    return _ExecutionResult(
        code=int(process.returncode or 0),
        stdout_text="".join(state.stdout_chunks),
        stderr_text="".join(state.stderr_chunks),
        timed_out=timed_out,
        recovered_from_stall=recovered_from_stall,
    )


def _run_via_subprocess(
    cmd: list[str],
    deps: CodexBatchRunnerDeps,
    state: _RunnerState,
    ctx: _AttemptContext,
    interval: float,
) -> _ExecutionResult:
    """Execute batch via subprocess.run (compatibility path for tests)."""
    writer_thread = _start_live_writer(state, ctx, interval)
    try:
        result = deps.subprocess_run(
            cmd,
            capture_output=True,
            text=True,
            timeout=deps.timeout_seconds,
        )
    except deps.timeout_error as exc:
        state.stop_event.set()
        writer_thread.join(timeout=2)
        ctx.log_sections.append(
            f"{ctx.header}\n\nTIMEOUT after {deps.timeout_seconds}s\n{exc}\n"
        )
        ctx.safe_write_text_fn(ctx.log_file, "\n\n".join(ctx.log_sections))
        return _ExecutionResult(code=124, stdout_text="", stderr_text="", early_return=124)
    except OSError as exc:
        state.stop_event.set()
        writer_thread.join(timeout=2)
        ctx.log_sections.append(f"{ctx.header}\n\nRUNNER ERROR:\n{exc}\n")
        ctx.safe_write_text_fn(ctx.log_file, "\n\n".join(ctx.log_sections))
        return _ExecutionResult(code=127, stdout_text="", stderr_text="", early_return=127)
    except (RuntimeError, ValueError) as exc:  # pragma: no cover - defensive boundary
        state.stop_event.set()
        writer_thread.join(timeout=2)
        ctx.log_sections.append(f"{ctx.header}\n\nUNEXPECTED RUNNER ERROR:\n{exc}\n")
        ctx.safe_write_text_fn(ctx.log_file, "\n\n".join(ctx.log_sections))
        return _ExecutionResult(code=1, stdout_text="", stderr_text="", early_return=1)
    finally:
        state.stop_event.set()
        writer_thread.join(timeout=2)

    return _ExecutionResult(
        code=int(result.returncode),
        stdout_text=result.stdout or "",
        stderr_text=result.stderr or "",
    )


def run_codex_batch(
    *,
    prompt: str,
    repo_root: Path,
    output_file: Path,
    log_file: Path,
    deps: CodexBatchRunnerDeps,
) -> int:
    """Execute one codex batch and return a stable CLI-style status code."""
    cmd = codex_batch_command(prompt=prompt, repo_root=repo_root, output_file=output_file)
    retries_raw = deps.max_retries if isinstance(deps.max_retries, int) else 0
    max_retries = max(0, retries_raw)
    max_attempts = max_retries + 1
    backoff_raw = (
        float(deps.retry_backoff_seconds)
        if isinstance(deps.retry_backoff_seconds, int | float)
        else 0.0
    )
    retry_backoff_seconds = max(0.0, backoff_raw)
    live_log_interval = (
        float(deps.live_log_interval_seconds)
        if isinstance(deps.live_log_interval_seconds, int | float)
        and float(deps.live_log_interval_seconds) > 0
        else 5.0
    )
    stall_seconds = (
        int(deps.stall_after_output_seconds)
        if isinstance(deps.stall_after_output_seconds, int | float)
        and int(deps.stall_after_output_seconds) > 0
        else 0
    )
    log_sections: list[str] = []
    use_popen = bool(deps.use_popen_runner) and callable(
        getattr(deps, "subprocess_popen", None)
    )

    for attempt in range(1, max_attempts + 1):
        header = f"ATTEMPT {attempt}/{max_attempts}\n$ {' '.join(cmd)}"
        started_monotonic = time.monotonic()
        state = _RunnerState(last_stream_activity=started_monotonic)
        ctx = _AttemptContext(
            header=header,
            started_at_iso=datetime.now(UTC).isoformat(timespec="seconds"),
            started_monotonic=started_monotonic,
            output_file=output_file,
            log_file=log_file,
            log_sections=log_sections,
            safe_write_text_fn=deps.safe_write_text_fn,
        )
        _write_live_snapshot(state, ctx)

        if use_popen:
            result = _run_via_popen(cmd, deps, state, ctx, live_log_interval, stall_seconds)
        else:
            result = _run_via_subprocess(cmd, deps, state, ctx, live_log_interval)

        if result.early_return is not None:
            return result.early_return

        if result.timed_out:
            log_sections.append(
                f"{header}\n\nTIMEOUT after {deps.timeout_seconds}s\n\n"
                f"STDOUT:\n{result.stdout_text}\n\nSTDERR:\n{result.stderr_text}\n"
            )
            if _output_file_has_json_payload(output_file):
                log_sections.append(
                    "Recovered timed-out batch from JSON output file; "
                    "continuing as success."
                )
                deps.safe_write_text_fn(log_file, "\n\n".join(log_sections))
                return 0
            deps.safe_write_text_fn(log_file, "\n\n".join(log_sections))
            return 124

        if result.recovered_from_stall:
            log_sections.append(
                f"{header}\n\nSTALL RECOVERY after {stall_seconds}s "
                "of stable output and no stream activity.\n\n"
                f"STDOUT:\n{result.stdout_text}\n\nSTDERR:\n{result.stderr_text}\n"
            )
            if _output_file_has_json_payload(output_file):
                log_sections.append(
                    "Recovered stalled batch from JSON output file; "
                    "continuing as success."
                )
                deps.safe_write_text_fn(log_file, "\n\n".join(log_sections))
                return 0
            deps.safe_write_text_fn(log_file, "\n\n".join(log_sections))
            return 124

        log_sections.append(
            f"{header}\n\nSTDOUT:\n{result.stdout_text}\n\nSTDERR:\n{result.stderr_text}\n"
        )

        if result.code == 0:
            deps.safe_write_text_fn(log_file, "\n\n".join(log_sections))
            return 0

        combined = f"{result.stdout_text}\n{result.stderr_text}".lower()
        is_transient = any(needle in combined for needle in _TRANSIENT_RUNNER_PHRASES)
        if not is_transient or attempt >= max_attempts:
            deps.safe_write_text_fn(log_file, "\n\n".join(log_sections))
            return result.code

        delay_seconds = retry_backoff_seconds * (2 ** (attempt - 1))
        log_sections.append(
            "Transient runner failure detected; "
            f"retrying in {delay_seconds:.1f}s (attempt {attempt + 1}/{max_attempts})."
        )
        try:
            if delay_seconds > 0:
                deps.sleep_fn(delay_seconds)
        except Exception:  # pragma: no cover - defensive boundary
            # Retry should proceed even if delay hook fails.
            pass

    deps.safe_write_text_fn(log_file, "\n\n".join(log_sections))
    return 1


def run_followup_scan(
    *,
    lang_name: str,
    scan_path: str,
    deps: FollowupScanDeps,
) -> int:
    """Run a follow-up scan and return a non-zero status when it fails."""
    scan_cmd = [
        deps.python_executable,
        "-m",
        "desloppify",
        "--lang",
        lang_name,
        "scan",
        "--path",
        scan_path,
    ]
    print(deps.colorize_fn("\n  Running follow-up scan...", "bold"))
    try:
        result = deps.subprocess_run(
            scan_cmd,
            cwd=str(deps.project_root),
            timeout=deps.timeout_seconds,
        )
    except deps.timeout_error:
        print(
            deps.colorize_fn(
                f"  Follow-up scan timed out after {deps.timeout_seconds}s.",
                "yellow",
            ),
            file=sys.stderr,
        )
        return 124
    except OSError as exc:
        print(
            deps.colorize_fn(f"  Follow-up scan failed: {exc}", "red"),
            file=sys.stderr,
        )
        return 1
    return int(getattr(result, "returncode", 0) or 0)


def write_packet_snapshot(
    packet: dict,
    *,
    stamp: str,
    review_packet_dir: Path,
    blind_path: Path,
    safe_write_text_fn,
) -> tuple[Path, Path]:
    """Persist immutable and blind packet snapshots for runner workflows."""
    review_packet_dir.mkdir(parents=True, exist_ok=True)
    packet_path = review_packet_dir / f"holistic_packet_{stamp}.json"
    safe_write_text_fn(packet_path, json.dumps(packet, indent=2) + "\n")
    blind_packet = _build_blind_packet(packet)
    safe_write_text_fn(blind_path, json.dumps(blind_packet, indent=2) + "\n")
    return packet_path, blind_path


def _build_blind_packet(packet: dict) -> dict:
    """Return a blind-review packet with score anchoring metadata removed."""
    blind = deepcopy(packet)
    for key in _BLIND_PACKET_DROP_KEYS:
        blind.pop(key, None)

    config = blind.get("config")
    if isinstance(config, dict):
        sanitized = _sanitize_blind_config(config)
        if sanitized:
            blind["config"] = sanitized
        else:
            blind.pop("config", None)
    return blind


def build_blind_packet(packet: dict) -> dict:
    """Public wrapper for blind packet sanitization."""
    return _build_blind_packet(packet)


def _sanitize_blind_config(config: dict[str, Any]) -> dict[str, Any]:
    """Drop score/target hints from config while preserving unrelated options."""
    sanitized: dict[str, Any] = {}
    for key, value in config.items():
        lowered = key.strip().lower()
        if not lowered:
            continue
        if lowered in _BLIND_CONFIG_SCORE_HINT_KEYS:
            continue
        if "target" in lowered:
            continue
        if lowered.endswith("_score"):
            continue
        sanitized[key] = value
    return sanitized


def sha256_file(path: Path) -> str | None:
    """Compute sha256 hex digest for path contents (or None on read failure)."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return sha256(data).hexdigest()


def build_batch_import_provenance(
    *,
    runner: str,
    blind_packet_path: Path,
    run_stamp: str,
    batch_indexes: list[int],
) -> dict[str, Any]:
    """Build provenance payload used to trust assessment-bearing imports."""
    packet_hash = sha256_file(blind_packet_path)
    batch_indexes_1 = sorted({int(index) + 1 for index in batch_indexes})
    return {
        "kind": "blind_review_batch_import",
        "blind": True,
        "runner": runner,
        "run_stamp": run_stamp,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "batch_count": len(batch_indexes_1),
        "batch_indexes": batch_indexes_1,
        "packet_path": str(blind_packet_path),
        "packet_sha256": packet_hash,
    }


def selected_batch_indexes(
    *,
    raw_selection: str | None,
    batch_count: int,
    parse_fn,
    colorize_fn,
) -> list[int]:
    """Validate selected batch indexes or exit with a CLI error."""
    try:
        selected = parse_fn(raw_selection, batch_count)
    except ValueError as exc:
        print(colorize_fn(f"  Error: {exc}", "red"), file=sys.stderr)
        sys.exit(2)
    if selected:
        return selected
    print(colorize_fn("  Error: no batches selected", "red"), file=sys.stderr)
    sys.exit(2)


def prepare_run_artifacts(
    *,
    stamp: str,
    selected_indexes: list[int],
    batches: list[dict],
    packet_path: Path,
    run_root: Path,
    repo_root: Path,
    build_prompt_fn,
    safe_write_text_fn,
    colorize_fn,
) -> tuple[Path, Path, dict[int, Path], dict[int, Path], dict[int, Path]]:
    """Build prompt/output/log paths and persist prompts for selected batches."""
    run_dir = run_root / stamp
    prompts_dir = run_dir / "prompts"
    results_dir = run_dir / "results"
    logs_dir = run_dir / "logs"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    selected_1_based = [idx + 1 for idx in selected_indexes]
    print(colorize_fn(f"\n  Running holistic batches: {selected_1_based}", "bold"))
    print(colorize_fn(f"  Run artifacts: {run_dir}", "dim"))

    prompt_files: dict[int, Path] = {}
    output_files: dict[int, Path] = {}
    log_files: dict[int, Path] = {}
    for idx in selected_indexes:
        batch = batches[idx] if isinstance(batches[idx], dict) else {}
        prompt_text = build_prompt_fn(
            repo_root=repo_root,
            packet_path=packet_path,
            batch_index=idx,
            batch=batch,
        )
        prompt_file = prompts_dir / f"batch-{idx + 1}.md"
        output_file = results_dir / f"batch-{idx + 1}.raw.txt"
        log_file = logs_dir / f"batch-{idx + 1}.log"
        safe_write_text_fn(prompt_file, prompt_text)
        prompt_files[idx] = prompt_file
        output_files[idx] = output_file
        log_files[idx] = log_file
    return run_dir, logs_dir, prompt_files, output_files, log_files


def execute_batches(
    *,
    selected_indexes: list[int],
    prompt_files: dict[int, Path],
    output_files: dict[int, Path],
    log_files: dict[int, Path],
    run_parallel: bool,
    run_batch_fn,
    safe_write_text_fn,
    progress_fn=None,
    max_parallel_workers: int | None = None,
    heartbeat_seconds: float | None = 15.0,
    clock_fn=time.monotonic,
) -> list[int]:
    """Execute batch prompts and return failed index list."""

    def _emit_progress(
        batch_index: int,
        event: str,
        code: int | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        if not callable(progress_fn):
            return
        payload = details or {}
        try:
            progress_fn(batch_index, event, code, **payload)
        except TypeError:
            try:
                progress_fn(batch_index, event, code)
            except Exception:
                return
        except Exception:
            return

    failures: list[int] = []
    if run_parallel:
        requested_workers = (
            int(max_parallel_workers)
            if isinstance(max_parallel_workers, int) and max_parallel_workers > 0
            else 8
        )
        max_workers = max(1, min(len(selected_indexes), requested_workers))
        heartbeat = (
            float(heartbeat_seconds)
            if isinstance(heartbeat_seconds, int | float) and heartbeat_seconds > 0
            else None
        )
        started_at: dict[int, float] = {}
        started_at_lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for idx in selected_indexes:
                _emit_progress(
                    idx,
                    "queued",
                    None,
                    details={"max_workers": max_workers},
                )

                def _run_one(batch_index: int) -> int:
                    with started_at_lock:
                        started_at[batch_index] = float(clock_fn())
                    _emit_progress(
                        batch_index,
                        "start",
                        None,
                        details={"max_workers": max_workers},
                    )
                    return run_batch_fn(
                        prompt=prompt_files[batch_index].read_text(),
                        output_file=output_files[batch_index],
                        log_file=log_files[batch_index],
                    )

                future = executor.submit(_run_one, idx)
                futures[future] = idx

            pending = set(futures.keys())

            def _handle_completed_future(future) -> None:
                idx = futures[future]
                with started_at_lock:
                    started_at_value = started_at.get(idx, float(clock_fn()))
                try:
                    code = future.result()
                except Exception as exc:  # future.result() can raise any exception from the batch runner
                    safe_write_text_fn(log_files[idx], f"Runner exception:\n{exc}\n")
                    failures.append(idx)
                    _emit_progress(
                        idx,
                        "done",
                        1,
                        details={"elapsed_seconds": int(max(0.0, clock_fn() - started_at_value))},
                    )
                    return
                if code != 0:
                    failures.append(idx)
                _emit_progress(
                    idx,
                    "done",
                    code,
                    details={"elapsed_seconds": int(max(0.0, clock_fn() - started_at_value))},
                )

            if heartbeat is None:
                for future in as_completed(pending):
                    pending.discard(future)
                    _handle_completed_future(future)
                return failures

            while pending:
                try:
                    future = next(as_completed(pending, timeout=heartbeat))
                except FuturesTimeoutError:
                    with started_at_lock:
                        active_indexes = sorted(
                            futures[fut] for fut in pending if futures[fut] in started_at
                        )
                    active_index_set = set(active_indexes)
                    queued_indexes = sorted(
                        futures[fut] for fut in pending if futures[fut] not in active_index_set
                    )
                    elapsed_seconds = {
                        idx: int(
                            max(
                                0.0,
                                clock_fn() - started_at.get(idx, clock_fn()),
                            )
                        )
                        for idx in active_indexes
                    }
                    _emit_progress(
                        -1,
                        "heartbeat",
                        None,
                        details={
                            "active_batches": active_indexes,
                            "queued_batches": queued_indexes,
                            "elapsed_seconds": elapsed_seconds,
                            "active_count": len(active_indexes),
                            "queued_count": len(queued_indexes),
                            "total_count": len(selected_indexes),
                        },
                    )
                    continue
                pending.discard(future)
                _handle_completed_future(future)
        return failures

    for idx in selected_indexes:
        started_at = float(clock_fn())
        _emit_progress(idx, "start", None, details={"max_workers": 1})
        code = run_batch_fn(
            prompt=prompt_files[idx].read_text(),
            output_file=output_files[idx],
            log_file=log_files[idx],
        )
        if code != 0:
            failures.append(idx)
        _emit_progress(
            idx,
            "done",
            code,
            details={"elapsed_seconds": int(max(0.0, clock_fn() - started_at))},
        )
    return failures


def _extract_payload_from_log(
    batch_index: int, raw_path: Path, extract_fn,
) -> dict[str, object] | None:
    """Try to recover a batch payload from the runner log file."""
    log_path = raw_path.parent.parent / "logs" / f"batch-{batch_index + 1}.log"
    if not log_path.exists():
        return None
    try:
        log_text = log_path.read_text()
    except OSError:
        return None

    # Prefer the final STDOUT section for the attempt; if that fails, scan the full log.
    stdout_marker = "\nSTDOUT:\n"
    stderr_marker = "\n\nSTDERR:\n"
    stdout_start = log_text.rfind(stdout_marker)
    if stdout_start == -1 and log_text.startswith("STDOUT:\n"):
        stdout_start = 0
        stdout_offset = len("STDOUT:\n")
    elif stdout_start >= 0:
        stdout_offset = len(stdout_marker)
    else:
        stdout_offset = 0
    if stdout_start >= 0:
        start_idx = stdout_start + stdout_offset
        stdout_end = log_text.find(stderr_marker, start_idx)
        stdout_text = (
            log_text[start_idx:] if stdout_end == -1 else log_text[start_idx:stdout_end]
        )
        payload = extract_fn(stdout_text)
        if payload is not None:
            return payload
        # If the batch log has a concrete STDOUT section but it contains no parseable
        # payload, do not fallback to parsing the whole log. Full logs include the
        # prompt template (often with JSON examples), which can generate misleading
        # decode errors and hide the true runner failure in STDERR.
        return None

    return extract_fn(log_text)


def collect_batch_results(
    *,
    selected_indexes: list[int],
    failures: list[int],
    output_files: dict[int, Path],
    allowed_dims: set[str],
    extract_payload_fn,
    normalize_result_fn,
) -> tuple[list[BatchResult], list[int]]:
    """Parse and normalize batch outputs, preserving prior failures."""
    batch_results: list[BatchResult] = []
    failure_set = set(failures)
    for idx in selected_indexes:
        had_execution_failure = idx in failure_set
        raw_path = output_files[idx]
        payload = None
        parsed_from_log = False
        if raw_path.exists():
            try:
                payload = extract_payload_fn(raw_path.read_text())
            except OSError:
                payload = None
        if payload is None:
            payload = _extract_payload_from_log(idx, raw_path, extract_payload_fn)
            parsed_from_log = payload is not None
        if payload is None:
            failure_set.add(idx)
            continue
        if parsed_from_log:
            try:
                raw_path.write_text(json.dumps(payload, indent=2) + "\n")
            except OSError:
                pass
        try:
            assessments, findings, dimension_notes, quality = normalize_result_fn(
                payload,
                allowed_dims,
            )
        except ValueError:
            failure_set.add(idx)
            continue
        if had_execution_failure:
            failure_set.discard(idx)
        batch_results.append(
            BatchResult(
                batch_index=idx + 1,
                assessments=assessments,
                dimension_notes=dimension_notes,
                findings=findings,
                quality=quality,
            )
        )
    return batch_results, sorted(failure_set)


def _classify_runner_failure(log_text: str) -> str:
    """Classify batch failure type from log contents."""
    text = log_text.lower()
    if "timeout after" in text:
        return "timeout"
    if any(phrase in text for phrase in _TRANSIENT_RUNNER_PHRASES):
        return "stream_disconnect"
    if (
        "codex not found" in text
        or ("no such file or directory" in text and "$ codex " in text)
        or ("errno 2" in text and "codex" in text)
    ):
        return "runner_missing"
    if any(
        phrase in text
        for phrase in (
            "not authenticated",
            "authentication failed",
            "unauthorized",
            "forbidden",
            "login required",
            "please login",
            "access token",
        )
    ):
        return "runner_auth"
    if "runner exception" in text:
        return "runner_exception"
    return "unknown"


def _has_codex_backend_connectivity_issue(log_text: str) -> bool:
    """Return True when logs indicate Codex backend URL is unreachable."""
    text = log_text.lower()
    if "error sending request for url" not in text:
        return False
    return (
        _CODEX_BACKEND_PATH_HINT in text
        or _CODEX_BACKEND_HOST_HINT in text
        or "nodename nor servname provided" in text
        or "name or service not known" in text
        or "temporary failure in name resolution" in text
    )


def _summarize_failure_categories(*, failures: list[int], logs_dir: Path) -> dict[str, int]:
    """Return counts by failure category for failed batches."""
    categories: dict[str, int] = {}
    for idx in sorted(set(failures)):
        log_file = logs_dir / f"batch-{idx + 1}.log"
        if not log_file.exists():
            category = "missing_log"
        else:
            try:
                category = _classify_runner_failure(log_file.read_text())
            except OSError:
                category = "log_read_error"
        categories[category] = categories.get(category, 0) + 1
    return categories


def _runner_failure_hints(*, failures: list[int], logs_dir: Path) -> list[str]:
    """Infer common runner environment failures from batch logs."""
    hints: list[str] = []
    for idx in sorted(set(failures)):
        log_file = logs_dir / f"batch-{idx + 1}.log"
        try:
            raw = log_file.read_text()
        except OSError:
            continue
        text = raw.lower()
        if (
            "codex not found" in text
            or ("no such file or directory" in text and "$ codex " in text)
            or ("errno 2" in text and "codex" in text)
        ):
            hint = (
                "codex CLI not found on PATH. Install Codex CLI and verify `codex --version`."
            )
            if hint not in hints:
                hints.append(hint)
        if any(
            phrase in text
            for phrase in (
                "not authenticated",
                "authentication failed",
                "unauthorized",
                "forbidden",
                "login required",
                "please login",
                "access token",
            )
        ):
            hint = "codex runner appears unauthenticated. Run `codex login` and retry."
            if hint not in hints:
                hints.append(hint)
        if any(phrase in text for phrase in _TRANSIENT_RUNNER_PHRASES):
            hint = (
                "Transient Codex connectivity issue detected. Retry with "
                "`--batch-max-retries 2 --batch-retry-backoff-seconds 2` and, if needed, "
                "lower concurrency via `--max-parallel-batches 1`."
            )
            if hint not in hints:
                hints.append(hint)
        if _has_codex_backend_connectivity_issue(text):
            hint = (
                "Codex runner cannot reach chatgpt.com backend from this environment. "
                "Check outbound HTTPS/DNS/proxy access, or use cloud fallback: "
                "`desloppify review --external-start --external-runner claude`."
            )
            if hint not in hints:
                hints.append(hint)
        if "failed to load skill" in text and "missing yaml frontmatter" in text:
            hint = (
                "Codex loaded an invalid local skill file. Fix/remove malformed "
                "SKILL.md entries under `~/.codex/skills` to reduce runner noise."
            )
            if hint not in hints:
                hints.append(hint)
    return hints


def _print_failures_report(
    *,
    failures: list[int],
    packet_path: Path,
    logs_dir: Path,
    colorize_fn,
) -> None:
    """Render retry guidance for failed batches."""
    failed_1 = sorted({idx + 1 for idx in failures})
    failed_csv = ",".join(str(i) for i in failed_1)
    print(colorize_fn(f"\n  Failed batches: {failed_1}", "red"), file=sys.stderr)
    categories = _summarize_failure_categories(failures=failures, logs_dir=logs_dir)
    if categories:
        labels = {
            "timeout": "timeout",
            "stream_disconnect": "stream disconnect",
            "runner_missing": "runner missing",
            "runner_auth": "runner auth",
            "runner_exception": "runner exception",
            "missing_log": "missing log",
            "log_read_error": "log read error",
            "unknown": "unknown",
        }
        category_segments = [
            f"{labels.get(name, name)}={count}"
            for name, count in sorted(categories.items())
        ]
        print(
            colorize_fn(
                f"  Failure categories: {', '.join(category_segments)}",
                "yellow",
            ),
            file=sys.stderr,
        )
        if categories.get("timeout", 0) > 0:
            print(
                colorize_fn(
                    "  Timeout tuning: lower concurrency with `--max-parallel-batches 1..3` "
                    "or increase `--batch-timeout-seconds` for long-running reviews.",
                    "yellow",
                ),
                file=sys.stderr,
            )
        if categories.get("stream_disconnect", 0) > 0:
            print(
                colorize_fn(
                    "  Connectivity tuning: enable retries with `--batch-max-retries 2` "
                    "and `--batch-retry-backoff-seconds 2`, then retry failed batches.",
                    "yellow",
                ),
                file=sys.stderr,
            )
    print(colorize_fn("  Retry command:", "yellow"), file=sys.stderr)
    print(
        colorize_fn(
            f"    desloppify review --run-batches --packet {packet_path} --only-batches {failed_csv}",
            "yellow",
        ),
        file=sys.stderr,
    )
    for idx_1 in failed_1:
        log_file = logs_dir / f"batch-{idx_1}.log"
        print(colorize_fn(f"    log: {log_file}", "dim"), file=sys.stderr)
    hints = _runner_failure_hints(failures=failures, logs_dir=logs_dir)
    if hints:
        print(colorize_fn("  Environment hints:", "yellow"), file=sys.stderr)
        for hint in hints:
            print(colorize_fn(f"    {hint}", "dim"), file=sys.stderr)


def print_failures(
    *,
    failures: list[int],
    packet_path: Path,
    logs_dir: Path,
    colorize_fn,
) -> None:
    """Render retry guidance for failed batches without exiting."""
    _print_failures_report(
        failures=failures,
        packet_path=packet_path,
        logs_dir=logs_dir,
        colorize_fn=colorize_fn,
    )


def print_failures_and_exit(
    *,
    failures: list[int],
    packet_path: Path,
    logs_dir: Path,
    colorize_fn,
) -> None:
    """Render retry guidance for failed batches and exit non-zero."""
    _print_failures_report(
        failures=failures,
        packet_path=packet_path,
        logs_dir=logs_dir,
        colorize_fn=colorize_fn,
    )
    sys.exit(1)


__all__ = [
    "BatchResult",
    "CodexBatchRunnerDeps",
    "FollowupScanDeps",
    "build_batch_import_provenance",
    "build_blind_packet",
    "sha256_file",
    "codex_batch_command",
    "collect_batch_results",
    "execute_batches",
    "prepare_run_artifacts",
    "print_failures",
    "print_failures_and_exit",
    "run_codex_batch",
    "run_followup_scan",
    "run_stamp",
    "selected_batch_indexes",
    "write_packet_snapshot",
]
