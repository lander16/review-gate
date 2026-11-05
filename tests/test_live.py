"""Opt-in authenticated smoke test with synthetic input only."""
import json
import os
from pathlib import Path

import pytest

from review_gate.config import load
from review_gate.runners import review

pytestmark = pytest.mark.live


@pytest.mark.skipif(os.environ.get("REVIEW_GATE_LIVE") != "1", reason="requires signed-in reviewer CLIs")
@pytest.mark.parametrize("family", os.environ.get("REVIEW_GATE_LIVE_FAMILIES", "openai").split(","))
def test_live_default_routes(tmp_path, family):
    config = Path(os.environ["REVIEW_GATE_LIVE_CONFIG"])
    # The user explicitly approves this root key and the selected services in the smoke config.
    root = Path(os.environ["REVIEW_GATE_LIVE_ROOT"]).resolve()
    packet = {
        "version": 1,
        "phase": "plan",
        "documents": [
            {"path": "task", "side": "task", "text": "Implement addition of two integers.\n"},
            {"path": "plan", "side": "plan", "text": "Return the sum and test signed inputs.\n"},
        ],
    }
    reviewers = load(config, root, family)
    results = review(reviewers, packet, json.dumps(packet).encode())
    assert [result["status"] for result in results] == ["ok"] * len(reviewers), results
