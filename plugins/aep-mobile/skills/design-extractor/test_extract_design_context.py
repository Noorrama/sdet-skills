#!/usr/bin/env python3
"""Unit tests for extract_design_context helpers."""

import unittest
import os

from extract_design_context import (
    assess_element_id_quality,
    attach_validations,
    build_element_id_quality_report,
    build_screens,
    build_ui_flow,
    classify_contextual_annotation,
    collect_flow_element_ids,
    collect_flow_element_instances,
    connector_destination_node_ids,
    connector_ui_flow_parity_gaps,
    derive_frame_qualifier,
    find_intentional_canonical_dupes,
    infer_app,
    is_mockup_trigger_node,
    looks_like_rule,
    merge_semantic_elements,
    normalize_element_label,
    pick_state_label_text,
    plan_screen_groups,
    resolve_screen_for_connector_endpoint,
    resolve_trigger_node_id,
    connector_roles_for_nodes,
    extract_elements,
    find_duplicate_element_ids,
    find_node_in_subtree,
    select_flow_nodes_for_screen,
)
from recover_design_context import apply_refinement, apply_screen_collapse


class TestAssessElementIdQuality(unittest.TestCase):
    def test_accepts_container_suffix(self):
        result = assess_element_id_quality("MPS.group_order_type_container")
        self.assertEqual(result["quality"], "GOOD")

    def test_accepts_img_suffix(self):
        result = assess_element_id_quality("LANDING.hero_banner_img")
        self.assertEqual(result["quality"], "GOOD")

    def test_accepts_image_suffix(self):
        result = assess_element_id_quality("LANDING.hero_banner_image")
        self.assertEqual(result["quality"], "GOOD")

    def test_rejects_overlong_token(self):
        result = assess_element_id_quality(
            "MPS.pagecontrolscrollpagination_st_nd_rd_th_btn"
        )
        self.assertEqual(result["quality"], "BAD")


class TestCollectFlowElementIds(unittest.TestCase):
    def test_includes_incoming_only_element(self):
        pp = {
            "edges": [
                {"from": "node-trigger", "to": "node-destination"},
            ],
            "original_edges": [],
        }
        screens = [
            {
                "screen_id": "LANDING",
                "elements": [
                    {
                        "source_ref": "node-trigger",
                        "element_id": "LANDING.start_order_btn",
                    },
                    {
                        "source_ref": "node-destination",
                        "element_id": "MPS.offer_bar_voucher_merchant_container",
                    },
                ],
            },
        ]
        ui_flow = [
            {
                "trigger_element_id": "LANDING.start_order_btn",
            },
        ]

        result = collect_flow_element_ids(pp, screens, ui_flow)

        self.assertEqual(
            result,
            [
                "LANDING.start_order_btn",
                "MPS.offer_bar_voucher_merchant_container",
            ],
        )

    def test_returns_sorted_deterministic_union(self):
        pp = {
            "edges": [
                {"from": "node-z", "to": "node-a"},
            ],
            "original_edges": [],
        }
        screens = [
            {
                "screen_id": "SCREEN",
                "elements": [
                    {
                        "source_ref": "node-z",
                        "element_id": "SCREEN.z_trigger_btn",
                    },
                    {
                        "source_ref": "node-a",
                        "element_id": "SCREEN.a_destination_container",
                    },
                ],
            },
        ]
        ui_flow = [
            {"trigger_element_id": "SCREEN.z_trigger_btn"},
            {"trigger_element_id": "SCREEN.aaa_trigger_btn"},
        ]

        result = collect_flow_element_ids(pp, screens, ui_flow)

        self.assertEqual(
            result,
            [
                "SCREEN.a_destination_container",
                "SCREEN.aaa_trigger_btn",
                "SCREEN.z_trigger_btn",
            ],
        )


class TestFindNodeInSubtree(unittest.TestCase):
    def test_finds_nested_frame_three_levels_deep(self):
        tree = {
            "id": "screen-1",
            "children": [
                {
                    "id": "level-1",
                    "children": [
                        {
                            "id": "level-2",
                            "children": [
                                {"id": "target", "name": "Deep link", "type": "TEXT"},
                            ],
                        },
                    ],
                },
            ],
        }
        found = find_node_in_subtree(tree, "target")
        self.assertIsNotNone(found)
        self.assertEqual(found["name"], "Deep link")

    def test_returns_none_when_missing(self):
        tree = {"id": "screen-1", "children": [{"id": "other"}]}
        self.assertIsNone(find_node_in_subtree(tree, "missing"))


