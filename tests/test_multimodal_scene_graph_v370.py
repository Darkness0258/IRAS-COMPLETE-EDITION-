from __future__ import annotations

from iras.vision.scene_graph import build_scene_graph, stable_element_id


REGION = {"left": 100, "top": 50, "width": 1000, "height": 800}


def uia(label="Search", left=150):
    return {
        "source": "uia",
        "label": label,
        "name": label,
        "automation_id": "SearchBox" if label == "Search" else "",
        "role": "Edit",
        "enabled": True,
        "interactive": True,
        "rect": {"left": left, "top": 100, "width": 200, "height": 40},
    }


def vision(label="Search", left=150, confidence=0.88):
    return {
        "source": "omniparser",
        "label": label,
        "name": label,
        "automation_id": "",
        "role": "Edit",
        "enabled": True,
        "interactive": True,
        "confidence": confidence,
        "rect": {"left": left, "top": 100, "width": 200, "height": 40},
    }


def test_v370_stable_element_id_does_not_depend_on_list_index():
    a = uia("Search", 150)
    b = uia("Send", 700)

    first = build_scene_graph([a, b], [], region=REGION, capture_sha256="abc")
    second = build_scene_graph([b, a], [], region=REGION, capture_sha256="def")

    first_by_label = {item["label"]: item["element_id"] for item in first["elements"]}
    second_by_label = {item["label"]: item["element_id"] for item in second["elements"]}
    assert first_by_label == second_by_label
    assert first_by_label["Search"].startswith("uia:")


def test_v370_scene_graph_preserves_visual_only_webview_control():
    graph = build_scene_graph([], [vision("Darkness", 500)], region=REGION, capture_sha256="shot")

    assert graph["version"] == "3.7.0"
    assert graph["visual_only_count"] == 1
    element = graph["elements"][0]
    assert element["element_id"].startswith("vision:")
    assert element["confidence"] == 0.88
    assert element["provenance"]["backend"] == "omniparser"
    assert element["provenance"]["capture_sha256"] == "shot"


def test_v370_scene_graph_prefers_uia_when_visual_duplicate_overlaps():
    accessible = uia("Search")
    visual = vision("Search")
    graph = build_scene_graph([accessible], [visual], region=REGION, capture_sha256="shot")

    assert graph["element_count"] == 1
    assert graph["suppressed_visual_duplicates"] == 1
    element = graph["elements"][0]
    assert element["source"] == "uia"
    assert "omniparser" in element["sources"]
    assert element["visual_corrobation"] is True


def test_v370_duplicate_actionable_labels_are_marked_ambiguous():
    graph = build_scene_graph(
        [],
        [vision("Open", 200, 0.91), vision("Open", 700, 0.91)],
        region=REGION,
        capture_sha256="shot",
    )

    assert graph["ambiguous_actionable_count"] == 2
    assert all(item["ambiguous_label"] is True for item in graph["elements"])


def test_v370_small_geometry_jitter_keeps_stable_id_inside_bucket():
    base = vision("Darkness", 500)
    jittered = vision("Darkness", 503)

    assert stable_element_id(base, region=REGION) == stable_element_id(jittered, region=REGION)
