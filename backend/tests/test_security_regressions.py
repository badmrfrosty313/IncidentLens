"""Regression tests for the Sprint 2 independent-review findings (framework-free)."""

from __future__ import annotations

import json
import math
import re
import time
import tracemalloc

import pytest

from app.analysis.correlation import pairwise_correlations
from app.config import Limits
from app.errors import IncidentLensError
from app.models import Severity
from app.normalization import normalize_severity
from app.parsing import parse_logs, safe_clip
from app.pipeline import analyze_text
from app.redaction import redact_text
from app.reporting import md_code, render_markdown

from .helpers import ev

SECRET_PEM_BODY = ["MIIEowIBAAKCAQEAxSECRETBODYLINE1abcdef", "Zm9vYmFyU0VDUkVUQkFTRTY0TElORTI=", "QUJDREVGR0hJSktMTU5PUFNFQ1JFVA=="]
PEM = "-----BEGIN RSA PRIVATE KEY-----\n" + "\n".join(SECRET_PEM_BODY) + "\n-----END RSA PRIVATE KEY-----"


def _dump(result) -> str:
    return result.model_dump_json() + render_markdown(result)


# ------------------------------------------------------------------ finding 2: clipping and multiline


def test_safe_clip_never_keeps_a_partial_token():
    text = "alpha beta sk-abcdefghijklmnopqrstuvwxyz0123"
    clipped, was = safe_clip(text, 22)  # cuts inside the key
    assert was and clipped == "alpha beta"
    assert safe_clip("a b c", 5) == ("a b c", False)
    assert safe_clip("aaaa bbbb", 4) == ("aaaa", True)  # cut lands exactly on a boundary
    assert safe_clip("x" * 50, 10) == ("", True)  # one giant token: keep nothing


def test_secret_straddling_the_line_limit_is_not_leaked():
    limits = Limits(max_line_chars=60)
    line = "2025-03-14 09:00:00 ERROR svc " + "ok " * 4 + "key sk-abcdefghijklmnopqrstuvwxyz0123456789"
    assert len(line) > 60
    result = analyze_text(line + "\n", limits=limits)
    assert "sk-" not in _dump(result)


def test_malformed_sample_cut_inside_a_secret_is_not_leaked():
    line = "no timestamp here " + "a" * 160 + " sk-abcdefghijklmnopqrstuvwxyz0123456789"
    result = analyze_text(line + "\n2025-03-14 09:00:00 INFO a ok\n")
    samples = [m.sample for m in result.ingest.malformed_samples]
    assert samples and all("sk-" not in s for s in samples)


def test_unterminated_quoted_secret_from_a_clipped_line_is_redacted():
    assert "phrase" not in redact_text('login password: "my secret phrase here')
    assert "phrase" not in redact_text("login token='my secret phrase here")


def test_json_escaped_quotes_around_secrets_are_redacted():
    out = redact_text(r'{"msg":"retry \"password\":\"hunter2secret\" failed"}')
    assert "hunter2secret" not in out


def test_multiline_private_key_in_plaintext_does_not_leak():
    text = f"2025-03-14 09:00:00 ERROR svc dumping key\n{PEM}\n2025-03-14 09:00:01 INFO svc done\n"
    result = analyze_text(text)
    assert not any(part in _dump(result) for part in SECRET_PEM_BODY)
    assert result.ingest.redactions.get("private_key", 0) >= 1
    assert result.ingest.malformed_records == 0  # the key body is swallowed, not reported as junk
    assert result.summary.total_events == 2  # the record after the block is still parsed


def test_private_key_without_a_preceding_record_does_not_leak():
    result = analyze_text(PEM + "\n2025-03-14 09:00:01 INFO svc done\n")
    assert not any(part in _dump(result) for part in SECRET_PEM_BODY)


def test_unterminated_private_key_block_stops_at_the_next_record():
    text = "2025-03-14 09:00:00 ERROR svc key\n-----BEGIN PRIVATE KEY-----\n" + SECRET_PEM_BODY[0] + "\n2025-03-14 09:00:05 INFO svc next\n"
    result = analyze_text(text)
    assert SECRET_PEM_BODY[0] not in _dump(result)
    assert result.summary.total_events == 2


