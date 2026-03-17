from __future__ import annotations

from memllm_letta_integration import RealLettaGateway


class _BrokenStepsResource:
    def list(self, **kwargs):  # noqa: ANN003
        raise RuntimeError("server-side steps endpoint failure")


class _BrokenClient:
    def __init__(self) -> None:
        self.steps = _BrokenStepsResource()


def test_real_letta_gateway_treats_step_trace_lookup_as_best_effort() -> None:
    gateway = object.__new__(RealLettaGateway)
    gateway._client = _BrokenClient()  # type: ignore[attr-defined]

    assert gateway.list_recent_steps(agent_id="agent-1", limit=5) == []