class TestSelectFlowNodesForScreen(unittest.TestCase):
    def test_drops_incoming_only_ancestor_when_descendant_has_outgoing(self):
        screen_id = "screen-landing"
        candidate_ids = ["ancestor", "descendant", "navbar"]
        pp = {
            "index": {
                "ancestor": {"parent_id": screen_id},
                "descendant": {"parent_id": "ancestor"},
                "navbar": {"parent_id": screen_id},
            },
            "edges": [
                {"from": "external", "to": "ancestor"},
                {"from": "descendant", "to": "other-screen"},
            ],
            "original_edges": [],
        }
        roles = connector_roles_for_nodes(pp, set(candidate_ids))
        result = select_flow_nodes_for_screen(
            screen_id, candidate_ids, pp, roles
        )
        self.assertEqual(result, ["descendant", "navbar"])
        self.assertNotIn("ancestor", result)

    def test_keeps_incoming_only_connector_destination(self):
        screen_id = "screen-landing"
        candidate_ids = ["ancestor", "descendant", "navbar"]
        pp = {
            "index": {
                "ancestor": {"parent_id": screen_id},
                "descendant": {"parent_id": "ancestor"},
                "navbar": {"parent_id": screen_id},
            },
            "edges": [
                {"from": "external", "to": "ancestor"},
                {"from": "descendant", "to": "other-screen"},
            ],
            "original_edges": [],
        }
        roles = connector_roles_for_nodes(pp, set(candidate_ids))
        result = select_flow_nodes_for_screen(
            screen_id,
            candidate_ids,
            pp,
            roles,
            connector_destinations={"ancestor"},
        )
        self.assertIn("ancestor", result)
        self.assertIn("descendant", result)


class TestMechanicalHeuristics(unittest.TestCase):
    def test_is_mockup_trigger_node_screenshot_rectangle(self):
        index = {
            "shot": {"type": "RECTANGLE", "name": "Screenshot"},
        }
        self.assertTrue(is_mockup_trigger_node(index, "shot"))

    def test_resolve_trigger_node_id_remaps_to_parent_instance(self):
        index = {
            "shot": {"type": "RECTANGLE", "name": "Screenshot", "parent_id": "card"},
            "card": {"type": "INSTANCE", "name": "social/16/ic_add_contact", "parent_id": "screen"},
            "screen": {"type": "FRAME", "name": "MPS"},
        }
        resolved, remapped = resolve_trigger_node_id(
            "shot", "screen", index, {"shot", "invite"},
        )
        self.assertTrue(remapped)
        self.assertEqual(resolved, "card")

    def test_resolve_screen_for_connector_endpoint_uses_snapped_screen_id(self):
        edge = {
            "from": "screen-a",
            "to": "screen-b",
            "original_from": "section-1",
            "original_to": "node-b",
        }
        screen_ids = {"screen-a", "screen-b"}
        index = {"node-b": {"parent_id": "screen-b"}}
        result = resolve_screen_for_connector_endpoint(
            edge, "from", screen_ids, index, {}, {},
        )
        self.assertEqual(result, "screen-a")

    def test_infer_app_gofood_defaults_to_consumer(self):
        self.assertEqual(
            infer_app("GoFood Group Order", "MVP - Group Order"),
            "gofood-consumer",
        )

    def test_connector_ui_flow_parity_gaps_reports_missing(self):
        pp = {
            "edges": [{"id": "c1"}, {"id": "c2"}],
            "original_edges": [],
        }
        ui_flow = [{"edge_source": "CONNECTOR", "source_ref": "c1"}]
        gaps = connector_ui_flow_parity_gaps(pp, ui_flow, {"summary": {"connectors_total": 2}})
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["severity"], "WARN")
        self.assertIn("c2", gaps[0]["reason"])

    def test_build_ui_flow_includes_screen_edge_with_section_start(self):
        pp = {
            "screens": [
                {"id": "screen-a", "name": "A"},
                {"id": "screen-b", "name": "B"},
            ],
            "entry_points": [{"id": "screen-a", "reason": "CONTEXT"}],
            "index": {
                "section": {"parent_id": None},
                "node-b": {"parent_id": "screen-b"},
            },
            "edges": [{
                "id": "conn-1",
                "from": "screen-a",
                "to": "screen-b",
                "original_from": "section",
                "original_to": "node-b",
                "snapped": True,
                "label": "Open WA",
            }],
            "original_edges": [],
            "node_id_to_screen": {},
            "contextual_node_id_to_screen": {},
        }
        screens = [
            {
                "screen_id": "A",
                "source_ref": "screen-a",
                "elements": [],
            },
            {
                "screen_id": "B",
                "source_ref": "screen-b",
                "elements": [],
            },
        ]
        ui_flow, remaps = build_ui_flow(pp, screens)
        connector_edges = [
            e for e in ui_flow if e.get("navigation_kind") == "NAVIGATE"
        ]
        self.assertEqual(len(connector_edges), 1)
        self.assertEqual(connector_edges[0]["source_ref"], "conn-1")
        self.assertEqual(connector_edges[0]["condition"], "Open WA")


