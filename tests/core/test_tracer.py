"""Tests for StructuredLogTracer."""
import json
import logging
import pytest

from core.rag.tracer import StructuredLogTracer


@pytest.fixture
def tracer():
    return StructuredLogTracer()


def test_start_trace_logs_json(tracer, caplog):
    with caplog.at_level(logging.INFO, logger="core.rag.tracer"):
        tracer.start_trace("trace-123")

    assert len(caplog.records) == 1
    data = json.loads(caplog.records[0].message)
    assert data["event"] == "trace_start"
    assert data["trace_id"] == "trace-123"


def test_log_step_includes_trace_id(tracer, caplog):
    with caplog.at_level(logging.INFO, logger="core.rag.tracer"):
        tracer.start_trace("trace-abc")
        tracer.log_step("intent", {"result": "in_scope"})

    step_record = caplog.records[1]
    data = json.loads(step_record.message)
    assert data["event"] == "step"
    assert data["trace_id"] == "trace-abc"
    assert data["step"] == "intent"
    assert data["data"] == {"result": "in_scope"}


def test_end_trace_logs_json(tracer, caplog):
    with caplog.at_level(logging.INFO, logger="core.rag.tracer"):
        tracer.start_trace("trace-xyz")
        tracer.end_trace()

    end_record = caplog.records[1]
    data = json.loads(end_record.message)
    assert data["event"] == "trace_end"
    assert data["trace_id"] == "trace-xyz"


def test_trace_id_cleared_after_end(tracer, caplog):
    with caplog.at_level(logging.INFO, logger="core.rag.tracer"):
        tracer.start_trace("trace-1")
        tracer.end_trace()
        tracer.log_step("orphan_step", {})

    orphan = caplog.records[2]
    data = json.loads(orphan.message)
    assert data["trace_id"] == ""


def test_all_log_records_are_valid_json(tracer, caplog):
    with caplog.at_level(logging.INFO, logger="core.rag.tracer"):
        tracer.start_trace("t1")
        tracer.log_step("step1", {"key": "value"})
        tracer.log_step("step2", {"num": 42})
        tracer.end_trace()

    for record in caplog.records:
        data = json.loads(record.message)
        assert "event" in data
