import pytest
from datetime import datetime, timezone
from services.memory import load_user_memory, save_user_memory
from services.goal_engine import get_user_goal, set_user_goal
from services.state import get_user_state, update_user_state, set_active_mode, build_initial_state
from services.execution import create_one_session_task, end_execution_session, get_execution_session
from services.trajectory import load_trajectory


def test_goal_state_migration(user_id, clean_memory, clean_state):
    """Test that legacy global goals in memory.json are migrated to active mode state on read."""
    clean_memory({})
    clean_state({})

    # 1. Store global goal in memory.json directly
    memory = load_user_memory(user_id) or {}
    memory["goal"] = "Legacy Global Goal"
    save_user_memory(user_id, memory)

    # 2. Verify state has no goal
    state = get_user_state(user_id)
    assert not state or not state.get("data", {}).get("goal")


    # 3. Reading the goal should auto-migrate it
    goal = get_user_goal(user_id)
    assert goal == "Legacy Global Goal"

    # 4. Verify goal is now written to state.json under active mode (General)
    migrated_state = get_user_state(user_id)
    assert migrated_state is not None
    assert migrated_state["data"]["goal"] == "Legacy Global Goal"


def test_dynamic_execution_stage_override(user_id, clean_memory, clean_state):
    """Test that conversation stage dynamically overrides to 'executing' while session is active."""
    clean_memory({})
    clean_state({})

    # Start with General mode and init stage
    state = build_initial_state("General")
    state["stage"] = "planned"
    update_user_state(user_id, state)

    # Ensure get_user_state returns planned
    assert get_user_state(user_id)["stage"] == "planned"
    assert load_trajectory(user_id)["current_stage"] != "executing"

    # 1. Start an execution session
    create_one_session_task(user_id, "Refactor task", 25)
    
    # 2. Stage should dynamically resolve to "executing"
    resolved_state = get_user_state(user_id)
    assert resolved_state["stage"] == "executing"

    resolved_trajectory = load_trajectory(user_id)
    assert resolved_trajectory["current_stage"] == "executing"

    # 3. End execution session
    end_execution_session(user_id, completed=True)

    # 4. Stage should transition to "ask"
    final_state = get_user_state(user_id)
    assert final_state["stage"] == "ask"
    assert load_trajectory(user_id)["current_stage"] != "executing"


def test_mode_isolated_goals(user_id, clean_memory, clean_state):
    """Test that setting active goals is isolated per mode and does not overwrite others."""
    clean_memory({})
    clean_state({})

    # Initialize modes
    set_active_mode(user_id, "General")
    set_user_goal(user_id, "Get Fit")

    set_active_mode(user_id, "Jobs")
    set_user_goal(user_id, "Become Software Engineer")

    # Verify General goal
    set_active_mode(user_id, "General")
    assert get_user_goal(user_id) == "Get Fit"

    # Verify Jobs goal
    set_active_mode(user_id, "Jobs")
    assert get_user_goal(user_id) == "Become Software Engineer"