class TestExtractElementsInventory(unittest.TestCase):
    def _landing_like_tree(self):
        return {
            "id": "screen-landing",
            "children": [
                {
                    "id": "navbar",
                    "name": "Navbar",
                    "type": "INSTANCE",
                    "children": [],
                },
                {
                    "id": "ancestor",
                    "name": "Billing section",
                    "type": "FRAME",
                    "children": [
                        {
                            "id": "nested-link",
                            "name": "Learn more link",
                            "type": "TEXT",
                            "children": [],
                        },
                    ],
                },
                {
                    "id": "cta",
                    "name": "Start order",
                    "type": "INSTANCE",
                    "children": [],
                },
            ],
        }

    def test_extracts_nested_flow_nodes_with_dedup(self):
        screen_node = self._landing_like_tree()
        text_cache = {"nested-link": "Learn more about billing methods"}
        flow_ids = ["navbar", "ancestor", "nested-link", "cta"]
        pp = {
            "index": {
                "navbar": {"parent_id": "screen-landing"},
                "ancestor": {"parent_id": "screen-landing"},
                "nested-link": {"parent_id": "ancestor"},
                "cta": {"parent_id": "screen-landing"},
            },
            "edges": [
                {"from": "external", "to": "ancestor"},
                {"from": "nested-link", "to": "billing-screen"},
            ],
            "original_edges": [],
        }

        elements, missing = extract_elements(
            screen_node,
            "LANDING",
            text_cache,
            flow_ids,
            pp,
        )

        self.assertEqual(missing, [])
        self.assertEqual(len(elements), 3)
        source_refs = {e["source_ref"] for e in elements}
        self.assertEqual(source_refs, {"navbar", "nested-link", "cta"})
        self.assertNotIn("ancestor", source_refs)

        link = next(e for e in elements if e["source_ref"] == "nested-link")
        self.assertIn("Learn more about billing methods", link["label"])

    def test_fallback_direct_children_without_inventory(self):
        screen_node = {
            "id": "screen-1",
            "children": [
                {"id": "child-a", "name": "Button A", "type": "INSTANCE"},
                {
                    "id": "child-b",
                    "name": "Wrapper",
                    "type": "FRAME",
                    "children": [
                        {"id": "nested", "name": "Hidden link", "type": "TEXT"},
                    ],
                },
            ],
        }
        elements, missing = extract_elements(screen_node, "SCREEN", {})
        self.assertEqual(missing, [])
        self.assertEqual(len(elements), 2)
        self.assertEqual(
            {e["source_ref"] for e in elements},
            {"child-a", "child-b"},
        )


class TestBuildScreensFallback(unittest.TestCase):
    def test_no_inventory_uses_direct_children(self):
        pp = {
            "screens": [{"id": "screen-1", "name": "Landing"}],
            "screen_context": {},
            "text_cache": {},
            "node_tree": {
                "id": "root",
                "children": [
                    {
                        "id": "screen-1",
                        "name": "Landing",
                        "children": [
                            {"id": "btn", "name": "Go", "type": "INSTANCE"},
                        ],
                    },
                ],
            },
            "index": {},
        }
        screens, gaps, _ = build_screens(pp, None, screen_flow_ids={}, use_inventory=False)
        self.assertEqual(len(screens), 1)
        self.assertEqual(len(screens[0]["elements"]), 1)
        self.assertEqual(screens[0]["elements"][0]["source_ref"], "btn")
        self.assertEqual(gaps, [])


