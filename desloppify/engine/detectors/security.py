"""Cross-language security detector — hardcoded secrets, weak crypto, sensitive logging.

Contains generic checks shared by all language plugins. Additional language-
specific checks live under ``lang/<name>/detectors/security.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from desloppify.utils import rel
from desloppify.engine.policy.zones import FileZoneMap, Zone
from desloppify.engine.detectors.patterns.security import LOG_CALLS as _LOG_CALLS
from desloppify.engine.detectors.patterns.security import RANDOM_CALLS as _RANDOM_CALLS
from desloppify.engine.detectors.patterns.security import SECRET_FORMAT_PATTERNS as _SECRET_FORMAT_PATTERNS
from desloppify.engine.detectors.patterns.security import SECRET_NAME_RE as _SECRET_NAME_RE
from desloppify.engine.detectors.patterns.security import SECRET_NAMES as _SECRET_NAMES
from desloppify.engine.detectors.patterns.security import SECURITY_CONTEXT_WORDS as _SECURITY_CONTEXT_WORDS
from desloppify.engine.detectors.patterns.security import SENSITIVE_IN_LOG as _SENSITIVE_IN_LOG
from desloppify.engine.detectors.patterns.security import WEAK_CRYPTO_PATTERNS as _WEAK_CRYPTO_PATTERNS
from desloppify.engine.detectors.patterns.security import has_secret_format_match as _has_secret_format_match
from desloppify.engine.detectors.patterns.security import is_comment_line as _is_comment_line
from desloppify.engine.detectors.patterns.security import is_env_lookup as _is_env_lookup
from desloppify.engine.detectors.patterns.security import is_placeholder as _is_placeholder

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SecurityRule:
    """Metadata describing one detector finding shape."""

    check_id: str
    summary: str
    severity: str
    confidence: str
    remediation: str


def _scan_line_for_security_entries(
    *,
    filepath: str,
    line_num: int,
    line: str,
    is_test: bool,
) -> list[dict[str, Any]]:
    """Evaluate one source line against all generic security checks."""
    entries: list[dict[str, Any]] = []
    entries.extend(_secret_format_entries(filepath, line_num, line, is_test))
    entries.extend(_secret_name_entries(filepath, line_num, line, is_test))
    entries.extend(_insecure_random_entries(filepath, line_num, line))
    entries.extend(_weak_crypto_entries(filepath, line_num, line))
    entries.extend(_sensitive_log_entries(filepath, line_num, line))

    return entries


def _secret_format_entries(
    filepath: str, line_num: int, line: str, is_test: bool
) -> list[dict[str, Any]]:
    confidence = "medium" if is_test else "high"
    entries: list[dict[str, Any]] = []
    for label, pattern, severity, remediation in _SECRET_FORMAT_PATTERNS:
        if not pattern.search(line):
            continue
        entries.append(
            make_security_entry(
                filepath,
                line_num,
                line,
                SecurityRule(
                    check_id="hardcoded_secret_value",
                    summary=f"Hardcoded {label} detected",
                    severity=severity,
                    confidence=confidence,
                    remediation=remediation,
                ),
            )
        )
    return entries


def _secret_name_entries(
    filepath: str, line_num: int, line: str, is_test: bool
) -> list[dict[str, Any]]:
    confidence = "medium" if is_test else "high"
    entries: list[dict[str, Any]] = []
    for secret_match in _SECRET_NAME_RE.finditer(line):
        var_name = secret_match.group(1)
        value = secret_match.group(3)
        if not _SECRET_NAMES.search(var_name):
            continue
        if _is_env_lookup(line):
            continue
        if _is_placeholder(value):
            continue
        entries.append(
            make_security_entry(
                filepath,
                line_num,
                line,
                SecurityRule(
                    check_id="hardcoded_secret_name",
                    summary=f"Hardcoded secret in variable '{var_name}'",
                    severity="high",
                    confidence=confidence,
                    remediation="Move secret to environment variable or secrets manager",
                ),
            )
        )
    return entries


def _insecure_random_entries(
    filepath: str, line_num: int, line: str
) -> list[dict[str, Any]]:
    if not (_RANDOM_CALLS.search(line) and _SECURITY_CONTEXT_WORDS.search(line)):
        return []
    return [
        make_security_entry(
            filepath,
            line_num,
            line,
            SecurityRule(
                check_id="insecure_random",
                summary="Insecure random used in security context",
                severity="medium",
                confidence="medium",
                remediation="Use secrets.token_hex() (Python) or crypto.randomUUID() (JS)",
            ),
        )
    ]


def _weak_crypto_entries(
    filepath: str, line_num: int, line: str
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for pattern, label, severity, remediation in _WEAK_CRYPTO_PATTERNS:
        if not pattern.search(line):
            continue
        entries.append(
            make_security_entry(
                filepath,
                line_num,
                line,
                SecurityRule(
                    check_id="weak_crypto_tls",
                    summary=label,
                    severity=severity,
                    confidence="high",
                    remediation=remediation,
                ),
            )
        )
    return entries


def _sensitive_log_entries(
    filepath: str, line_num: int, line: str
) -> list[dict[str, Any]]:
    if not (_LOG_CALLS.search(line) and _SENSITIVE_IN_LOG.search(line)):
        return []
    return [
        make_security_entry(
            filepath,
            line_num,
            line,
            SecurityRule(
                check_id="log_sensitive",
                summary="Sensitive data may be logged",
                severity="medium",
                confidence="medium",
                remediation="Remove sensitive data from log statements",
            ),
        )
    ]


def _detect_secret_format_findings(filepath: str, line_num: int, line: str, is_test: bool) -> list[dict]:
    findings: list[dict] = []
    for label, pattern, severity, remediation in _SECRET_FORMAT_PATTERNS:
        if not pattern.search(line):
            continue
        findings.append(
            make_security_entry(
                filepath,
                line_num,
                "hardcoded_secret_value",
                f"Hardcoded {label} detected",
                confidence="medium" if is_test else "high",
                detail=_security_detail(
                    check_id="hardcoded_secret_value",
                    severity=severity,
                    line=line_num,
                    content=line,
                    remediation=remediation,
                ),
            )
        )
    return findings


def _detect_secret_name_findings(filepath: str, line_num: int, line: str, is_test: bool) -> list[dict]:
    findings: list[dict] = []
    for match in _SECRET_NAME_RE.finditer(line):
        var_name = match.group(1)
        value = match.group(3)
        if not _SECRET_NAMES.search(var_name):
            continue
        if _is_env_lookup(line) or _is_placeholder(value):
            continue
        findings.append(
            make_security_entry(
                filepath,
                line_num,
                "hardcoded_secret_name",
                f"Hardcoded secret in variable '{var_name}'",
                confidence="medium" if is_test else "high",
                detail=_security_detail(
                    check_id="hardcoded_secret_name",
                    severity="high",
                    line=line_num,
                    content=line,
                    remediation="Move secret to environment variable or secrets manager",
                ),
            )
        )
    return findings


def _detect_insecure_random_findings(filepath: str, line_num: int, line: str) -> list[dict]:
    if not (_RANDOM_CALLS.search(line) and _SECURITY_CONTEXT_WORDS.search(line)):
        return []
    return [
        make_security_entry(
            filepath,
            line_num,
            "insecure_random",
            "Insecure random used in security context",
            confidence="medium",
            detail=_security_detail(
                check_id="insecure_random",
                severity="medium",
                line=line_num,
                content=line,
                remediation="Use secrets.token_hex() (Python) or crypto.randomUUID() (JS)",
            ),
        )
    ]


def _detect_weak_crypto_findings(filepath: str, line_num: int, line: str) -> list[dict]:
    findings: list[dict] = []
    for pattern, label, severity, remediation in _WEAK_CRYPTO_PATTERNS:
        if not pattern.search(line):
            continue
        findings.append(
            make_security_entry(
                filepath,
                line_num,
                "weak_crypto_tls",
                label,
                confidence="high",
                detail=_security_detail(
                    check_id="weak_crypto_tls",
                    severity=severity,
                    line=line_num,
                    content=line,
                    remediation=remediation,
                ),
            )
        )
    return findings


def _detect_sensitive_log_findings(filepath: str, line_num: int, line: str) -> list[dict]:
    if not (_LOG_CALLS.search(line) and _SENSITIVE_IN_LOG.search(line)):
        return []
    return [
        make_security_entry(
            filepath,
            line_num,
            "log_sensitive",
            "Sensitive data may be logged",
            confidence="medium",
            detail=_security_detail(
                check_id="log_sensitive",
                severity="medium",
                line=line_num,
                content=line,
                remediation="Remove sensitive data from log statements",
            ),
        )
    ]


def _scan_line_for_security_findings(filepath: str, line_num: int, line: str, is_test: bool) -> list[dict]:
    findings: list[dict] = []
    findings.extend(_detect_secret_format_findings(filepath, line_num, line, is_test))
    findings.extend(_detect_secret_name_findings(filepath, line_num, line, is_test))
    findings.extend(_detect_insecure_random_findings(filepath, line_num, line))
    findings.extend(_detect_weak_crypto_findings(filepath, line_num, line))
    findings.extend(_detect_sensitive_log_findings(filepath, line_num, line))
    return findings


def _security_detail(*, check_id: str, severity: str, line: int, content: str, remediation: str) -> dict[str, Any]:
    return {
        "kind": check_id,
        "severity": severity,
        "line": line,
        "content": content[:200],
        "remediation": remediation,
    }


def detect_security_issues(
    files: list[str],
    zone_map: FileZoneMap | None,
    lang_name: str,
) -> tuple[list[dict], int]:
    """Detect cross-language security issues in source files.

    Returns (entries, potential) where potential = number of files scanned.
    """
    entries: list[dict] = []
    scanned = 0

    for filepath in files:
        # Skip zones excluded from security scanning.
        if zone_map is not None:
            zone = zone_map.get(filepath)
            if zone in (Zone.TEST, Zone.CONFIG, Zone.GENERATED, Zone.VENDOR):
                continue

        try:
            content = Path(filepath).read_text(errors="replace")
        except OSError as exc:
            logger.debug(
                "Skipping unreadable file in security detector: %s (%s)", filepath, exc
            )
            continue

        scanned += 1
        lines = content.splitlines()
        is_test = zone_map is not None and zone_map.get(filepath) == Zone.TEST

        for line_num, line in enumerate(lines, 1):
            if _is_comment_line(line) and not _has_secret_format_match(line):
                continue
            entries.extend(
                _scan_line_for_security_entries(
                    filepath=filepath,
                    line_num=line_num,
                    line=line,
                    is_test=is_test,
                )
            )

    return entries, scanned


def make_security_entry(
    filepath: str,
    line: int,
    *args: Any,
) -> dict[str, Any]:
    """Build a security finding entry dict.

    Accepts both:
    - new form: ``(content, SecurityRule)``
    - legacy form: ``(check_id, summary, severity, confidence, content, remediation)``
    """
    if len(args) == 2 and isinstance(args[1], SecurityRule):
        content = args[0]
        rule = args[1]
    elif len(args) == 6:
        check_id, summary, severity, confidence, content, remediation = args
        rule = SecurityRule(
            check_id=str(check_id),
            summary=str(summary),
            severity=str(severity),
            confidence=str(confidence),
            remediation=str(remediation),
        )
    else:
        raise TypeError(
            "make_security_entry() expects (content, SecurityRule) or "
            "(check_id, summary, severity, confidence, content, remediation)"
        )

    rel_path = rel(filepath)
    return {
        "file": filepath,
        "name": f"security::{rule.check_id}::{rel_path}::{line}",
        "tier": 2,
        "confidence": rule.confidence,
        "summary": rule.summary,
        "detail": {
            "kind": rule.check_id,
            "severity": rule.severity,
            "line": line,
            "content": content[:200],
            "remediation": rule.remediation,
        },
    }
