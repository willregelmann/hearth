"""What the gateway exports through OpenTelemetry (docs/interfaces/TELEMETRY.md), read back from the SDK's
in-memory exporters. The gateway, its socket and its database are real; claude and the clock are faked."""
import json
import time

import pytest

from conftest import SECRET_REPLY, ask, push, quiet, register, status, wait_until, wakes
from hearth import telemetry as tel
from hearth.home import Config
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

NOTE = "PRIVATE-NOTE-TEXT check the deploy"


class Signals:
    def __init__(self):
        self.spans_out = InMemorySpanExporter()
        tracer = TracerProvider()
        tracer.add_span_processor(SimpleSpanProcessor(self.spans_out))
        self.reader = InMemoryMetricReader()
        self.telemetry = tel.Telemetry(tracer_provider=tracer, meter_provider=MeterProvider(metric_readers=[self.reader]))

    def spans(self, name=None):
        return [s for s in self.spans_out.get_finished_spans() if name is None or s.name == name]

    def points(self, metric: str) -> list:
        data = self.reader.get_metrics_data()
        out = []
        for rm in (data.resource_metrics if data else []):
            for sm in rm.scope_metrics:
                for m in sm.metrics:
                    if m.name == metric:
                        out += [(dict(p.attributes), getattr(p, "value", None), getattr(p, "count", None))
                                for p in m.data.data_points]
        return out


@pytest.fixture
def signals():
    return Signals()


@pytest.fixture
async def traced_gateway(home, fake, clock, signals):
    from hearth import gateway
    running = []

    async def start(**config):
        settings = dict(claude=str(fake.path), tick_s=0.02, retry_s=30.0, retry_max_s=1800.0, shutdown_grace_s=0.0)
        settings.update(config)
        gw = gateway.Gateway(home, clock=clock, config=Config(**settings), telemetry=signals.telemetry)
        await gw.start()
        running.append(gw)
        return gw

    yield start
    for gw in running:
        if gw.ctx is not None:
            await gw.stop(grace=0)


def _exported_text(signals) -> str:
    parts = []
    for s in signals.spans():
        parts += [s.name, json.dumps({k: str(v) for k, v in (s.attributes or {}).items()}),
                  str(s.status.description)]
    data = signals.reader.get_metrics_data()
    parts.append(data.to_json() if data else "")
    return "\n".join(parts)


async def test_a_turns_span_links_to_the_span_of_every_wake_it_delivered(home, fake, root, traced_gateway, signals):
    register(home, "ash", root)
    await traced_gateway()
    await push(home, "ash", "build", note="one")
    await wait_until(lambda: len(fake.ends) == 1, what="the turn")
    await wait_until(lambda: signals.spans("hearth.turn"), what="the turn's span")
    [turn] = signals.spans("hearth.turn")
    [accepted] = signals.spans("hearth.wake")
    assert [l.context.span_id for l in turn.links] == [accepted.context.span_id]
    attrs = turn.attributes
    assert attrs["hearth.agent"] == "ash" and attrs["hearth.conversation"] == "build"
    assert attrs["hearth.turn.outcome"] == "ok" and attrs["session.id"] == fake.starts[0]["session"]


async def test_the_link_survives_a_gateway_restart_between_accepting_and_delivering(
        home, fake, root, traced_gateway, signals, clock):
    register(home, "ash", root)
    first = await traced_gateway()
    await push(home, "ash", "later", delay=600)
    [accepted] = signals.spans("hearth.wake")
    await first.stop(grace=0)
    again = Signals()                    # a new process: nothing in memory carries over
    from hearth import gateway
    second = gateway.Gateway(home, clock=clock, config=Config(claude=str(fake.path), tick_s=0.02),
                             telemetry=again.telemetry)
    await second.start()
    try:
        clock.advance(601)
        await wait_until(lambda: again.spans("hearth.turn"), what="the turn after the restart")
        [turn] = again.spans("hearth.turn")
        assert [l.context.span_id for l in turn.links] == [accepted.context.span_id]
        assert [l.context.trace_id for l in turn.links] == [accepted.context.trace_id]
    finally:
        await second.stop(grace=0)


async def test_a_wake_raised_inside_a_trace_is_a_child_of_it(home, fake, root, traced_gateway, signals):
    register(home, "ash", root)
    await traced_gateway()
    parent = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    await push(home, "ash", "later", delay=600, traceparent=parent)
    [accepted] = signals.spans("hearth.wake")
    assert format(accepted.context.trace_id, "032x") == "0af7651916cd43dd8448eb211c80319c"
    assert format(accepted.parent.span_id, "016x") == "b7ad6b7169203331"
    refused = await ask(home, op="wake", agent="ash", conversation="x", source="t", key="k2", traceparent="nonsense")
    assert not refused["ok"] and "traceparent" in refused["error"]