class TestGlobalSeenPurposes(unittest.TestCase):
    def test_shares_canonical_element_id_across_collapsed_state_frames(self):
        sku_node = {
            "id": "sku-a",
            "name": "Merchant Profile / SKU / SKU List v3",
            "type": "INSTANCE",
            "children": [],
        }
        pp = {
            "screens": [
                {"id": "frame-a", "name": "MPS"},
                {"id": "frame-b", "name": "MPS"},
            ],
            "screen_context": {},
            "text_cache": {},
            "node_tree": {
                "id": "root",
                "children": [
                    {"id": "frame-a", "name": "MPS", "children": [sku_node]},
                    {
                        "id": "frame-b",
                        "name": "MPS",
                        "children": [
                            {
                                **sku_node,
                                "id": "sku-b",
                            }
                        ],
                    },
                ],
            },
            "index": {},
        }
        screen_flow_ids = {
            "frame-a": ["sku-a"],
            "frame-b": ["sku-b"],
        }
        screens, gaps, collapse_map = build_screens(
            pp,
            None,
            screen_flow_ids=screen_flow_ids,
            use_inventory=True,
        )
        self.assertEqual(gaps, [])
        self.assertEqual(len(screens), 1)
        self.assertEqual(len(screens[0]["source_refs"]), 2)
        element_ids = [el["element_id"] for el in screens[0]["elements"]]
        self.assertEqual(len(element_ids), 2)
        self.assertEqual(len(set(element_ids)), 1)
        self.assertIn("MPS.merchant_profile_sku_sku_list", element_ids)
        self.assertEqual(find_duplicate_element_ids(screens), [])
        self.assertEqual(len(find_intentional_canonical_dupes(screens)), 1)
        self.assertEqual(len(collapse_map["auto_collapsed"]), 1)


class TestDuplicateDetection(unittest.TestCase):
    def test_find_duplicate_element_ids_flags_true_collisions(self):
        screens = [
            {
                "screen_id": "MPS",
                "elements": [
                    {"element_id": "MPS.bundle_sku_list", "source_ref": "a", "label": "A"},
                    {"element_id": "MPS.bundle_sku_list", "source_ref": "b", "label": "B"},
                ],
            }
        ]
        duplicates = find_duplicate_element_ids(screens)
        self.assertEqual(len(duplicates), 1)
        self.assertEqual(duplicates[0]["source_refs"], ["a", "b"])

    def test_allows_intentional_canonical_dupes(self):
        screens = [
            {
                "screen_id": "LANDING",
                "elements": [
                    {
                        "element_id": "LANDING.join_group_order_btn",
                        "source_ref": "a",
                        "label": "Join group order",
                        "states_represented": ["Variant 1"],
                    },
                    {
                        "element_id": "LANDING.join_group_order_btn",
                        "source_ref": "b",
                        "label": "Join group order",
                        "states_represented": ["Variant 2"],
                    },
                ],
            }
        ]
        self.assertEqual(find_duplicate_element_ids(screens), [])
        intentional = find_intentional_canonical_dupes(screens)
        self.assertEqual(len(intentional), 1)

    def test_quality_report_flags_duplicate_instances(self):
        instances = [
            {
                "screen_id": "MPS",
                "source_ref": "a",
                "element_id": "MPS.bundle_sku_list",
            },
            {
                "screen_id": "MPS",
                "source_ref": "b",
                "element_id": "MPS.bundle_sku_list",
            },
        ]
        report = build_element_id_quality_report(instances)
        qualities = {row["source_ref"]: row["quality"] for row in report}
        self.assertEqual(qualities["a"], "DUPLICATE")
        self.assertEqual(qualities["b"], "DUPLICATE")


