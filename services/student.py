"""Student roadmap service for BOWA."""

from typing import Any


def normalize_branch(branch: str) -> str:
    """Convert user branch input into a known roadmap key."""
    normalized_branch = branch.strip().lower()

    branch_aliases = {
        "cse": "CSE",
        "computer science": "CSE",
        "computer science engineering": "CSE",
        "cs": "CSE",
        "ece": "ECE",
        "electronics": "ECE",
        "electronics and communication": "ECE",
        "electronics and communication engineering": "ECE",
        "mechanical": "Mechanical",
        "mechanical engineering": "Mechanical",
        "mech": "Mechanical",
        "civil": "Civil",
        "civil engineering": "Civil"
    }

    return branch_aliases.get(normalized_branch, "Generic")


def get_roadmaps() -> dict[str, dict[str, Any]]:
    """Return all available student roadmaps."""
    return {
        "CSE": {
            "branch_name": "CSE",
            "skills": [
                "Data Structures & Algorithms",
                "Python / Backend Development",
                "SQL / Databases",
                "Web Development",
                "Git & GitHub"
            ],
            "steps": [
                "Step 1: Learn programming basics with Python or C++",
                "Step 2: Learn DSA and solve beginner coding problems",
                "Step 3: Build 2-3 projects using web and database concepts",
                "Step 4: Learn API development and backend fundamentals",
                "Step 5: Learn system design basics and deployment"
            ],
            "weekly_actions": [
                "Solve 10 coding problems",
                "Build or improve one project feature",
                "Revise one core CS concept",
                "Push project updates to GitHub"
            ]
        },
        "ECE": {
            "branch_name": "ECE",
            "skills": [
                "Digital Electronics",
                "Embedded Systems",
                "C / Python Programming",
                "IoT Basics",
                "Communication Systems"
            ],
            "steps": [
                "Step 1: Strengthen electronics and circuit fundamentals",
                "Step 2: Learn C programming for embedded systems",
                "Step 3: Work with Arduino, sensors, and microcontrollers",
                "Step 4: Build an IoT or embedded mini project",
                "Step 5: Learn basics of signal processing and communication"
            ],
            "weekly_actions": [
                "Revise one electronics topic",
                "Practice C or Python for 3 sessions",
                "Simulate or build one small circuit",
                "Document one mini project idea"
            ]
        },
        "Mechanical": {
            "branch_name": "Mechanical",
            "skills": [
                "Engineering Mechanics",
                "CAD Design",
                "Manufacturing Processes",
                "Thermodynamics",
                "Python / MATLAB Basics"
            ],
            "steps": [
                "Step 1: Strengthen mechanics and thermodynamics basics",
                "Step 2: Learn CAD tools like AutoCAD, SolidWorks, or Fusion 360",
                "Step 3: Build design and simulation mini projects",
                "Step 4: Learn manufacturing and quality control basics",
                "Step 5: Add Python or MATLAB for engineering calculations"
            ],
            "weekly_actions": [
                "Practice one CAD model",
                "Revise one core mechanical subject",
                "Solve 5 numerical problems",
                "Document one design improvement idea"
            ]
        },
        "Civil": {
            "branch_name": "Civil",
            "skills": [
                "Structural Analysis",
                "AutoCAD",
                "Estimation & Costing",
                "Surveying",
                "Construction Management"
            ],
            "steps": [
                "Step 1: Strengthen engineering drawing and surveying basics",
                "Step 2: Learn AutoCAD for civil layouts",
                "Step 3: Study structural analysis and concrete fundamentals",
                "Step 4: Practice estimation and costing problems",
                "Step 5: Build a small planning or design portfolio"
            ],
            "weekly_actions": [
                "Create one AutoCAD drawing",
                "Revise one civil engineering concept",
                "Solve 5 estimation or structure problems",
                "Study one real construction case"
            ]
        },
        "Generic": {
            "branch_name": "Generic",
            "skills": [
                "Communication Skills",
                "Problem Solving",
                "Basic Programming",
                "Domain Fundamentals",
                "Project Building"
            ],
            "steps": [
                "Step 1: Identify your target career path",
                "Step 2: Learn the core subjects of your branch",
                "Step 3: Pick one practical tool used in your field",
                "Step 4: Build a small portfolio project",
                "Step 5: Prepare a resume and share your work online"
            ],
            "weekly_actions": [
                "Study one core topic",
                "Practice one technical skill",
                "Work on one small project task",
                "Update your notes or portfolio"
            ]
        }
    }


def get_student_roadmap(branch: str) -> dict[str, Any]:
    """Return a structured learning roadmap for a student branch."""
    roadmap_key = normalize_branch(branch)
    roadmap = get_roadmaps()[roadmap_key]

    return {
        "input_branch": branch,
        "matched_branch": roadmap_key,
        "roadmap": roadmap
    }
