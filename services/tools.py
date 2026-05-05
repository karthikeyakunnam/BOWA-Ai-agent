"""Tool registry for BOWA AI Orchestrator.

Maps existing deterministic Python modules (jobs, news, student) 
to LLM-callable JSON schema tools.
"""

import json
from typing import Any

from services.student import get_student_roadmap
from services.jobs import filter_jobs, fetch_jobs, get_skill_gap_analysis
from services.news import get_priority_news
from services.planner import create_user_plan, mark_task_done


BOWA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_study_roadmap",
            "description": "Generate a study roadmap for a specific academic branch or subject.",
            "parameters": {
                "type": "object",
                "properties": {
                    "branch": {
                        "type": "string",
                        "description": "The academic branch or subject (e.g., CSE, Mechanical, Data Structures)."
                    }
                },
                "required": ["branch"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_jobs",
            "description": "Search for jobs and get a skill gap analysis based on a target role and user's current skills.",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "description": "The target job role (e.g., Frontend Developer, Data Analyst)."
                    },
                    "current_skills": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of skills the user currently possesses."
                    }
                },
                "required": ["role", "current_skills"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_latest_news",
            "description": "Fetch the latest priority news updates related to tech, jobs, and academics.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "plan_tracker",
            "description": "Create a practical plan or mark a plan task complete for study, job search, or daily execution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create_plan", "mark_done"],
                        "description": "Use create_plan for a new plan and mark_done to complete a numbered task."
                    },
                    "user_id": {
                        "type": "string",
                        "description": "The current user ID."
                    },
                    "goal": {
                        "type": "string",
                        "description": "The outcome the user wants to achieve."
                    },
                    "hours": {
                        "type": "number",
                        "description": "Available hours for the plan."
                    },
                    "tasks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tasks to schedule."
                    },
                    "task_number": {
                        "type": "integer",
                        "description": "Task block number to mark done."
                    }
                },
                "required": ["action", "user_id"]
            }
        }
    }
]


def execute_tool(name: str, arguments_json: str | dict[str, Any]) -> str:
    """Execute a local BOWA tool and return the result as a JSON string."""
    if isinstance(arguments_json, dict):
        args = arguments_json
    else:
        try:
            args = json.loads(arguments_json or "{}")
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON arguments provided."})

    try:
        if name == "get_study_roadmap":
            roadmap = get_student_roadmap(args.get("branch", ""))
            return json.dumps({"roadmap": roadmap})
            
        elif name == "search_jobs":
            role = args.get("role", "")
            skills = args.get("current_skills", [])
            
            jobs = fetch_jobs()
            matched = filter_jobs(jobs, role)
            # Only return top 3 to save token context
            matched = matched[:3]
            
            gap = get_skill_gap_analysis(role, skills)
            return json.dumps({
                "job_matches": matched,
                "skill_gap": gap
            })
            
        elif name == "get_latest_news":
            news = get_priority_news()
            return json.dumps({"news": news})

        elif name == "plan_tracker":
            action = args.get("action", "create_plan")
            user_id = args.get("user_id", "default")
            if action == "mark_done":
                return json.dumps(mark_task_done(user_id, int(args.get("task_number", 1))))

            plan = create_user_plan(
                user_id=user_id,
                goal=args.get("goal", "Plan today"),
                hours=args.get("hours", 2),
                tasks=args.get("tasks", []),
            )
            return json.dumps({"plan": plan})
            
        else:
            return json.dumps({"error": f"Tool '{name}' not found."})
            
    except Exception as e:
        return json.dumps({"error": f"Error executing tool {name}: {str(e)}"})