class TestApplyRefinementGuardrails(unittest.TestCase):
    def test_skips_ambiguous_rename_without_source_ref(self):
        context = {
            "screens": [
                {
                    "screen_id": "MPS",
                    "source_ref": "frame-a",
                    "elements": [
                        {
                            "element_id": "MPS.merchant_profile_sku_sku_list",
                            "source_ref": "sku-a",
                        }
                    ],
                },
                {
                    "screen_id": "MPS",
                    "source_ref": "frame-b",
                    "elements": [
                        {
                            "element_id": "MPS.merchant_profile_sku_sku_list",
                            "source_ref": "sku-b",
                        }
                    ],
                },
            ],
            "ui_flow": [],
        }
        status, detail = apply_refinement(
            context,
            {
                "screen_id": "MPS",
                "old_id": "MPS.merchant_profile_sku_sku_list",
                "suggested_id": "MPS.bundle_sku_list",
                "confidence": "high",
            },
        )
        self.assertEqual(status, "skipped_ambiguous")
        self.assertIn("source_ref", detail)

    def test_applies_rename_with_source_ref_and_scoped_ui_flow(self):
        context = {
            "screens": [
                {
                    "screen_id": "MPS",
                    "source_ref": "frame-a",
                    "elements": [
                        {
                            "element_id": "MPS.merchant_profile_sku_sku_list",
                            "source_ref": "sku-a",
                        }
                    ],
                },
                {
                    "screen_id": "MPS",
                    "source_ref": "frame-b",
                    "elements": [
                        {
                            "element_id": "MPS.merchant_profile_sku_sku_list_2",
                            "source_ref": "sku-b",
                        }
                    ],
                },
            ],
            "ui_flow": [
                {
                    "from_screen_id": "MPS",
                    "from_source_ref": "frame-a",
                    "trigger_element_id": "MPS.merchant_profile_sku_sku_list",
                },
                {
                    "from_screen_id": "MPS",
                    "from_source_ref": "frame-b",
                    "trigger_element_id": "MPS.merchant_profile_sku_sku_list_2",
                },
            ],
        }
        status, _ = apply_refinement(
            context,
            {
                "screen_id": "MPS",
                "old_id": "MPS.merchant_profile_sku_sku_list",
                "suggested_id": "MPS.bundle_sku_list",
                "source_ref": "sku-a",
                "confidence": "high",
            },
        )
        self.assertEqual(status, "applied")
        self.assertEqual(
            context["screens"][0]["elements"][0]["element_id"],
            "MPS.bundle_sku_list",
        )
        self.assertEqual(
            context["screens"][1]["elements"][0]["element_id"],
            "MPS.merchant_profile_sku_sku_list_2",
        )
        self.assertEqual(
            context["ui_flow"][0]["trigger_element_id"],
            "MPS.bundle_sku_list",
        )
        self.assertEqual(
            context["ui_flow"][1]["trigger_element_id"],
            "MPS.merchant_profile_sku_sku_list_2",
        )

    def test_applies_rename_using_trigger_source_ref(self):
        context = {
            "screens": [
                {
                    "screen_id": "LANDING",
                    "source_ref": "frame-a",
                    "source_refs": ["frame-a", "frame-b"],
                    "elements": [
                        {
                            "element_id": "LANDING.join_group_order_btn",
                            "source_ref": "btn-a",
                        },
                        {
                            "element_id": "LANDING.join_group_order_btn",
                            "source_ref": "btn-b",
                        },
                    ],
                },
            ],
            "ui_flow": [
                {
                    "from_screen_id": "LANDING",
                    "from_source_ref": "frame-a",
                    "trigger_element_id": "LANDING.join_group_order_btn",
                    "trigger_source_ref": "btn-a",
                },
                {
                    "from_screen_id": "LANDING",
                    "from_source_ref": "frame-b",
                    "trigger_element_id": "LANDING.join_group_order_btn",
                    "trigger_source_ref": "btn-b",
                },
            ],
        }
        status, _ = apply_refinement(
            context,
            {
                "screen_id": "LANDING",
                "old_id": "LANDING.join_group_order_btn",
                "suggested_id": "LANDING.start_group_order_btn",
                "source_ref": "btn-a",
                "confidence": "high",
            },
        )
        self.assertEqual(status, "applied")
        self.assertEqual(
            context["ui_flow"][0]["trigger_element_id"],
            "LANDING.start_group_order_btn",
        )
        self.assertEqual(
            context["ui_flow"][1]["trigger_element_id"],
            "LANDING.join_group_order_btn",
        )
        self.assertEqual(context["ui_flow"][0]["trigger_source_ref"], "btn-a")


