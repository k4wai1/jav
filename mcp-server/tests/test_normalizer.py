"""Tests del normalizer: sintético + fixture real de WhatsApp (174 nodos)."""
import json
import os

from jev_mcp.ui_normalizer import MAX_CANDIDATES, format_state, normalize

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "wa_home.json")


def test_drops_decor_and_mute_containers():
    dump = {"package": "p", "snapshot_id": 1, "nodes": [
        {"id": "n_0", "text": None, "content_desc": None, "class": "android.view.View",
         "resource_id": "android:id/statusBarBackground", "bounds": [0, 0, 1, 1],
         "clickable": False, "editable": False, "scrollable": False,
         "enabled": True, "checked": False, "focused": False, "visible": True, "children": []},
        {"id": "n_1", "text": None, "content_desc": None, "class": "android.widget.LinearLayout",
         "resource_id": None, "bounds": [0, 0, 1, 1],
         "clickable": False, "editable": False, "scrollable": False,
         "enabled": True, "checked": False, "focused": False, "visible": True, "children": []},
        {"id": "n_2", "text": "Hola", "content_desc": None, "class": "android.widget.TextView",
         "resource_id": None, "bounds": [0, 0, 1, 1],
         "clickable": False, "editable": False, "scrollable": False,
         "enabled": True, "checked": False, "focused": False, "visible": True, "children": []},
    ]}
    st = normalize(dump)
    assert [c.id for c in st.candidates] == ["n_2"]
    assert st.raw_count == 3


def test_compact_format():
    dump = {"package": "p", "snapshot_id": 1, "nodes": [
        {"id": "n_0", "text": "Buscar", "content_desc": None,
         "class": "android.widget.EditText", "resource_id": "x:id/s",
         "bounds": [0, 0, 1, 1], "clickable": True, "editable": True,
         "scrollable": False, "enabled": True, "checked": False,
         "focused": False, "visible": True, "children": []},
    ]}
    st = normalize(dump)
    assert st.compact_lines() == ['[n_0] EditText "Buscar"']


def test_wa_home_fixture():
    with open(FIX, encoding="utf-8") as f:
        dump = json.load(f)
    assert dump["package"] == "com.whatsapp"
    st = normalize(dump)
    assert len(st.candidates) <= MAX_CANDIDATES
    assert st.raw_count == len(dump["nodes"])
    assert st.snapshot_id == dump["snapshot_id"]
    # sin decoración y ordenado por tier (editable > clickable-con-texto > resto)
    assert not any("Background" in (c.resource_id or "") for c in st.candidates)
    tiers = [0 if c.editable else 1 if (c.clickable and (c.text or c.desc)) else 2
             for c in st.candidates]
    assert tiers == sorted(tiers)
    assert any("Buscar" in (c.text or c.desc) for c in st.candidates)
    print("\n" + format_state(st)[:1200])


def test_poda_cadena_documentada():
    # Cadena real: 500 raw (extractor) → 254 (normalizer vigente)
    # ⊂ 255 Choice (254 + NONE, capacidad Jev). Tope vigente = capacidad
    # (contrato generic-dual-tier §4: 0..253 + NONE = 255 Choice).
    assert MAX_CANDIDATES == 254
    assert MAX_CANDIDATES <= 254
    dump = {"package": "p", "snapshot_id": 1, "nodes": [
        {"id": f"n_{i}", "text": f"item {i}", "content_desc": None,
         "class": "android.widget.Button", "resource_id": f"x:id/b{i}",
         "bounds": [0, 0, 1, 1], "clickable": True, "editable": False,
         "scrollable": False, "enabled": True, "checked": False,
         "focused": False, "visible": True, "children": []}
        for i in range(300)
    ]}
    st = normalize(dump)
    assert len(st.candidates) == MAX_CANDIDATES
    assert st.raw_count == 300
