import pytest

from protolab import tool_schemas_for, TOOLS


def test_schemas_for_known_tools():
    schemas = tool_schemas_for(["boltz_predict"])
    assert schemas[0]["name"] == "boltz_predict"
    assert schemas[0]["type"] == "function"


def test_empty_list_is_fine():
    assert tool_schemas_for([]) == []


def test_unknown_tool_raises():
    with pytest.raises(KeyError, match="unknown tool"):
        tool_schemas_for(["nope"])


def test_stub_runs_return_a_note():
    assert "note" in TOOLS["boltz_predict"].run(sequence="MKV...")