class TestContextualEnrichment(unittest.TestCase):
    _SCREEN_GEOM = {"abs_x": 100, "abs_y": 500, "width": 400, "height": 800}

    def test_classify_state_label(self):
        kind = classify_contextual_annotation(
            {"name": "File management/Driver/Screen label", "abs_x": 100, "abs_y": 400, "width": 300, "height": 40},
            "GO - Host item added New screen",
            self._SCREEN_GEOM,
        )
        self.assertEqual(kind, "STATE_LABEL")

    def test_classify_validation_note(self):
        kind = classify_contextual_annotation(
            {"name": "Note", "abs_x": 0, "abs_y": 0, "width": 100, "height": 40},
            "Unable to add if the discounted SKU is sold out",
            self._SCREEN_GEOM,
        )
        self.assertEqual(kind, "VALIDATION_NOTE")

    def test_classify_lane_banner(self):
        kind = classify_contextual_annotation(
            {"name": "Swim lane header", "abs_x": 100, "abs_y": 200, "width": 380, "height": 30},
            "Host - Pre-Booking Experience [Everyone pays for their items]",
            self._SCREEN_GEOM,
        )
        self.assertEqual(kind, "LANE_BANNER")

    def test_looks_like_rule_rejects_short_nav_tokens(self):
        self.assertFalse(looks_like_rule("Changes"))
        self.assertFalse(looks_like_rule("New screen"))
        self.assertTrue(looks_like_rule("Unable to add if the discounted SKU is sold out"))

    def test_pick_state_label_prefers_above_frame(self):
        ctx_infos = [
            {"id": "far", "name": "File management/Driver/Screen label", "abs_x": 500, "abs_y": 100, "width": 100, "height": 30},
            {"id": "near", "name": "File management/Driver/Screen label", "abs_x": 120, "abs_y": 420, "width": 200, "height": 30},
        ]
        text_cache = {"far": "Far label", "near": "Checkout Changes"}
        label = pick_state_label_text(ctx_infos, text_cache, self._SCREEN_GEOM)
        self.assertEqual(label, "Checkout Changes")

    def test_derive_frame_qualifier_priority_ladder(self):
        self.assertEqual(
            derive_frame_qualifier("MPS / EN", "Screen label text"),
            "Screen label text",
        )
        self.assertEqual(derive_frame_qualifier("MPS / EN", None), "EN")
        self.assertEqual(derive_frame_qualifier("Group order - Loading", None), "Loading")
        self.assertEqual(derive_frame_qualifier("Shimmer", None), "Shimmer")

    def test_build_screens_populates_screen_states_from_labels(self):
        pp = {
            "screens": [
                {
                    "id": "frame-a",
                    "name": "Shared cart",
                    "abs_x": 100,
                    "abs_y": 500,
                    "width": 400,
                    "height": 800,
                    "contextual_informations": [
                        {
                            "id": "label-a",
                            "name": "File management/Driver/Screen label",
                            "abs_x": 120,
                            "abs_y": 420,
                            "width": 200,
                            "height": 30,
                        },
                    ],
                },
                {
                    "id": "frame-b",
                    "name": "Shared cart",
                    "abs_x": 600,
                    "abs_y": 500,
                    "width": 400,
                    "height": 800,
                    "contextual_informations": [
                        {
                            "id": "label-b",
                            "name": "File management/Driver/Screen label",
                            "abs_x": 620,
                            "abs_y": 420,
                            "width": 200,
                            "height": 30,
                        },
                    ],
                },
            ],
            "screen_context": {},
            "text_cache": {
                "label-a": "GO - Host item added New screen",
                "label-b": "GO - Host item added New screen",
            },
            "node_tree": {
                "id": "root",
                "children": [
                    {"id": "frame-a", "name": "Shared cart", "children": []},
                    {"id": "frame-b", "name": "Shared cart", "children": []},
                ],
            },
            "index": {},
        }
        screens, _, collapse_map = build_screens(pp, None, screen_flow_ids={}, use_inventory=False)
        self.assertEqual(len(screens), 1)
        self.assertEqual(len(screens[0]["source_refs"]), 2)
        states = screens[0]["screen_states"]
        self.assertIn("GO - Host item added New screen", states)
        self.assertIn("Variant 2", states)
        self.assertEqual(len(collapse_map["auto_collapsed"]), 1)

    def test_attach_validations_binds_rule_to_flow_trigger(self):
        pp = {
            "screens": [
                {
                    "id": "screen-a",
                    "name": "MPS",
                    "abs_x": 0,
                    "abs_y": 100,
                    "width": 400,
                    "height": 800,
                    "contextual_informations": [
                        {
                            "id": "rule-note",
                            "name": "Unable to add if the discounted SKU is sold out",
                            "abs_x": 10,
                            "abs_y": 50,
                            "width": 100,
                            "height": 40,
                        },
                    ],
                },
            ],
            "text_cache": {
                "rule-note": "Unable to add if the discounted SKU is sold out",
            },
            "index": {
                "screen-a": {"abs_x": 0, "abs_y": 100, "width": 400, "height": 800},
                "btn-node": {"abs_x": 20, "abs_y": 200, "width": 80, "height": 40},
            },
            "node_tree": {"id": "screen-a", "children": []},
        }
        screens = [
            {
                "screen_id": "MPS",
                "source_ref": "screen-a",
                "elements": [
                    {
                        "element_id": "MPS.add_item_btn",
                        "source_ref": "btn-node",
                        "role": "BUTTON",
                        "validations_and_edge_cases": [],
                    },
                ],
            },
        ]
        inventory = {
            "screens": [{"id": "screen-a", "flow_element_ids": ["btn-node"]}],
            "elements": [],
            "connectors": [],
        }
        ui_flow = [
            {
                "from_screen_id": "MPS",
                "from_source_ref": "screen-a",
                "trigger_element_id": "MPS.add_item_btn",
                "navigation_kind": "NAVIGATE",
                "source_ref": "conn-1",
            },
        ]
        gaps = attach_validations(screens, pp, inventory, ui_flow)
        validations = screens[0]["elements"][0]["validations_and_edge_cases"]
        self.assertTrue(any("Unable to add" in v for v in validations))
        self.assertEqual(gaps, [])


