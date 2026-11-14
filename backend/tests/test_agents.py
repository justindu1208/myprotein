from conftest import PROTOCOLS_DIR
from protolab import ProjectRecord, load_protocol, build_instructions, run_step


class FakeClient:
    """Records the last responses.create call so we can assert on it."""

    def __init__(self):
        self.last = None
        self.responses = self

    def create(self, **kwargs):
        self.last = kwargs
        return {"output_text": "ok"}


def _setup():
    protocol = load_protocol(PROTOCOLS_DIR / "variant-screening.json")
    record = ProjectRecord.from_protocol(protocol)
    record.write("question", {"question": "Q"})
    return protocol, record


def test_build_instructions_has_role_and_record():
    protocol, record = _setup()
    text = build_instructions(protocol.step("hypothesis"), record)
    assert protocol.step("hypothesis").role.split(".")[0] in text
    assert "question" in text   # hypothesis reads question


def test_run_step_passes_stack_role_and_tools():
    protocol, record = _setup()
    client = FakeClient()
    run_step(client, "stack:test", protocol, "predict", record, "go")
    assert client.last["model"] == "stack:test"
    # Predict's single tool is boltz_predict.
    assert [t["name"] for t in client.last["tools"]] == ["boltz_predict"]
    assert "Execute the plan" in client.last["instructions"]
