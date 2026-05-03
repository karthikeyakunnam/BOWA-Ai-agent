"""Job recommendation and skill gap service for BOWA."""

from typing import Any


def fetch_jobs() -> list[dict[str, str]]:
    """Fetch available jobs from a local mock dataset."""
    return [
        {
            "company": "Google",
            "role": "Data Analyst",
            "location": "Bengaluru, India",
            "url": "https://careers.google.com/jobs/results/"
        },
        {
            "company": "Microsoft",
            "role": "Frontend Developer",
            "location": "Hyderabad, India",
            "url": "https://careers.microsoft.com/"
        },
        {
            "company": "Amazon",
            "role": "Software Engineer",
            "location": "Chennai, India",
            "url": "https://www.amazon.jobs/"
        },
        {
            "company": "Infosys",
            "role": "Java Developer",
            "location": "Pune, India",
            "url": "https://www.infosys.com/careers/"
        },
        {
            "company": "TCS",
            "role": "Backend Developer",
            "location": "Mumbai, India",
            "url": "https://www.tcs.com/careers"
        },
        {
            "company": "Accenture",
            "role": "Data Analyst Intern",
            "location": "Gurugram, India",
            "url": "https://www.accenture.com/in-en/careers"
        },
        {
            "company": "Zoho",
            "role": "Full Stack Developer",
            "location": "Chennai, India",
            "url": "https://www.zoho.com/careers/"
        },
        {
            "company": "Freshworks",
            "role": "Frontend Engineer",
            "location": "Chennai, India",
            "url": "https://www.freshworks.com/company/careers/"
        },
        {
            "company": "Flipkart",
            "role": "Product Manager",
            "location": "Bengaluru, India",
            "url": "https://www.flipkartcareers.com/"
        },
        {
            "company": "Swiggy",
            "role": "Business Analyst",
            "location": "Bengaluru, India",
            "url": "https://careers.swiggy.com/"
        },
        {
            "company": "Zomato",
            "role": "DevOps Engineer",
            "location": "Gurugram, India",
            "url": "https://www.zomato.com/careers"
        },
        {
            "company": "Razorpay",
            "role": "Python Backend Developer",
            "location": "Bengaluru, India",
            "url": "https://razorpay.com/jobs/"
        },
        {
            "company": "Paytm",
            "role": "Machine Learning Engineer",
            "location": "Noida, India",
            "url": "https://paytm.com/careers/"
        },
        {
            "company": "Deloitte",
            "role": "Data Scientist",
            "location": "Hyderabad, India",
            "url": "https://www.deloitte.com/global/en/careers.html"
        },
        {
            "company": "Wipro",
            "role": "Cloud Engineer",
            "location": "Bengaluru, India",
            "url": "https://careers.wipro.com/"
        },
        {
            "company": "IBM",
            "role": "AI Engineer",
            "location": "Kochi, India",
            "url": "https://www.ibm.com/careers"
        },
        {
            "company": "Capgemini",
            "role": "QA Automation Engineer",
            "location": "Pune, India",
            "url": "https://www.capgemini.com/careers/"
        },
        {
            "company": "Adobe",
            "role": "UI Developer",
            "location": "Noida, India",
            "url": "https://careers.adobe.com/"
        },
        {
            "company": "LinkedIn",
            "role": "Software Engineer Intern",
            "location": "Bengaluru, India",
            "url": "https://careers.linkedin.com/"
        },
        {
            "company": "Oracle",
            "role": "Database Administrator",
            "location": "Hyderabad, India",
            "url": "https://www.oracle.com/careers/"
        }
    ]


def calculate_job_relevance(job_role: str, preferred_role: str) -> int:
    """Calculate relevance score using simple case-insensitive string matching."""
    job_role_lower = job_role.lower()
    preferred_role_lower = preferred_role.lower()
    preferred_words = preferred_role_lower.split()

    if job_role_lower == preferred_role_lower:
        return 100
    if preferred_role_lower in job_role_lower:
        return 80
    if job_role_lower in preferred_role_lower:
        return 70

    matched_words = sum(1 for word in preferred_words if word in job_role_lower)
    return matched_words * 20


def filter_jobs(jobs: list[dict[str, str]], role: str) -> list[dict[str, Any]]:
    """Filter jobs by preferred role and sort them by relevance."""
    scored_jobs = []

    for job in jobs:
        relevance = calculate_job_relevance(job["role"], role)
        if relevance > 0:
            scored_job = {**job, "relevance_score": relevance}
            scored_jobs.append(scored_job)

    scored_jobs.sort(key=lambda job: job["relevance_score"], reverse=True)
    return scored_jobs[:10]