class TestScreenCollapse(unittest.TestCase):
    def test_name_variant_frames_stay_split(self):
        pp = {
            "screens": [
                {"id": "frame-en", "name": "MPS / EN"},
                {"id": "frame-error", "name": "MPS / Error"},
            ],
            "screen_context": {},
            "text_cache": {},
            "node_tree": {
                "id": "root",
                "children": [
                    {"id": "frame-en", "name": "MPS / EN", "children": []},
                    {"id": "frame-error", "name": "MPS / Error", "children": []},
                ],
            },
            "index": {},
            "edges": [],
            "original_edges": [],
        }
        screens, _, collapse_map = build_screens(pp, None, use_inventory=False)
        self.assertEqual(len(screens), 2)
        self.assertEqual(len(collapse_map["candidates"]), 1)
        self.assertIn("name_variant", collapse_map["candidates"][0]["signals"])

    def test_merge_semantic_elements_keeps_distinct_labels(self):
        elements = [
            {
                "element_id": "LANDING.view_group_cart_btn",
                "source_ref": "a",
                "role": "BUTTON",
                "label": "View group cart",
                "type": "INSTANCE",
                "interactions": [],
                "validations_and_edge_cases": [],
                "_frame_qualifier": "Variant 1",
            },
            {
                "element_id": "LANDING.view_group_cart_1_btn",
                "source_ref": "b",
                "role": "BUTTON",
                "label": "View group cart • 1",
                "type": "INSTANCE",
                "interactions": [],
                "validations_and_edge_cases": [],
                "_frame_qualifier": "Variant 2",
            },
        ]
        merged = merge_semantic_elements(elements)
        self.assertEqual(len(merged), 2)
        self.assertEqual(len({el["element_id"] for el in merged}), 2)

    def test_build_ui_flow_maps_all_source_refs(self):
        pp = {
            "screens": [
                {"id": "frame-a", "name": "Landing"},
                {"id": "frame-b", "name": "Landing"},
                {"id": "target", "name": "Target"},
            ],
            "entry_points": [{"id": "frame-a", "reason": "CONTEXT"}],
            "index": {
                "btn-a": {"parent_id": "frame-a"},
                "btn-b": {"parent_id": "frame-b"},
                "target-node": {"parent_id": "target"},
            },
            "edges": [
                {
                    "id": "edge-b",
                    "from": "frame-b",
                    "to": "target",
                    "original_from": "btn-b",
                    "original_to": "target-node",
                    "label": "Go",
                },
            ],
            "original_edges": [],
            "node_id_to_screen": {},
            "contextual_node_id_to_screen": {},
        }
        screens = [
            {
                "screen_id": "LANDING",
                "source_ref": "frame-a",
                "source_refs": ["frame-a", "frame-b"],
                "elements": [
                    {
                        "source_ref": "btn-b",
                        "element_id": "LANDING.go_btn",
                    },
                ],
            },
            {
                "screen_id": "TARGET",
                "source_ref": "target",
                "source_refs": ["target"],
                "elements": [],
            },
        ]
        ui_flow, _ = build_ui_flow(pp, screens)
        navigate = [e for e in ui_flow if e.get("navigation_kind") == "NAVIGATE"]
        self.assertEqual(len(navigate), 1)
        self.assertEqual(navigate[0]["from_screen_id"], "LANDING")
        self.assertEqual(navigate[0]["trigger_source_ref"], "btn-b")

    def test_apply_screen_collapse_merges_agent_decision(self):
        context = {
            "screens": [
                {
                    "screen_id": "MPS",
                    "source_ref": "frame-en",
                    "source_refs": ["frame-en"],
                    "screen_states": ["EN"],
                    "state_kinds": ["LOCALE_VARIANT"],
                    "elements": [
                        {
                            "element_id": "MPS.order_type_chip",
                            "source_ref": "chip-a",
                            "role": "BUTTON",
                            "label": "Delivery",
                            "type": "INSTANCE",
                            "interactions": [],
                            "validations_and_edge_cases": [],
                        },
                    ],
                    "screen_notes": "",
                },
                {
                    "screen_id": "MPS",
                    "source_ref": "frame-error",
                    "source_refs": ["frame-error"],
                    "screen_states": ["Error"],
                    "state_kinds": ["ERROR"],
                    "elements": [
                        {
                            "element_id": "MPS.order_type_chip_2",
                            "source_ref": "chip-b",
                            "role": "BUTTON",
                            "label": "Delivery",
                            "type": "INSTANCE",
                            "interactions": [],
                            "validations_and_edge_cases": [],
                        },
                    ],
                    "screen_notes": "",
                },
            ],
            "ui_flow": [],
        }
        collapse_map = {
            "decisions": [
                {
                    "screen_id": "MPS",
                    "action": "collapse",
                    "frame_ids": ["frame-en", "frame-error"],
                    "confidence": "high",
                },
            ],
        }
        results = apply_screen_collapse(context, collapse_map)
        self.assertEqual(results[0][0], "applied")
        self.assertEqual(len(context["screens"]), 1)
        self.assertEqual(
            set(context["screens"][0]["source_refs"]),
            {"frame-en", "frame-error"},
        )
        element_ids = {el["element_id"] for el in context["screens"][0]["elements"]}
        self.assertEqual(len(element_ids), 1)


