"""gain_for unit-scale tests (Phase 0.2) -- pure logic, no DB.

Locks the goal_alignment->points normalization so a learned client can't silently jump ~50x (the old
roadmap/predict_plan bug) or 2x (the old predict_impact *100), and so plan-ROI and roadmap-ROI, both
routed through gain_for, can never diverge again.
"""
from __future__ import annotations

from rep_engine import roi_predictor as roi


def test_learned_gain_is_ga_times_50_not_1_or_100():
    # a learned 0.10 goal_alignment-per-unit -> 5.0 POINTS (x50). NOT 0.10 (x1) and NOT 10.0 (x100).
    pts, basis, conf = roi.gain_for("content_writing", own={"third_party_articles": 0.10}, priors={})
    assert pts == 5.0
    assert basis == "this client" and conf == "medium"


def test_static_baseline_is_points_as_is():
    pts, basis, _ = roi.gain_for("content_writing", own={}, priors={})
    assert pts == float(roi._STATIC_GAIN["content_writing"])   # already points -> unchanged
    assert basis == "industry baseline"


def test_cross_client_prior_also_scaled_x50():
    pts, basis, conf = roi.gain_for(
        "content_writing", own={},
        priors={"third_party_articles": {"gain_per_unit": 0.04, "confidence": "medium"}})
    assert pts == 2.0        # 0.04 * 50
    assert basis == "cross-client" and conf == "medium"


def test_learned_gain_is_clamped_to_sane_max():
    # an absurd learned value can't produce a runaway projection (defensive cap).
    pts, _, _ = roi.gain_for("content_writing", own={"third_party_articles": 5.0}, priors={})
    assert pts == roi._MAX_TASK_POINTS   # clamped, not 250


def test_this_client_wins_over_prior_and_static():
    pts, basis, _ = roi.gain_for(
        "content_writing", own={"third_party_articles": 0.10},
        priors={"third_party_articles": {"gain_per_unit": 0.30, "confidence": "high"}})
    assert basis == "this client" and pts == 5.0   # own 0.10*50, not the prior


def test_all_paths_return_points_in_sane_range():
    for own in ({}, {"third_party_articles": 0.05}, {"third_party_articles": 0.3}):
        pts, _, _ = roi.gain_for("content_writing", own=own, priors={})
        assert 0.0 <= pts <= roi._MAX_TASK_POINTS + 0.01
