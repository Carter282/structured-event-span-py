"""Span tree with monotonic-style timestamps and deterministic export."""

from __future__ import annotations

import time
from contextlib import AbstractContextManager
from typing import Any, Callable, Dict, List, Optional


class Span:
    """A single operation span within a tree.

    Children are appended in completion order, so the tree reflects the order
    in which spans actually finished rather than the order they started. This
    is deliberate: it makes nested exports readable as a transcript without a
    separate sort at export time.
    """

    __slots__ = ("name", "_metadata", "_start", "_end", "_children", "_recorder")

    def __init__(
        self,
        name: str,
        *,
        metadata: Optional[Dict[str, Any]] = None,
        recorder: Optional["SpanRecorder"] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = name
        # Copy defensively so the caller can mutate their dict after creation
        # without retroactively changing what this span recorded.
        self._metadata = dict(metadata) if metadata else {}
        self._start = clock()
        self._end: Optional[float] = None
        self._children: List[Span] = []
        self._recorder = recorder

    @property
    def metadata(self) -> Dict[str, Any]:
        return dict(self._metadata)

    @property
    def start(self) -> float:
        return self._start

    @property
    def end(self) -> Optional[float]:
        return self._end

    @property
    def duration(self) -> Optional[float]:
        if self._end is None:
            return None
        return self._end - self._start

    @property
    def children(self) -> List[Span]:
        return list(self._children)

    def add_metadata(self, **kwargs: Any) -> None:
        """Merge keys into this span's metadata.

        Returns ``None`` rather than the span to make it obvious at call sites
        that this is a mutation, not a builder. Overwriting keys is allowed.
        """
        self._metadata.update(kwargs)

    def _close(self, clock: Callable[[], float]) -> None:
        # Idempotent: closing an already-closed span is a no-op rather than an
        # error. This lets ``__exit__`` stay simple when a recorder also closes
        # the span in a finally block.
        if self._end is None:
            self._end = clock()

    def to_dict(self) -> Dict[str, Any]:
        if self._end is None:
            raise ValueError(f"Span '{self.name}' is still open")
        result: Dict[str, Any] = {
            "name": self.name,
            "start": self._start,
            "end": self._end,
            "duration": self.duration,
        }
        if self._metadata:
            result["metadata"] = dict(self._metadata)
        if self._children:
            result["children"] = [c.to_dict() for c in self._children]
        return result


class SpanRecorder:
    """Owns the clock and the root span; use as a context manager to build trees."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self._current: List[Span] = []
        self._root: Optional[Span] = None

    @property
    def root(self) -> Optional[Span]:
        return self._root

    def __enter__(self) -> "SpanRecorder":
        return self

    def __exit__(self, *exc: Any) -> None:
        # Don't close the root here; the caller closes it via the span it got
        # from ``span()``. The recorder's own context just scopes ownership.
        pass

    def span(
        self,
        name: str,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AbstractContextManager:  # type: ignore[type-arg]
        """Open a new span, parenting it to the innermost open span (or root)."""
        s = Span(name, metadata=metadata, recorder=self, clock=self._clock)
        if not self._current:
            self._root = s
        else:
            self._current[-1]._children.append(s)
        self._current.append(s)
        return _SpanContext(self, s)


class _SpanContext(AbstractContextManager):  # type: ignore[type-arg]
    """Context manager for a single span; appends itself to its parent on exit."""

    __slots__ = ("_recorder", "_span")

    def __init__(self, recorder: SpanRecorder, span: Span) -> None:
        self._recorder = recorder
        self._span = span

    def __enter__(self) -> Span:
        return self._span

    def __exit__(self, *exc: Any) -> None:
        self._span._close(self._recorder._clock)
        # Pop ourselves off the open-stack. Guard against double-exit by
        # checking membership; a robust library shouldn't rely on callers being
        # perfect, but we still only pop once.
        if self._span in self._recorder._current:
            # Remove the rightmost occurrence, which is this span.
            for i in range(len(self._recorder._current) - 1, -1, -1):
                if self._recorder._current[i] is self._span:
                    del self._recorder._current[i]
                    break


class SpanTree:
    """Thin wrapper around a completed root span for export."""

    def __init__(self, root: Span) -> None:
        if root.end is None:
            raise ValueError("Root span is not closed")
        self._root = root

    @property
    def root(self) -> Span:
        return self._root

    def to_dict(self) -> Dict[str, Any]:
        return self._root.to_dict()


def export_dict(tree: SpanTree) -> Dict[str, Any]:
    """Serialize a ``SpanTree`` to a plain dict suitable for JSON or tracing backends."""
    return tree.to_dict()