class TestMandatoryPipelineOutputs(unittest.TestCase):
    def test_clean_workdir_removes_prior_artefacts(self):
        import tempfile

        from run_design_extractor import clean_workdir, workdir_artifacts

        stem = "Sample-Export"
        with tempfile.TemporaryDirectory() as tmp:
            for name in workdir_artifacts(stem):
                path = os.path.join(tmp, name)
                with open(path, "w", encoding="utf-8") as f:
                    f.write("{}")
            clean_workdir(tmp, stem)
            for name in workdir_artifacts(stem):
                self.assertFalse(os.path.exists(os.path.join(tmp, name)))

    def test_finalize_writes_refinement_scaffold_and_design_context(self):
        import json
        import tempfile

        from recover_design_context import finalize_design_context

        with tempfile.TemporaryDirectory() as tmp:
            context = {
                "extraction_status": "OK",
                "extraction_gaps": [],
                "visual_analysis_scratchpad": "test",
                "project_context": {
                    "overall_ambiguity_rating": "LOW",
                    "blocking_issues": [],
                },
                "screens": [],
                "ui_flow": [],
            }
            context_path = os.path.join(tmp, "design_context.temp.json")
            with open(context_path, "w", encoding="utf-8") as f:
                json.dump(context, f)

            finalize_design_context(tmp, context_path=context_path)

            refinement_path = os.path.join(tmp, "id_refinement_map.json")
            final_path = os.path.join(tmp, "design_context.json")
            self.assertTrue(os.path.exists(refinement_path))
            self.assertTrue(os.path.exists(final_path))
            with open(refinement_path, encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"refinements": []})
            with open(final_path, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["extraction_status"], "OK")


if __name__ == "__main__":
    unittest.main()