async def test_claude_codes_telemetry_carries_the_agent_the_turn_and_its_trace(
        home, fake, root, traced_gateway, signals, monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:9")
    monkeypatch.setenv("OTEL_SERVICE_NAME", tel.DEFAULT_SERVICE)
    register(home, "ash", root)
    await traced_gateway()
    await push(home, "ash", "build")
    await wait_until(lambda: signals.spans("hearth.turn"), what="the turn")
    [turn] = signals.spans("hearth.turn")
    start = fake.starts[0]
    assert start["traceparent"].split("-")[1:3] == [format(turn.context.trace_id, "032x"),
                                                   format(turn.context.span_id, "016x")]
    resource = dict(kv.split("=", 1) for kv in start["otel_resource"].split(","))
    assert resource["hearth.agent"] == "ash" and resource["hearth.conversation"] == "build"
    assert resource["hearth.turn.id"] == str(turn.attributes["hearth.turn.id"])
    assert start["otel_service"] == tel.CLAUDE_SERVICE, "the turn inherited the gateway's service name"


async def test_with_no_otel_variables_a_turns_environment_is_left_alone(home, fake, root, start_gateway, monkeypatch):
    for name in ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_SERVICE_NAME", "CLAUDE_CODE_ENABLE_TELEMETRY", "TRACEPARENT"):
        monkeypatch.delenv(name, raising=False)
    register(home, "ash", root)
    await start_gateway()
    await push(home, "ash", "build")
    await wait_until(lambda: len(fake.ends) == 1, what="the turn")
    start = fake.starts[0]
    assert start["traceparent"] is None and start["otel_resource"] is None and start["otel_service"] is None
    assert (await status(home))["telemetry"] == {"signals": [], "problem": None, "service": "hearth"}


def test_with_no_otel_variables_nothing_is_asked_for():
    assert tel.requested({}) == {"traces": False, "metrics": False, "logs": False}
    assert not tel.Telemetry.from_env({}).enabled
    assert tel.requested({"OTEL_EXPORTER_OTLP_ENDPOINT": "http://x:4318"}) == {"traces": True, "metrics": True, "logs": True}
    assert tel.requested({"OTEL_EXPORTER_OTLP_ENDPOINT": "http://x", "OTEL_LOGS_EXPORTER": "none"})["logs"] is False
    assert tel.requested({"OTEL_EXPORTER_OTLP_ENDPOINT": "http://x", "OTEL_SDK_DISABLED": "true"})["traces"] is False


async def test_telemetry_never_carries_a_prompt_a_reply_a_note_or_a_checks_output(
        home, fake, root, traced_gateway, signals):
    register(home, "ash", root, lines=[
        "[[check]]", 'name = "inbox"', f"command = \"echo '{{\\\"conversation\\\": \\\"c\\\", \\\"key\\\": \\\"k\\\", \\\"note\\\": \\\"CHECK-OUTPUT-NOTE\\\"}}'\"",
        "interval = 3600"])
    await traced_gateway()
    await push(home, "ash", "build", note=NOTE)
    await wait_until(lambda: len(fake.ends) >= 2, what="both turns")
    await wait_until(lambda: len(signals.spans("hearth.turn")) >= 2, what="both turns' spans")
    exported = _exported_text(signals)
    for secret in (SECRET_REPLY, "PRIVATE-NOTE-TEXT", "CHECK-OUTPUT-NOTE", "Hearth started this turn"):
        assert secret not in exported, f"{secret!r} was exported"


async def test_wakes_held_back_are_measured_by_why_they_wait(home, fake, root, traced_gateway, signals):
    register(home, "ash", root)
    await traced_gateway()
    await push(home, "ash", "later", delay=3600)
    points = {(a["hearth.agent"], a["hearth.wake.waiting"]): v for a, v, _ in signals.points("hearth.wakes.waiting")}
    assert points[("ash", "not_due")] == 1 and points[("ash", "due")] == 0


async def test_turns_and_checks_are_counted_by_outcome_for_each_agent(home, fake, root, traced_gateway, signals):
    register(home, "ash", root, lines=["[[check]]", 'name = "broken"', 'command = "exit 3"', "interval = 3600"])
    await traced_gateway()
    fake.mode(fail="exit")
    await push(home, "ash", "build")
    await wait_until(lambda: len(fake.ends) == 1, what="the failing turn")
    await wait_until(lambda: signals.points("hearth.turns") and signals.points("hearth.checks"), what="the counts")
    turns = {a["hearth.turn.outcome"]: v for a, v, _ in signals.points("hearth.turns") if a["hearth.agent"] == "ash"}
    checks = {a["hearth.check.outcome"]: v for a, v, _ in signals.points("hearth.checks") if a["hearth.agent"] == "ash"}
    assert turns == {"failed": 1} and checks == {"failed": 1}
    [span] = signals.spans("hearth.check")
    assert span.status.status_code.name == "ERROR"


async def test_a_collector_that_is_down_costs_signals_never_a_turn_and_stopping_is_bounded(
        home, fake, root, clock, monkeypatch):
    from hearth import gateway
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:9")   # nothing listens there
    telemetry = tel.Telemetry.from_env()
    assert telemetry.enabled and telemetry.problem is None
    register(home, "ash", root)
    gw = gateway.Gateway(home, clock=clock, config=Config(claude=str(fake.path), tick_s=0.02), telemetry=telemetry)
    await gw.start()
    try:
        await push(home, "ash", "build")
        async def done():
            return [w["state"] for w in await wakes(home)] == ["done"]
        await wait_until(done, timeout=10, what="the wake to be done, with the collector down")
    finally:
        began = time.monotonic()
        await gw.stop(grace=0)
        assert time.monotonic() - began < tel.SHUTDOWN_S + 2, "stopping waited on a dead collector"


def test_telemetry_asked_for_but_impossible_is_reported_never_silent(monkeypatch):
    shown = tel.Telemetry.from_env({"OTEL_EXPORTER_OTLP_ENDPOINT": "http://x", "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc"})
    assert shown.problem and "grpc" in shown.problem
    import builtins
    real = builtins.__import__

    def no_sdk(name, *args, **kwargs):
        if name.startswith("opentelemetry.sdk"):
            raise ImportError(name)
        return real(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", no_sdk)
    missing = tel.Telemetry.from_env({"OTEL_EXPORTER_OTLP_ENDPOINT": "http://x"})
    assert not missing.enabled and "not installed" in missing.problem
