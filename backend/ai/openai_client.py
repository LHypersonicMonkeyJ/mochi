"""The robot's replies, from OpenAI's Responses API, streamed."""

from __future__ import annotations

from typing import Iterator

from .personality import INSTRUCTIONS


class Brain:
    def __init__(self, model: str, api_key: str | None = None, instructions: str = INSTRUCTIONS,
                 history_turns: int = 10, reasoning_effort: str | None = None, client=None):
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
        self._client = client
        self.model = model
        self.instructions = instructions
        self.reasoning_effort = reasoning_effort  # only for models that reason (GPT-5, o-series)
        self.history_turns = history_turns
        self.history: list[dict] = []  # alternating user / assistant messages

    def reply(self, user_text: str) -> Iterator[str]:
        """Streams the reply as text pieces. The finished reply joins the history."""
        messages = self.history + [{"role": "user", "content": user_text}]
        extra = {"reasoning": {"effort": self.reasoning_effort}} if self.reasoning_effort else {}
        stream = self._client.responses.create(
            model=self.model, instructions=self.instructions, input=messages, stream=True, **extra)
        parts = []
        for event in stream:
            kind = getattr(event, "type", "")
            if kind == "response.output_text.delta":
                parts.append(event.delta)
                yield event.delta
            elif kind in ("error", "response.failed"):
                raise RuntimeError(f"OpenAI error: {getattr(event, 'message', None) or event}")
        self.history = (messages + [{"role": "assistant", "content": "".join(parts)}])[-2 * self.history_turns:]

    def forget(self):
        self.history = []
