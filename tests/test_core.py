import json
import unittest

from structured_event_span_py import (
    Span,
    SpanRecorder,
    SpanTree,
    export_dict,
)


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        self.t += 1.0
        return self.t


class TestSpanRecorder(unittest.TestCase):
    def test_single_span(self):
        clock = FakeClock()
        with SpanRecorder(clock=clock) as r:
            with r.span("op") as s:
                pass
        root = r.root
        self.assertEqual(root.name, "op")
        self.assertEqual(root.start, 1.0)
        self.assertEqual(root.end, 2.0)
        self.assertEqual(root.duration, 1.0)
        self.assertEqual(root.children, [])
        tree = SpanTree(root)
        self.assertEqual(tree.to_dict(), {
            "name": "op",
            "start": 1.0,
            "end": 2.0,
            "duration": 1.0,
        })

    def test_nested_children_append_on_exit(self):
        clock = FakeClock()
        with SpanRecorder(clock=clock) as r:
            with r.span("a"):
                with r.span("b"):
                    with r.span("c"):
                        pass
                with r.span("d"):
                    pass
        root = r.root
        # Children reflect completion order: c finishes before d's parent.
        # b finishes before d, so root.children == [b, d], and b.children == [c].
        self.assertEqual([c.name for c in root.children], ["b", "d"])
        b = root.children[0]
        self.assertEqual([c.name for c in b.children], ["c"])

    def test_metadata_copied_defensively(self):
        clock = FakeClock()
        meta = {"k": "v"}
        with SpanRecorder(clock=clock) as r:
            with r.span("op", metadata=meta) as s:
                pass
        meta["k"] = "changed"
        self.assertEqual(s.metadata, {"k": "v"})

    def test_add_metadata(self):
        clock = FakeClock()
        with SpanRecorder(clock=clock) as r:
            with r.span("op") as s:
                s.add_metadata(http_status=200)
                s.add_metadata(http_method="GET")
                s.add_metadata(http_status=201)  # overwrite
        self.assertEqual(s.metadata, {
            "http_status": 201,
            "http_method": "GET",
        })

    def test_to_dict_includes_metadata_when_present(self):
        clock = FakeClock()
        with SpanRecorder(clock=clock) as r:
            with r.span("op", metadata={"id": 42}):
                pass
        d = export_dict(SpanTree(r.root))
        self.assertEqual(d["metadata"], {"id": 42})

    def test_to_dict_omits_metadata_when_empty(self):
        clock = FakeClock()
        with SpanRecorder(clock=clock) as r:
            with r.span("op"):
                pass
        d = export_dict(SpanTree(r.root))
        self.assertNotIn("metadata", d)

    def test_to_dict_omits_children_when_empty(self):
        clock = FakeClock()
        with SpanRecorder(clock=clock) as r:
            with r.span("op"):
                pass
        d = export_dict(SpanTree(r.root))
        self.assertNotIn("children", d)

    def test_full_tree_dict(self):
        clock = FakeClock()
        with SpanRecorder(clock=clock) as r:
            with r.span("root", metadata={"env": "test"}):
                with r.span("child1"):
                    pass
                with r.span("child2", metadata={"tag": "x"}):
                    pass
        d = export_dict(SpanTree(r.root))
        expected = {
            "name": "root",
            "start": 1.0,
            "end": 6.0,
            "duration": 5.0,
            "metadata": {"env": "test"},
            "children": [
                {
                    "name": "child1",
                    "start": 2.0,
                    "end": 3.0,
                    "duration": 1.0,
                },
                {
                    "name": "child2",
                    "start": 4.0,
                    "end": 5.0,
                    "duration": 1.0,
                    "metadata": {"tag": "x"},
                },
            ],
        }
        self.assertEqual(d, expected)
        # Also ensure it's JSON-serializable since that's the export point.
        json.dumps(d)

    def test_open_span_to_dict_raises(self):
        clock = FakeClock()
        with SpanRecorder(clock=clock) as r:
            with r.span("op") as s:
                with self.assertRaises(ValueError):
                    s.to_dict()

    def test_span_tree_requires_closed_root(self):
        clock = FakeClock()
        r = SpanRecorder(clock=clock)
        with r.span("op") as s:
            with self.assertRaises(ValueError):
                SpanTree(s)

    def test_children_property_returns_copy(self):
        clock = FakeClock()
        with SpanRecorder(clock=clock) as r:
            with r.span("root") as root:
                with r.span("child"):
                    pass
        kids = root.children
        kids.clear()
        # Mutating the returned list must not affect the span.
        self.assertEqual(len(root.children), 1)

    def test_metadata_property_returns_copy(self):
        clock = FakeClock()
        with SpanRecorder(clock=clock) as r:
            with r.span("op", metadata={"k": 1}) as s:
                pass
        m = s.metadata
        m.clear()
        self.assertEqual(s.metadata, {"k": 1})

    def test_span_class_directly(self):
        clock = FakeClock()
        s = Span("direct", clock=clock)
        self.assertIsNone(s.duration)
        s._close(clock)
        self.assertEqual(s.duration, 1.0)
        # The span is now closed, so this should work.
        SpanTree(s).to_dict()

    def test_default_clock_is_monotonic(self):
        r = SpanRecorder()
        self.assertEqual(r._clock.__name__, "monotonic")


if __name__ == "__main__":
    unittest.main()
