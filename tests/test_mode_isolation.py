"""Tests for BOWA mode system isolation, state isolation, and endpoints."""

import pytest
from fastapi.testclient import TestClient
from main import app
from services.state import get_user_state, update_user_state, set_active_mode, build_initial_state
from services.trajectory import _stage_from_action
from services.planner_engine import generate_plan

@pytest.fixture
def client():
    return TestClient(app)

def test_set_active_mode_and_isolation(user_id, clean_state):
    """Test that setting active mode isolates states and histories across different modes."""
    clean_state({})
    
    # Initialize General mode state
    general_state = build_initial_state("General")
    general_state["data"]["goal"] = "General Mode Goal"
    update_user_state(user_id, general_state)
    
    # Initialize Jobs mode state
    jobs_state = build_initial_state("Jobs")
    jobs_state["data"]["goal"] = "Jobs Mode Goal"
    update_user_state(user_id, jobs_state)
    
    # Set active mode to General
    set_active_mode(user_id, "General")
    state = get_user_state(user_id)
    assert state is not None
    assert state["mode"] == "General"
    assert state["data"]["goal"] == "General Mode Goal"
    
    # Set active mode to Jobs
    set_active_mode(user_id, "Jobs")
    state = get_user_state(user_id)
    assert state is not None
    assert state["mode"] == "Jobs"
    assert state["data"]["goal"] == "Jobs Mode Goal"

def test_post_active_mode_endpoint(client, user_id, clean_state):
    """Test that POST /user/active_mode synchronizes active mode state on the backend."""
    clean_state({})
    
    # 1. Update active mode to Jobs
    response = client.post("/user/active_mode", json={"user_id": user_id, "mode": "Jobs"})
    assert response.status_code == 200
    assert response.json() == {"status": "success", "active_mode": "Jobs"}
    
    # Verify via get_user_state that the active mode has updated
    state = get_user_state(user_id)
    # Since we set active mode but haven't updated user state dict for Jobs, it might be None or default.
    # In state.py, get_user_state defaults to returning None if state dict for the mode does not exist.
    assert state is None
    
    # Now let's initialize a Jobs state and verify
    jobs_state = build_initial_state("Jobs")
    jobs_state["data"]["goal"] = "Become an iOS Developer"
    update_user_state(user_id, jobs_state)
    
    # Fetch state endpoint and verify it returns Jobs goal
    response = client.get(f"/state/{user_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["goal"] == "Become an iOS Developer"

def test_trajectory_stage_for_research_actions():
    """Verify that research/info action types keep the stage in 'planning' instead of 'executing'."""
    # Research/information gathering actions should return planning
    assert _stage_from_action("jobs", 0.0, 0, 0) == "planning"
    assert _stage_from_action("news", 0.0, 0, 0) == "planning"
    assert _stage_from_action("explanation", 0.0, 0, 0) == "planning"
    assert _stage_from_action("motivation", 0.0, 0, 0) == "planning"
    
    # Actual execution should transition to executing
    assert _stage_from_action("plan_step", 0.0, 0, 0) == "executing"
    assert _stage_from_action("execute", 0.0, 0, 0) == "planning"  # defaults to planning for unmapped types unless tracked

def test_greeting_guard_prevents_plan_generation(user_id, clean_state):
    """Planner engine should not generate plans for greeting messages."""
    clean_state({})
    
    # A greeting query should yield None/empty or not trigger planning
    plan = generate_plan({"mode": "General"}, "greeting", "hi BOWA hello")
    assert plan is None
