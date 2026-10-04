"""Contrato core/titles.py: título por rid_keys del plugin + franja superior."""
from jev_mcp.core.titles import find_title, has_any_title

RIDS = ("contact_name", "title")


def _cand(id, text="", rid="", editable=False, top=None):
    c = {"id": id, "text": text, "desc": "", "resource_id": rid,
         "editable": editable, "label": text}
    c["bounds"] = [0, top, 720, top + 100] if top is not None else [0, 0, 0, 0]
    return c


def test_find_title_rid():
    st = {"screen_height": 1600, "candidates": [
        _cand("n_1", text="Ana", rid="x:id/contact_name"),
        _cand("n_2", text="Buscar", rid="x:id/search"),
    ]}
    assert find_title(st, "Ana", rid_keys=RIDS)["id"] == "n_1"
    assert find_title(st, "Carlos", rid_keys=RIDS) is None


def test_find_title_top_fallback():
    st = {"screen_height": 1600, "candidates": [
        _cand("n_1", text="Ana", rid="x:id/foo", top=100),
        _cand("n_2", text="Ana", rid="x:id/bar", top=900),
    ]}
    assert find_title(st, "Ana", rid_keys=RIDS)["id"] == "n_1"


def test_skips_editable_and_has_any():
    st = {"screen_height": 1600, "candidates": [
        _cand("n_1", text="Ana", rid="x:id/contact_name", editable=True),
    ]}
    assert find_title(st, "Ana", rid_keys=RIDS) is None
    assert not has_any_title(st, rid_keys=RIDS)
    st2 = {"screen_height": 1600, "candidates": [
        _cand("n_1", text="Otra vista", rid="x:id/title"),
    ]}
    assert has_any_title(st2, rid_keys=RIDS)
