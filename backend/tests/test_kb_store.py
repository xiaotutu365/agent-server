import pytest

import kb.config as cfg
from kb import store


def test_validate_kb_id_ok():
    assert cfg.validate_kb_id("policy-1") == "policy-1"


@pytest.mark.parametrize("bad", ["", "../evil", "a b", "x" * 65])
def test_validate_kb_id_rejects(bad):
    with pytest.raises(ValueError):
        cfg.validate_kb_id(bad)


def test_create_list_drop():
    r = store.create_kb("unit_test")
    assert r["status"] in ("created", "exists")
    assert "unit_test" in [k["kb_id"] for k in store.list_kbs()]

    d = store.drop_kb("unit_test")
    assert d["status"] == "deleted"
    assert "unit_test" not in [k["kb_id"] for k in store.list_kbs()]
