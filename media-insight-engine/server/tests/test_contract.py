"""The API must keep matching docs/openapi.yaml (the contract handed to the frontend)."""
from pathlib import Path

import yaml

from app.main import app

METHODS = {"get", "post", "put", "patch", "delete"}


def operations(spec: dict) -> set[tuple[str, str]]:
    return {(m.upper(), path) for path, item in spec["paths"].items() for m in item if m in METHODS}


def test_paths_match_contract():
    contract = yaml.safe_load((Path(__file__).parent.parent / "docs" / "openapi.yaml").read_text(encoding="utf-8"))
    assert operations(app.openapi()) == operations(contract)


def test_response_schemas_have_contract_fields():
    contract = yaml.safe_load((Path(__file__).parent.parent / "docs" / "openapi.yaml").read_text(encoding="utf-8"))
    ours = app.openapi()["components"]["schemas"]
    for name in ("Collection", "SyncLog", "SourceSummary", "Citation", "AskResponse", "QuestionBank", "BankRun",
                 "ReportItem", "Segment", "KeyQuote", "Chapter"):
        want = set(contract["components"]["schemas"][name].get("required", []))
        assert want <= set(ours[name]["properties"]), (name, want - set(ours[name]["properties"]))
