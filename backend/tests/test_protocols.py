import pytest

from conftest import PROTOCOLS_DIR
from protolab import load_protocol, load_protocols


def test_variant_screening_shape():
    protocol = load_protocol(PROTOCOLS_DIR / "variant-screening.json")
    assert protocol.step_ids == [
        "question", "literature", "hypothesis", "design", "predict", "analyse",
    ]
    assert protocol.step("predict").tools == ["boltz_predict"]
    assert protocol.step("question").reads == []


def test_load_all_protocols_keyed_by_id():
    protocols = load_protocols(PROTOCOLS_DIR)
    assert "variant-screening" in protocols
    assert "literature-review" in protocols


def test_reads_must_reference_an_earlier_step(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"id":"x","name":"X","steps":['
        '{"id":"a","name":"A","role":"r","output":[],"reads":["z"],"tools":[]}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not an earlier step"):
        load_protocol(bad)
