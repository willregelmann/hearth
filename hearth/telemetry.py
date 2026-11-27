"""Telemetry: what the gateway exports about itself through OpenTelemetry (docs/interfaces/TELEMETRY.md).

Configured only by the standard OTEL_* variables. When none of them asks for anything, every call here
does nothing and Hearth behaves exactly as without it. When they ask and it can't be produced (the SDK
isn't installed, an exporter is unknown), ``problem`` says why, for status and the log.

The SDK exports on threads of its own, so nothing in the gateway waits on a collector, and shutting down
waits for it only for a bounded time. Nothing here is ever given a prompt, a reply, a wake's note or a
check's output, so none of them can be exported.
"""
from __future__ import annotations

import logging
import os
import threading
import urllib.parse
from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional

log = logging.getLogger("hearth")

SIGNALS = ("traces", "metrics", "logs")
SHUTDOWN_S = 5.0
DEFAULT_SERVICE = "hearth"
CLAUDE_SERVICE = "claude-code"


def requested(env: Mapping[str, str]) -> dict:
    """Which signals the OTEL_* variables ask for. Only an endpoint, or an exporter named outright,
    asks for one: with nothing set, nothing is exported."""
    if env.get("OTEL_SDK_DISABLED", "").strip().lower() == "true":
        return {s: False for s in SIGNALS}
    out = {}
    for s in SIGNALS:
        exporter = env.get(f"OTEL_{s.upper()}_EXPORTER")
        if exporter is not None:
            out[s] = exporter.strip().lower() not in ("", "none")
        else:
            out[s] = bool(env.get("OTEL_EXPORTER_OTLP_ENDPOINT") or env.get(f"OTEL_EXPORTER_OTLP_{s.upper()}_ENDPOINT"))
    return out


def asks_for_telemetry(env: Mapping[str, str]) -> bool:
    """Whether a process given this environment would export anything: Hearth itself, or Claude Code."""
    return any(requested(env).values()) or env.get("CLAUDE_CODE_ENABLE_TELEMETRY", "") not in ("", "0", "false")