def test_private_key_in_json_string_and_jsonl_does_not_leak():
    as_json = json.dumps([{"timestamp": "2025-03-14T09:00:00Z", "level": "error", "service": "a", "message": "key " + PEM}])
    as_jsonl = as_json[1:-1] + "\n"
    for payload in (as_json, as_jsonl):
        assert not any(part in _dump(analyze_text(payload)) for part in SECRET_PEM_BODY)


def test_secret_beyond_json_field_cap_is_not_partially_kept():
    msg = "x " * 495 + "token sk-abcdefghijklmnopqrstuvwxyz0123456789"  # key straddles the 1000-char cap
    payload = json.dumps({"timestamp": "2025-03-14T09:00:00Z", "level": "error", "service": "a", "message": msg}) + "\n"
    assert "sk-" not in _dump(analyze_text(payload))


# ------------------------------------------------------------------ finding 3: numeric severity


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf"), "²", "٣", "9" * 5000, "1e999", -5, 10**30, 1e308, "99999", "", " ", [], {}],
    ids=["nan", "inf", "-inf", "superscript-digit", "arabic-digit", "5000-digits", "1e999", "negative", "1e30-int", "1e308", "5-digits", "empty", "space", "list", "dict"],
)
def test_malformed_numeric_severity_is_unknown_not_a_crash(value):
    assert normalize_severity(value) is None


def test_valid_numeric_severities_still_map():
    assert normalize_severity(3) is Severity.ERROR
    assert normalize_severity("4") is Severity.WARNING
    assert normalize_severity(30) is Severity.INFO
    assert normalize_severity(50.0) is Severity.ERROR
    assert normalize_severity(60) is Severity.CRITICAL


def test_nan_and_huge_levels_in_json_input_do_not_fail_analysis():
    payload = (
        '{"timestamp":"2025-03-14T09:00:00Z","level":NaN,"service":"a","message":"x"}\n'
        '{"timestamp":"2025-03-14T09:00:01Z","level":Infinity,"service":"a","message":"y"}\n'
        + '{"timestamp":"2025-03-14T09:00:02Z","level":' + "9" * 400 + ',"service":"a","message":"z"}\n'
        + '{"timestamp":"2025-03-14T09:00:03Z","level":"' + "9" * 5000 + '","service":"a","message":"w"}\n'
    )
    result = analyze_text(payload)
    assert result.summary.total_events == 4 and result.ingest.events_without_severity == 4


# ------------------------------------------------------------------ finding 4: high-cardinality services


def test_correlation_allocates_only_for_the_selected_services():
    n_buckets, n_services = 4000, 15000
    events = [ev(i, i, "ERROR", f"svc-{i}", "boom") for i in range(n_services)]  # one error each
    events += [ev(n_services + i, i % 600, "ERROR", f"hot-{i % 4}", "boom") for i in range(400)]
    index = {e.id: min(int(e.timestamp.timestamp() - events[0].timestamp.timestamp()) % n_buckets, n_buckets - 1) for e in events}
    tracemalloc.start()
    try:
        pairwise_correlations(events, n_buckets, index, 1)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # Allocating a 4000-slot list for each of 15k services would need ~480 MB.
    assert peak < 20 * 1024 * 1024


def test_correlation_selects_top_services_by_volume_then_name():
    events, i = [], 0
    for svc, n in (("zeta", 5), ("alpha", 5), ("busy", 50), ("rare", 2)):
        for k in range(n):
            events.append(ev(i, k * 10, "ERROR", svc, "boom"))
            i += 1
    index = {e.id: int(e.timestamp.timestamp() - events[0].timestamp.timestamp()) // 10 for e in events}
    pairs = pairwise_correlations(events, 60, index, 10, top_services=2)
    names = {p.service_a for p in pairs} | {p.service_b for p in pairs}
    assert names <= {"busy", "alpha"}  # "rare" is below the minimum, "zeta" loses the tie to "alpha"


def test_high_cardinality_services_end_to_end_stay_bounded():
    lines = [f"2025-03-14 09:{(i // 60) % 60:02d}:{i % 60:02d} ERROR svc{i} boom {i}" for i in range(20000)]
    start = time.perf_counter()
    result = analyze_text("\n".join(lines))
    assert time.perf_counter() - start < 30
    assert result.summary.total_events == 20000


# ------------------------------------------------------------------ finding 5: markdown table injection


def _table_rows(markdown: str, header_prefix: str) -> list[str]:
    lines = markdown.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith(header_prefix))
    rows = []
    for ln in lines[start:]:
        if not ln.startswith("|"):
            break
        rows.append(ln)
    return rows


