import pytest

from app.config import Limits
from app.errors import EmptyInputError, InputTooLargeError, TooManyEventsError
from app.llm import HypothesisEnricher, NullEnricher
from app.pipeline import analyze_text

LINE = "2025-03-14T09:00:{s:02d}Z INFO [a] hello {s}\n"


def test_empty_and_whitespace_input_rejected():
    for text in ("", "   \n\t\n"):
        with pytest.raises(EmptyInputError):
            analyze_text(text)


def test_oversized_input_rejected_with_clear_message():
    with pytest.raises(InputTooLargeError) as e:
        analyze_text("x" * 2000, limits=Limits(max_input_bytes=1000))
    assert "limit" in e.value.message and e.value.status_code == 413


def test_size_limit_counts_bytes_not_characters():
    # 600 two-byte characters = 1200 bytes
    with pytest.raises(InputTooLargeError):
        analyze_text("é" * 600, limits=Limits(max_input_bytes=1000))


def test_too_many_events_rejected_not_silently_truncated():
    text = "".join(LINE.format(s=i % 60) for i in range(200))
    with pytest.raises(TooManyEventsError) as e:
        analyze_text(text, limits=Limits(max_events=100))
    assert e.value.status_code == 413


def test_exactly_at_event_limit_is_accepted():
    text = "".join(LINE.format(s=i % 60) for i in range(100))
    assert analyze_text(text, limits=Limits(max_events=100)).summary.total_events == 100


def test_malformed_lines_count_toward_event_limit():
    with pytest.raises(TooManyEventsError):
        analyze_text("garbage\n" * 500, limits=Limits(max_events=100))


def test_all_malformed_input_returns_insufficient_evidence():
    r = analyze_text("garbage\nmore garbage\n")
    assert r.summary.total_events == 0 and r.verdict == "insufficient_evidence"
    assert r.ingest.malformed_records == 2 and r.ingest.malformed_samples


def test_malformed_sample_cap():
    r = analyze_text("garbage\n" * 50 + LINE.format(s=1))
    assert len(r.ingest.malformed_samples) <= Limits().max_malformed_samples


def test_returned_events_are_capped_but_errors_are_prioritized():
    lines = [LINE.format(s=i % 60).replace("INFO", "INFO") for i in range(300)]
    lines += ["2025-03-14T09:01:00Z ERROR [a] boom\n"] * 5
    r = analyze_text("".join(lines), limits=Limits(max_returned_events=50))
    assert r.events_truncated and len(r.events) == 50 and r.events_total == 305
    assert sum(e.severity.value == "ERROR" for e in r.events) == 5


def test_null_enricher_is_a_noop_and_satisfies_the_protocol():
    assert isinstance(NullEnricher(), HypothesisEnricher)
    plain = analyze_text(LINE.format(s=1) * 6)
    assert analyze_text(LINE.format(s=1) * 6, enricher=NullEnricher()) == plain


def test_no_network_or_disk_access_during_analysis(monkeypatch):
    import socket

    def deny(*a, **k):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr("builtins.open", deny)
    analyze_text("".join(LINE.format(s=i % 60) for i in range(20)))