def _encode(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def claude_env(env: dict, *, agent: str, conversation: str, turn_id: int, traceparent: Optional[str],
               gateway_service: str) -> None:
    """Give Claude Code's own telemetry for a turn the turn's identity and trace context. Only when the
    environment asks for telemetry at all; otherwise the turn's environment is left exactly as it was."""
    if not asks_for_telemetry(env):
        return
    mine = f"hearth.agent={_encode(agent)},hearth.conversation={_encode(conversation)},hearth.turn.id={turn_id}"
    given = env.get("OTEL_RESOURCE_ATTRIBUTES", "").strip().strip(",")
    env["OTEL_RESOURCE_ATTRIBUTES"] = f"{given},{mine}" if given else mine
    # A service name inherited from the gateway would make every turn look like the gateway.
    if env.get("OTEL_SERVICE_NAME", gateway_service) == gateway_service:
        env["OTEL_SERVICE_NAME"] = CLAUDE_SERVICE
    if traceparent:
        env["TRACEPARENT"] = traceparent
    else:
        env.pop("TRACEPARENT", None)


@dataclass
class WakeSpan:
    """The span of a wake being accepted. ``traceparent`` is what the wake carries, so the turn that
    delivers it can link to it after any restart."""
    traceparent: Optional[str] = None
    _span: object = None

    def accepted(self, wake_id: int, duplicate: bool) -> None:
        if self._span is not None:
            self._span.set_attribute("hearth.wake.id", wake_id)
            self._span.set_attribute("hearth.wake.duplicate", duplicate)
            self._span.end()


@dataclass
class TurnSpan:
    traceparent: Optional[str] = None
    _end: Callable = field(default=lambda *a, **k: None)

    def end(self, outcome: str, detail: str, session_id: Optional[str], duration: float) -> None:
        self._end(outcome, detail, session_id, duration)


@dataclass
class CheckSpan:
    traceparent: Optional[str] = None
    _end: Callable = field(default=lambda *a, **k: None)

    def end(self, ok: bool, raised: int, duration: float, error: Optional[str] = None) -> None:
        self._end(ok, raised, duration, error)


class Telemetry:
    """The gateway's telemetry. Made with no providers, it does nothing."""

    def __init__(self, *, tracer_provider=None, meter_provider=None, logger_provider=None,
                 problem: Optional[str] = None, service: str = DEFAULT_SERVICE):
        self.problem = problem
        self.service = service
        self._providers = [p for p in (tracer_provider, meter_provider, logger_provider) if p is not None]
        self._signals = {"traces": tracer_provider is not None, "metrics": meter_provider is not None,
                         "logs": logger_provider is not None}
        self._state: Optional[Callable[[], dict]] = None
        self._log_handler = None
        self._tracer = tracer_provider.get_tracer("hearth") if tracer_provider is not None else None
        if tracer_provider is not None:
            from opentelemetry import trace
            from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
            self._trace, self._propagator = trace, TraceContextTextMapPropagator()
        self._meter = meter_provider.get_meter("hearth") if meter_provider is not None else None
        if self._meter is not None:
            m = self._meter
            self._accepted = m.create_counter("hearth.wakes.accepted", unit="{wake}",
                                              description="Wakes accepted, by source and route")
            self._delay = m.create_histogram("hearth.wake.delay", unit="s",
                                             description="How long after it was due a wake reached a turn")
            self._turns = m.create_counter("hearth.turns", unit="{turn}", description="Turns, by outcome")
            self._duration = m.create_histogram("hearth.turn.duration", unit="s", description="How long turns took")
            self._checks = m.create_counter("hearth.checks", unit="{run}", description="Check runs, by outcome")
            m.create_observable_gauge("hearth.wakes.waiting", callbacks=[self._observe_waiting], unit="{wake}",
                                      description="Wakes not yet done, by why they wait")
            m.create_observable_gauge("hearth.sessions.open", callbacks=[self._observe_sessions], unit="{session}",
                                      description="Sessions a person has open")
        if logger_provider is not None:
            from opentelemetry.sdk._logs import LoggingHandler
            self._log_handler = LoggingHandler(logger_provider=logger_provider)
            log.addHandler(self._log_handler)

    # Making one -----------------------------------------------------------------------------------

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Telemetry":
        """What the OTEL_* variables ask for. Asked for and impossible is a problem, never silence."""
        wanted = requested(env)
        service = env.get("OTEL_SERVICE_NAME") or DEFAULT_SERVICE
        if not any(wanted.values()):
            return cls(service=service)
        try:
            from opentelemetry.sdk.resources import Resource
        except ImportError:
            return cls(problem="telemetry is configured, but the OpenTelemetry SDK is not installed "
                               "(install hearth[otel])", service=service)
        resource = Resource.create({"service.name": service})
        made, problems = {}, []
        for signal in SIGNALS:
            if not wanted[signal]:
                continue
            try:
                made[signal] = _provider(signal, env, resource)
            except _Unavailable as exc:
                problems.append(f"{signal}: {exc}")
        problem = "; ".join(problems) or None
        if problem:
            log.error("telemetry: %s", problem)
        return cls(tracer_provider=made.get("traces"), meter_provider=made.get("metrics"),
                   logger_provider=made.get("logs"), problem=problem, service=service)

    @property
    def enabled(self) -> bool:
        return bool(self._providers)

    def report(self) -> dict:
        return {"signals": [s for s, on in self._signals.items() if on], "problem": self.problem,
                "service": self.service}

    def watch(self, state: Optional[Callable[[], dict]]) -> None:
        """``state()`` returns {"waiting": [(agent, why, n)], "sessions": [(agent, n)]}, read on the SDK's thread."""
        self._state = state

    def shutdown(self, timeout: float = SHUTDOWN_S) -> None:
        if self._log_handler is not None:
            log.removeHandler(self._log_handler)
        providers, self._providers = self._providers, []

        def flush() -> None:
            for p in providers:
                try:
                    p.shutdown()
                except Exception:   # a collector that is down costs signals, nothing else
                    pass
        t = threading.Thread(target=flush, name="hearth-telemetry-shutdown", daemon=True)
        t.start()
        t.join(timeout)

    # Spans and measurements -----------------------------------------------------------------------

    def _context(self, traceparent: Optional[str]):
        return self._propagator.extract({"traceparent": traceparent}) if traceparent else None

    def _carrier(self, span) -> Optional[str]:
        carrier: dict = {}
        self._propagator.inject(carrier, context=self._trace.set_span_in_context(span))
        return carrier.get("traceparent")

    def wake(self, *, agent: str, source: str, route: str, conversation: str,
             parent: Optional[str] = None) -> WakeSpan:
        if self._meter is not None:
            self._accepted.add(1, {"hearth.agent": agent, "hearth.wake.source": source, "hearth.wake.route": route})
        if self._tracer is None:
            return WakeSpan()
        span = self._tracer.start_span("hearth.wake", context=self._context(parent),
                                       kind=self._trace.SpanKind.PRODUCER,
                                       attributes={"hearth.agent": agent, "hearth.wake.source": source,
                                                   "hearth.wake.route": route, "hearth.conversation": conversation})
        return WakeSpan(self._carrier(span), span)

    def turn(self, *, agent: str, conversation: str, session_id: Optional[str], turn_id: int,
             wakes: list, started: float) -> TurnSpan:
        """``wakes`` is [(source, traceparent, due_at, attempts)] for every wake the turn was shown."""
        sources = sorted({w[0] for w in wakes})
        if self._meter is not None:
            for source, _, due_at, _ in wakes:
                self._delay.record(max(0.0, started - due_at), {"hearth.agent": agent, "hearth.wake.source": source})
        span = None
        if self._tracer is not None:
            from opentelemetry.trace import Link
            links = []
            for _, traceparent, _, _ in wakes:
                ctx = self._context(traceparent)
                linked = self._trace.get_current_span(ctx).get_span_context() if ctx is not None else None
                if linked is not None and linked.is_valid:
                    links.append(Link(linked))
            attrs = {"hearth.agent": agent, "hearth.conversation": conversation, "hearth.turn.id": turn_id,
                     "hearth.wakes": len(wakes), "hearth.wake.sources": sources,
                     "hearth.wake.attempts": max((w[3] for w in wakes), default=0)}
            if session_id:
                attrs["session.id"] = session_id
            span = self._tracer.start_span("hearth.turn", links=links, attributes=attrs,
                                           kind=self._trace.SpanKind.CONSUMER, start_time=int(started * 1e9))

        def end(outcome: str, detail: str, session: Optional[str], duration: float) -> None:
            labels = {"hearth.agent": agent, "hearth.turn.outcome": outcome}
            if self._meter is not None:
                self._turns.add(1, labels)
                self._duration.record(duration, labels)
            if span is not None:
                span.set_attribute("hearth.turn.outcome", outcome)
                if session:
                    span.set_attribute("session.id", session)
                if outcome not in ("ok", "deferred"):
                    from opentelemetry.trace import Status, StatusCode
                    span.set_status(Status(StatusCode.ERROR, detail[:200]))
                span.end(end_time=int((started + duration) * 1e9))
        return TurnSpan(self._carrier(span) if span is not None else None, end)

    def check(self, *, agent: str, check: str, started: float) -> "CheckSpan":
        """A check run's span. Its ``traceparent`` is the parent of the wakes the run raises."""
        span = None
        if self._tracer is not None:
            span = self._tracer.start_span("hearth.check", start_time=int(started * 1e9),
                                           attributes={"hearth.agent": agent, "hearth.check.name": check})

        def end(ok: bool, raised: int, duration: float, error: Optional[str]) -> None:
            outcome = "ok" if ok else "failed"
            if self._meter is not None:
                self._checks.add(1, {"hearth.agent": agent, "hearth.check.name": check,
                                     "hearth.check.outcome": outcome})
            if span is not None:
                span.set_attribute("hearth.check.outcome", outcome)
                span.set_attribute("hearth.wakes", raised)
                if not ok:
                    from opentelemetry.trace import Status, StatusCode
                    span.set_status(Status(StatusCode.ERROR, (error or "")[:200]))
                span.end(end_time=int((started + duration) * 1e9))
        return CheckSpan(self._carrier(span) if span is not None else None, end)

    def _observe(self, key: str, attrs: Callable):
        from opentelemetry.metrics import Observation
        if self._state is None:
            return []
        try:
            rows = self._state().get(key, [])
        except Exception:
            log.exception("telemetry: reading the gateway's state for a measurement failed")
            return []
        return [Observation(row[-1], attrs(row)) for row in rows]

    def _observe_waiting(self, options):
        return self._observe("waiting", lambda r: {"hearth.agent": r[0], "hearth.wake.waiting": r[1]})

    def _observe_sessions(self, options):
        return self._observe("sessions", lambda r: {"hearth.agent": r[0]})


class _Unavailable(Exception):
    pass


def _provider(signal: str, env: Mapping[str, str], resource):
    exporter = (env.get(f"OTEL_{signal.upper()}_EXPORTER") or "otlp").strip().lower()
    if "," in exporter:
        raise _Unavailable(f"only one exporter per signal is supported, not {exporter!r}")
    protocol = (env.get(f"OTEL_EXPORTER_OTLP_{signal.upper()}_PROTOCOL")
                or env.get("OTEL_EXPORTER_OTLP_PROTOCOL") or "http/protobuf").strip().lower()
    if exporter not in ("otlp", "console"):
        raise _Unavailable(f"exporter {exporter!r} is not supported (use otlp or console)")
    if exporter == "otlp" and protocol not in ("http/protobuf",):
        raise _Unavailable(f"OTLP protocol {protocol!r} is not supported (use http/protobuf)")
    try:
        if signal == "traces":
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
            if exporter == "otlp":
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as Exp
            else:
                Exp = ConsoleSpanExporter
            provider = TracerProvider(resource=resource)
            provider.add_span_processor(BatchSpanProcessor(Exp()))
            return provider
        if signal == "metrics":
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
            if exporter == "otlp":
                from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter as Exp
            else:
                Exp = ConsoleMetricExporter
            return MeterProvider(resource=resource, metric_readers=[PeriodicExportingMetricReader(Exp())])
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter
        if exporter == "otlp":
            from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter as Exp
        else:
            Exp = ConsoleLogExporter
        provider = LoggerProvider(resource=resource)
        provider.add_log_record_processor(BatchLogRecordProcessor(Exp()))
        return provider
    except ImportError as exc:
        raise _Unavailable(f"the {exporter} exporter is not installed ({exc.name}); install hearth[otel]") from None