def _cells(row: str) -> int:
    return len(re.findall(r"(?<!\\)\|", row)) - 1


def test_md_code_cell_mode_escapes_pipes():
    assert md_code("a|b", cell=True) == "`a\\|b`"
    assert md_code("a|b") == "`a|b`"  # outside tables the pipe is harmless


def test_pipes_in_log_messages_cannot_break_the_pattern_table():
    logs = "".join(
        f"2025-03-14 09:00:{i:02d} ERROR svc payload a|b|c | injected | cell | {i % 3}\n" for i in range(12)
    )
    md = render_markdown(analyze_text(logs))
    rows = _table_rows(md, "| Count | Severity | Services | Pattern |")
    assert len(rows) >= 3
    assert {_cells(r) for r in rows} == {4}, rows
    assert "injected" in "".join(rows)  # content is kept, just contained in its cell


def test_pipes_in_service_names_cannot_break_tables():
    result = analyze_text("".join(f"2025-03-14 09:00:{i:02d} ERROR [a|b] boom\n" for i in range(6)))
    rows = _table_rows(render_markdown(result), "| Count | Severity | Services | Pattern |")
    assert {_cells(r) for r in rows} == {4}


# ------------------------------------------------------------------ large, malformed and adversarial input


def test_record_limit_rejects_instead_of_truncating():
    with pytest.raises(IncidentLensError) as err:
        analyze_text("x\n" * 50, limits=Limits(max_events=10))
    assert err.value.status_code == 413


ADVERSARIAL = {
    "deeply_nested_json": "[" * 50000 + "]" * 50000,
    "deeply_nested_jsonl": '{"a":' * 20000 + "1" + "}" * 20000 + "\n",
    "huge_single_line": "2025-03-14 09:00:00 ERROR svc " + "A" * 3_000_000,
    "only_whitespace_lines": "   \n\t\n" * 10000 + "x",
    "nul_bytes": "2025-03-14 09:00:00 ERROR svc a\x00b\x00\n" * 50,
    "binary_garbage": bytes(range(256)).decode("latin-1") * 200,
    "json_numbers": "[" + ",".join(["1"] * 20000) + "]",
    "bogus_timestamps": "".join(f"{y}-13-45 99:99:99 ERROR svc x\n" for y in range(2000, 2100)),
    "unicode_mix": "2025-03-14 09:00:00 ERROR s‮\u0000 ퟿\U0010ffff ​ boom\n" * 20,
    "pem_without_end": "-----BEGIN PRIVATE KEY-----\n" + "QUJD\n" * 50000,
    "quote_bomb": "2025-03-14 09:00:00 ERROR svc password=" + '"' * 100000 + "\n",
}


@pytest.mark.parametrize("name", sorted(ADVERSARIAL))
def test_adversarial_input_never_crashes_or_hangs(name):
    start = time.perf_counter()
    try:
        result = analyze_text(ADVERSARIAL[name])
        assert json.loads(result.model_dump_json())  # always serialisable
    except IncidentLensError:
        pass  # a clean, typed rejection is an acceptable outcome
    assert time.perf_counter() - start < 20


def test_parse_logs_rejects_unknown_format_cleanly():
    with pytest.raises(IncidentLensError):
        parse_logs("x", format_hint="yaml")


def test_nan_never_reaches_the_response():
    result = analyze_text('{"timestamp":"2025-03-14T09:00:00Z","level":"error","service":"a","message":"x","status":NaN}\n')
    assert not math.isnan(result.summary.error_ratio)