def get_required_skills(role: str) -> list[str]:
    """Return required skills for a target job role."""
    role_key = role.strip().lower()
    role_skills = {
        "data analyst": [
            "Python",
            "SQL",
            "Excel",
            "Data Visualization",
            "Statistics"
        ],
        "business analyst": [
            "Excel",
            "SQL",
            "Communication",
            "Requirement Analysis",
            "Data Visualization"
        ],
        "frontend developer": [
            "HTML",
            "CSS",
            "JavaScript",
            "React",
            "Git"
        ],
        "frontend engineer": [
            "HTML",
            "CSS",
            "JavaScript",
            "React",
            "Git"
        ],
        "ui developer": [
            "HTML",
            "CSS",
            "JavaScript",
            "React",
            "Responsive Design"
        ],
        "software engineer": [
            "Data Structures & Algorithms",
            "Python or Java",
            "SQL",
            "Git",
            "System Design Basics"
        ],
        "software engineer intern": [
            "Programming Basics",
            "Data Structures & Algorithms",
            "Git",
            "Problem Solving",
            "Projects"
        ],
        "backend developer": [
            "Python or Java",
            "APIs",
            "SQL",
            "Databases",
            "Authentication"
        ],
        "python backend developer": [
            "Python",
            "FastAPI or Django",
            "SQL",
            "REST APIs",
            "Git"
        ],
        "full stack developer": [
            "HTML",
            "CSS",
            "JavaScript",
            "Backend APIs",
            "Databases"
        ],
        "java developer": [
            "Java",
            "OOP",
            "Spring Boot",
            "SQL",
            "REST APIs"
        ],
        "data scientist": [
            "Python",
            "SQL",
            "Machine Learning",
            "Statistics",
            "Data Visualization"
        ],
        "machine learning engineer": [
            "Python",
            "Machine Learning",
            "Deep Learning Basics",
            "Model Deployment",
            "SQL"
        ],
        "devops engineer": [
            "Linux",
            "Git",
            "Docker",
            "CI/CD",
            "Cloud Basics"
        ],
        "cloud engineer": [
            "Linux",
            "Networking",
            "Cloud Basics",
            "Docker",
            "Security Basics"
        ],
        "product manager": [
            "Product Thinking",
            "Market Research",
            "User Stories",
            "Analytics",
            "Communication"
        ],
        "qa automation engineer": [
            "Manual Testing",
            "Selenium",
            "Python or Java",
            "Test Cases",
            "API Testing"
        ],
        "ai engineer": [
            "Python",
            "Machine Learning",
            "Deep Learning Basics",
            "APIs",
            "Model Evaluation"
        ],
        "database administrator": [
            "SQL",
            "Database Design",
            "Backup & Recovery",
            "Performance Tuning",
            "Security Basics"
        ]
    }

    if role_key in role_skills:
        return role_skills[role_key]

    for known_role, skills in role_skills.items():
        if role_key in known_role or known_role in role_key:
            return skills

    return [
        "Communication",
        "Problem Solving",
        "Git",
        "Basic Programming",
        "Project Building"
    ]


def skill_matches(user_skill: str, required_skill: str) -> bool:
    """Check whether a user skill matches a required skill."""
    user_skill_lower = user_skill.lower().strip()
    required_skill_lower = required_skill.lower().strip()

    if user_skill_lower == required_skill_lower:
        return True
    if user_skill_lower in required_skill_lower:
        return True
    if required_skill_lower in user_skill_lower:
        return True

    required_parts = [
        part.strip()
        for separator in [" or ", "/", "&"]
        for part in required_skill_lower.split(separator)
    ]

    return any(part and part == user_skill_lower for part in required_parts)


def analyze_skill_gap(
    user_skills: list[str],
    required_skills: list[str]
) -> dict[str, list[str]]:
    """Compare user skills with required skills."""
    matched_skills = []
    missing_skills = []

    for required_skill in required_skills:
        has_skill = any(
            skill_matches(user_skill, required_skill)
            for user_skill in user_skills
        )

        if has_skill:
            matched_skills.append(required_skill)
        else:
            missing_skills.append(required_skill)

    return {
        "matched_skills": matched_skills,
        "missing_skills": missing_skills
    }


def build_skill_gap_action_plan(missing_skills: list[str]) -> list[str]:
    """Build a simple action plan from missing skills."""
    if not missing_skills:
        return [
            "Step 1: Build a portfolio project for your target role",
            "Step 2: Practice interview questions and explain your projects",
            "Step 3: Apply to 5 relevant jobs this week"
        ]

    return [
        f"Step 1: Start with {missing_skills[0]} and learn the fundamentals",
        "Step 2: Practice with small exercises or mini tasks",
        "Step 3: Build one project feature using your missing skills"
    ]


def get_skill_gap_analysis(role: str, user_skills: list[str]) -> dict[str, Any]:
    """Return complete skill gap analysis for a target role."""
    cleaned_user_skills = [
        skill.strip()
        for skill in user_skills
        if skill.strip()
    ]
    required_skills = get_required_skills(role)
    gap_result = analyze_skill_gap(cleaned_user_skills, required_skills)

    return {
        "target_role": role,
        "required_skills": required_skills,
        "user_skills": cleaned_user_skills,
        "matched_skills": gap_result["matched_skills"],
        "missing_skills": gap_result["missing_skills"],
        "action_plan": build_skill_gap_action_plan(gap_result["missing_skills"])
    }


def get_job_recommendation_response(
    role: str,
    user_skills: list[str]
) -> dict[str, Any]:
    """Return job recommendations and skill gap analysis."""
    jobs = fetch_jobs()
    matched_jobs = filter_jobs(jobs, role)

    return {
        "target_role": role,
        "jobs": matched_jobs,
        "skill_gap_analysis": get_skill_gap_analysis(role, user_skills)
    }
