from conftest import PROTOCOLS_DIR
from protolab import ProjectRecord, load_protocol


def _record():
    protocol = load_protocol(PROTOCOLS_DIR / "variant-screening.json")
    return protocol, ProjectRecord.from_protocol(protocol)


def test_write_and_read():
    _, record = _record()
    record.write("question", {"question": "Q1"})
    entry = record.read("question")
    assert entry is not None
    assert entry.fields["question"] == "Q1"


def test_changing_upstream_marks_dependents_stale():
    _, record = _record()
    record.write("question", {"question": "Q1"})
    record.write("hypothesis", {"hypothesis": "H1"})   # hypothesis reads question
    assert not record.is_stale("hypothesis")

    record.write("question", {"question": "Q2"})       # change upstream
    assert record.is_stale("hypothesis")


def test_staleness_cascades():
    _, record = _record()
    for sid, fields in [
        ("question", {"question": "Q"}),
        ("hypothesis", {"hypothesis": "H"}),
        ("design", {"plan": "P"}),
        ("predict", {"results": "R"}),
    ]:
        record.write(sid, fields)
    assert not record.is_stale("predict")

    record.write("hypothesis", {"hypothesis": "H2"})   # design reads hypothesis, predict reads design
    assert record.is_stale("design")
    assert record.is_stale("predict")


def test_as_context_includes_only_reads_and_flags_stale():
    _, record = _record()
    record.write("question", {"question": "Q"})
    record.write("literature", {"evidence_notes": "N"})
    record.write("hypothesis", {"hypothesis": "H"})
    record.write("question", {"question": "Q2"})       # makes hypothesis stale

    # Design reads question + hypothesis, not literature.
    context = record.as_context(reads=["question", "hypothesis"])
    assert "question" in context
    assert "hypothesis" in context
    assert "evidence_notes" not in context
    assert "OUT OF DATE" in context   # hypothesis is stale
