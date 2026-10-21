# structured-event-span-py

A context manager that records nested operation spans with start time, end time, duration, and arbitrary metadata into a tree, exportable to a plain dict for tracing backends.

```python
from structured_event_span_py import SpanRecorder, SpanTree, export_dict

with SpanRecorder() as r:
    with r.span("request", metadata={"method": "GET"}) as req:
        req.add_metadata(http_status=200)
        with r.span("db_query", metadata={"table": "users"}):
            pass

tree = SpanTree(r.root)
print(export_dict(tree))
```

## Why this exists

Tracing backends all want roughly the same shape: a tree of spans, each with a name, timing, and free-form metadata. The libraries that ship with those backends tend to pull in protobuf, gRPC, or vendor SDKs. This library gives you the tree and the export format and nothing else, so you can hand the dict to whatever transport you already have.

The trade-off: there is no built-in serialization to any specific backend. You call `export_dict(tree)` and get a plain dict. If you want OTLP or Zipkin JSON, you convert it yourself. That is one less dependency to break and one less format to drift on.

## The awkward edge

Children are appended to their parent in **completion order**, not start order. If span A starts before span B but B finishes first, B appears before A in `children`. This keeps the export readable as a transcript but means you cannot assume the child list is sorted by `start`. If you need start-order, sort `children` by `start` after export.

## Exported names

- `Span` — a single span. Construct directly only if you are not using a recorder.
- `SpanRecorder` — owns the clock and the root span. Call `r.span(name, metadata=...)` as a context manager.
- `SpanTree` — wraps a closed root span. Raises `ValueError` if the root is still open.
- `export_dict(tree)` — returns a plain dict suitable for `json.dumps` or a tracing backend.

`SpanRecorder` and `span()` accept an optional `clock` callable for deterministic testing; the default is `time.monotonic`.
