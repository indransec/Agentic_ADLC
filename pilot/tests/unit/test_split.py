"""T018: hash-based canary assignment is even and deterministic (FR-011, SC-003)."""

from pilot_tools.split import bucket, chooses_candidate


def test_canary_share_over_500_requests() -> None:
    ids = [f"INC-7-{n}" for n in range(500)]
    chosen = sum(chooses_candidate("canary", 0.2, i, True) for i in ids)
    assert 75 <= chosen <= 125  # 15-25%
    assert [chooses_candidate("canary", 0.2, i, True) for i in ids] == [
        chooses_candidate("canary", 0.2, i, True) for i in ids
    ]


def test_shadow_full_and_no_candidate_never_choose_it() -> None:
    for request_id in ("a", "b", "c"):
        assert not chooses_candidate("shadow", 1.0, request_id, True)
        assert not chooses_candidate("full", 1.0, request_id, True)
        assert not chooses_candidate("canary", 1.0, request_id, False)
    assert 0 <= bucket("x") < 1
