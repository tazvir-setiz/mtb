import json
from pathlib import Path
DATA = Path(__file__).parent / "data" / "guard_benchmark_v1.json"
def load_cases(): return json.loads(DATA.read_text(encoding="utf-8"))
def test_count_and_ids():
    c=load_cases(); assert len(c)==150; assert len({x["id"] for x in c})==150
def test_schema():
    actions={"SEND","DROP","REVIEW"}
    labels={"OK","REWRITE","ABUSE","HATE","THREAT","PORN","SPAM","INJECTION","REVIEW"}
    for x in load_cases():
        assert x["text"].strip()
        assert x["expected_action"] in actions
        assert x["expected_label"] in labels
        assert isinstance(x["protected_meaning"],list)
        assert isinstance(x["removable_meaning"],list)
        assert isinstance(x["ambiguities"],list)
def test_rewrites_have_content():
    for x in load_cases():
        if x["expected_action"]=="SEND" and x["expected_label"]=="REWRITE":
            assert x["protected_meaning"], x["id"]
            assert x["example_rewrite"], x["id"]
