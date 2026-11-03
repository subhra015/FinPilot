"""Tests for Simulator & Security Challenge Suite (Layer 14).

Executes and verifies all 17 challenges specified in Layer 14 requirements.
"""

from __future__ import annotations

import pytest

from finpilot.workflow.challenge_suite import SimulatorSecurityChallengeSuite


@pytest.fixture
def suite() -> SimulatorSecurityChallengeSuite:
    return SimulatorSecurityChallengeSuite()


def test_challenge_01_stop_gap(suite: SimulatorSecurityChallengeSuite) -> None:
    res = suite.challenge_01_stop_gap()
    assert res.passed is True


def test_challenge_02_stop_target_collision(suite: SimulatorSecurityChallengeSuite) -> None:
    res = suite.challenge_02_stop_target_collision()
    assert res.passed is True


def test_challenge_03_partial_fill(suite: SimulatorSecurityChallengeSuite) -> None:
    res = suite.challenge_03_partial_fill()
    assert res.passed is True


def test_challenge_04_limit_touch_without_proven_fill(suite: SimulatorSecurityChallengeSuite) -> None:
    res = suite.challenge_04_limit_touch_without_proven_fill()
    assert res.passed is True


def test_challenge_05_duplicate_event(suite: SimulatorSecurityChallengeSuite) -> None:
    res = suite.challenge_05_duplicate_event()
    assert res.passed is True


def test_challenge_06_out_of_order_candle(suite: SimulatorSecurityChallengeSuite) -> None:
    res = suite.challenge_06_out_of_order_candle()
    assert res.passed is True


def test_challenge_07_simultaneous_candidates_competing_for_cash(suite: SimulatorSecurityChallengeSuite) -> None:
    res = suite.challenge_07_simultaneous_candidates_competing_for_cash()
    assert res.passed is True


def test_challenge_08_session_close_with_unresolved_position(suite: SimulatorSecurityChallengeSuite) -> None:
    res = suite.challenge_08_session_close_with_unresolved_position()
    assert res.passed is True


def test_challenge_09_provider_outage_stale_data(suite: SimulatorSecurityChallengeSuite) -> None:
    res = suite.challenge_09_provider_outage_stale_data()
    assert res.passed is True


def test_challenge_10_corporate_action_discontinuity(suite: SimulatorSecurityChallengeSuite) -> None:
    res = suite.challenge_10_corporate_action_discontinuity()
    assert res.passed is True


def test_challenge_11_unauthenticated_api_call(suite: SimulatorSecurityChallengeSuite) -> None:
    res = suite.challenge_11_unauthenticated_api_call()
    assert res.passed is True


def test_challenge_12_cross_user_data_access(suite: SimulatorSecurityChallengeSuite) -> None:
    res = suite.challenge_12_cross_user_data_access()
    assert res.passed is True


def test_challenge_13_xss_payload(suite: SimulatorSecurityChallengeSuite) -> None:
    res = suite.challenge_13_xss_payload()
    assert res.passed is True


def test_challenge_14_malformed_oversized_import(suite: SimulatorSecurityChallengeSuite) -> None:
    res = suite.challenge_14_malformed_oversized_import()
    assert res.passed is True


def test_challenge_15_rate_limit_abuse(suite: SimulatorSecurityChallengeSuite) -> None:
    res = suite.challenge_15_rate_limit_abuse()
    assert res.passed is True


def test_challenge_16_csrf_attempt(suite: SimulatorSecurityChallengeSuite) -> None:
    res = suite.challenge_16_csrf_attempt()
    assert res.passed is True


def test_challenge_17_unauthorized_admin_request(suite: SimulatorSecurityChallengeSuite) -> None:
    res = suite.challenge_17_unauthorized_admin_request()
    assert res.passed is True


def test_all_17_challenges_pass_in_sequence(suite: SimulatorSecurityChallengeSuite) -> None:
    """Run all 17 challenges as a batch and assert 100% success."""
    results = suite.run_all_challenges()
    assert len(results) == 17
    failed = [r for r in results if not r.passed]
    assert len(failed) == 0, f"Challenges failed: {[f.name for f in failed]}"
