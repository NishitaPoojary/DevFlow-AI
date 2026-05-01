import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import random
import json
import os
import requests

# ----------------------------
# CONFIG
# ----------------------------
from dotenv import load_dotenv
load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# ----------------------------
# DATABASE SETUP
# ----------------------------
conn = sqlite3.connect("project.db", check_same_thread=False)
cursor = conn.cursor()

cursor.executescript("""
CREATE TABLE IF NOT EXISTS developers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    skill TEXT,
    workload INTEGER,
    performance INTEGER,
    tasks_completed INTEGER DEFAULT 0,
    ai_usage_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    skill TEXT,
    priority TEXT,
    hours INTEGER,
    assigned_to TEXT DEFAULT 'Unassigned',
    status TEXT DEFAULT 'Pending',
    phase TEXT DEFAULT 'Planning',
    created_at TEXT,
    completed_at TEXT,
    ai_assisted INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ai_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    developer TEXT,
    task_id INTEGER,
    prompt TEXT,
    response TEXT,
    phase TEXT
);

CREATE TABLE IF NOT EXISTS workflow_phases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    phase TEXT,
    started_at TEXT,
    completed_at TEXT,
    notes TEXT
);
""")
conn.commit()

# ----------------------------
# GROQ AI HELPER
# ----------------------------
def call_groq(prompt: str, system: str = "You are an expert software engineering assistant.") -> str:
    if not GROQ_API_KEY:
        return _mock_ai_response(prompt)
    try:
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 800,
            "temperature": 0.7
        }
        resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return _mock_ai_response(prompt)

def _mock_ai_response(prompt: str) -> str:
    """Intelligent mock responses based on prompt keywords."""
    prompt_lower = prompt.lower()

    if "break" in prompt_lower or "subtask" in prompt_lower or "breakdown" in prompt_lower:
        project_name = "the project"
        for word in prompt.split():
            if len(word) > 4 and word.istitle():
                project_name = word
                break
        return f"""Here are the recommended subtasks for {project_name}:

**Phase 1 - Planning**
1. Requirements Gathering & Stakeholder Interviews
2. System Architecture Design
3. Technology Stack Finalization
4. Project Timeline & Milestone Planning

**Phase 2 - Development**
5. Database Schema Design & Setup
6. Backend API Development (REST/GraphQL)
7. Authentication & Authorization Module
8. Frontend UI/UX Implementation
9. Third-party Integrations

**Phase 3 - Testing**
10. Unit Testing (80%+ coverage target)
11. Integration Testing
12. Performance & Load Testing
13. Security Audit

**Phase 4 - Feedback & Deploy**
14. User Acceptance Testing (UAT)
15. Bug Fixes & Iteration
16. CI/CD Pipeline Setup
17. Production Deployment & Monitoring

*Estimated total: 120–160 hours for a team of 4*"""

    elif "risk" in prompt_lower or "bottleneck" in prompt_lower:
        return """**Risk Analysis:**
- 🔴 High Risk: 2 developers overloaded (>80% workload)
- 🟡 Medium Risk: Testing phase has no dedicated resource
- 🟢 Low Risk: Frontend tasks well distributed

**Bottlenecks Detected:**
- Backend API tasks queued behind database design
- Single developer handling both auth + API modules

**Recommendations:**
- Redistribute 2 tasks from overloaded devs
- Assign dedicated QA resource for testing phase
- Parallelize frontend and backend where possible"""

    elif "improve" in prompt_lower or "productiv" in prompt_lower:
        return """**Productivity Improvement Suggestions:**

1. **Time Blocking**: Schedule deep work sessions (2-3hr blocks) for complex tasks
2. **AI-Assisted Code Review**: Use AI to catch common bugs before peer review
3. **Daily Standups**: 15-min syncs to surface blockers early
4. **Task Batching**: Group similar skill tasks for context efficiency
5. **Performance Incentives**: Recognize top performers weekly

*Estimated productivity gain: 20-35% with consistent application*"""

    else:
        return f"""Based on the engineering context provided:

**Analysis Complete** ✅

Key observations:
- The task requires careful planning and modular execution
- AI assistance can reduce implementation time by ~30%
- Recommend breaking into 3-5 day sprints

**Action Items:**
1. Define clear acceptance criteria for each subtask
2. Assign based on skill compatibility scores
3. Set up automated testing from day one
4. Schedule daily progress check-ins

*This response was generated using intelligent mock AI (add GROQ_API_KEY for full AI power)*"""

# ----------------------------
# ALLOCATION ENGINE
# ----------------------------
def calculate_allocation_score(task, dev):
    """
    Weighted scoring:
    - Skill match:       50 pts
    - Low workload:      30 pts (normalized)
    - High performance:  20 pts (normalized)
    """
    score = 0
    task_skill = task[2].lower() if task[2] else ""
    dev_skills = dev[2].lower() if dev[2] else ""

    # Skill match (partial match supported)
    if task_skill and task_skill in dev_skills:
        score += 50
    elif task_skill and any(s.strip() in dev_skills for s in task_skill.split(",")):
        score += 25  # partial match

    # Workload (lower = better): 0 workload → 30 pts, 100 workload → 0 pts
    workload = dev[3] if dev[3] is not None else 50
    score += (100 - workload) * 0.30

    # Performance (higher = better): 100 perf → 20 pts
    performance = dev[4] if dev[4] is not None else 50
    score += performance * 0.20

    return round(score, 2)

def auto_allocate_tasks():
    devs = cursor.execute("SELECT * FROM developers").fetchall()
    tasks = cursor.execute("SELECT * FROM tasks WHERE assigned_to='Unassigned'").fetchall()

    if not devs or not tasks:
        return [], "No developers or unassigned tasks found."

    allocated = []
    for task in tasks:
        best_dev = None
        best_score = -1
        scores = []

        for dev in devs:
            score = calculate_allocation_score(task, dev)
            scores.append((dev[1], score))
            if score > best_score:
                best_score = score
                best_dev = dev

        if best_dev:
            cursor.execute(
                "UPDATE tasks SET assigned_to=?, status='In Progress', phase='Development' WHERE id=?",
                (best_dev[1], task[0])
            )
            # Update developer workload
            new_workload = min(100, best_dev[3] + 10)
            cursor.execute("UPDATE developers SET workload=? WHERE id=?", (new_workload, best_dev[0]))
            allocated.append({
                "Task": task[1],
                "Assigned To": best_dev[1],
                "Score": best_score,
                "Skill Match": "✅" if task[2].lower() in best_dev[2].lower() else "⚠️"
            })

    conn.commit()
    return allocated, None

# ----------------------------
# SEED SAMPLE DATA
# ----------------------------
def seed_sample_data():
    existing = cursor.execute("SELECT COUNT(*) FROM developers").fetchone()[0]
    if existing > 0:
        return False

    developers = [
        ("Alice Chen", "Python, FastAPI, SQL", 45, 88, 12, 8),
        ("Bob Kumar", "React, JavaScript, CSS", 60, 75, 9, 5),
        ("Carol Singh", "Python, Machine Learning, SQL", 30, 92, 15, 12),
        ("David Park", "React, Node.js, JavaScript", 75, 70, 7, 3),
        ("Eva Martinez", "SQL, PostgreSQL, Data Engineering", 50, 85, 11, 7),
    ]
    cursor.executemany(
        "INSERT INTO developers(name, skill, workload, performance, tasks_completed, ai_usage_count) VALUES(?,?,?,?,?,?)",
        developers
    )

    tasks_data = [
        ("User Authentication Module", "Python", "High", 16, "Alice Chen", "In Progress", "Development"),
        ("Dashboard UI Components", "React", "High", 20, "Bob Kumar", "In Progress", "Development"),
        ("ML Recommendation Engine", "Machine Learning", "High", 40, "Carol Singh", "In Progress", "Development"),
        ("Database Schema Optimization", "SQL", "Medium", 12, "Eva Martinez", "Completed", "Feedback"),
        ("REST API Endpoints", "Python", "High", 24, "Alice Chen", "In Progress", "Development"),
        ("Mobile Responsive Layout", "React", "Medium", 10, "David Park", "Pending", "Planning"),
        ("Data Pipeline Setup", "Data Engineering", "Medium", 18, "Eva Martinez", "In Progress", "Testing"),
        ("Unit Test Suite", "Python", "Low", 8, "Unassigned", "Pending", "Planning"),
        ("Performance Optimization", "JavaScript", "Medium", 14, "Unassigned", "Pending", "Planning"),
        ("CI/CD Pipeline", "Python", "Low", 6, "Unassigned", "Pending", "Planning"),
    ]

    now = datetime.now()
    for i, t in enumerate(tasks_data):
        created = (now - timedelta(days=random.randint(1, 14))).strftime("%Y-%m-%d %H:%M")
        completed = (now - timedelta(days=random.randint(0, 3))).strftime("%Y-%m-%d %H:%M") if t[6] == "Completed" else None
        cursor.execute(
            "INSERT INTO tasks(title, skill, priority, hours, assigned_to, status, phase, created_at, completed_at, ai_assisted) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (*t, created, completed, random.randint(0, 1))
        )

    ai_logs_data = [
        (datetime.now().strftime("%Y-%m-%d %H:%M"), "Alice Chen", 1, "How to implement JWT auth in FastAPI?", "Here's a complete JWT implementation...", "Development"),
        (datetime.now().strftime("%Y-%m-%d %H:%M"), "Carol Singh", 3, "Optimize this ML model for lower latency", "Consider quantization and caching...", "Development"),
        (datetime.now().strftime("%Y-%m-%d %H:%M"), "Bob Kumar", 2, "Best React patterns for dashboard components?", "Use compound components pattern...", "Development"),
        (datetime.now().strftime("%Y-%m-%d %H:%M"), "Alice Chen", 5, "Debug this API endpoint 500 error", "The issue is in your middleware chain...", "Testing"),
        (datetime.now().strftime("%Y-%m-%d %H:%M"), "Carol Singh", 3, "Feature engineering ideas for recommendations", "Consider user-item interaction matrix...", "Development"),
    ]
    cursor.executemany(
        "INSERT INTO ai_logs(timestamp, developer, task_id, prompt, response, phase) VALUES(?,?,?,?,?,?)",
        ai_logs_data
    )

    conn.commit()
    return True

# ----------------------------
# PAGE CONFIG
# ----------------------------
st.set_page_config(
    page_title="DevFlow AI",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    [data-testid="stSidebar"] { background: #0f172a; }
    [data-testid="stSidebar"] * { color: #e2e8f0 !important; }
    .metric-card {
        background: linear-gradient(135deg, #1e293b, #0f172a);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        color: white;
    }
    .phase-badge {
        display: inline-block;
        padding: 3px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
    }
    .stButton > button {
        background: linear-gradient(135deg, #3b82f6, #1d4ed8);
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: 600;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #2563eb, #1e40af);
        transform: translateY(-1px);
    }
</style>
""", unsafe_allow_html=True)

# ----------------------------
# SIDEBAR
# ----------------------------
with st.sidebar:
    st.markdown("## ⚙️ DevFlow AI")
    st.markdown("*Engineering Workflow Optimizer*")
    st.markdown("---")

    menu = st.radio(
        "Navigate",
        ["🏠 Home", "👨‍💻 Developers", "📋 Tasks", "🤖 AI Breakdown",
         "⚡ Auto Allocate", "📊 Dashboard", "🔍 AI Insights"],
        label_visibility="collapsed"
    )

    st.markdown("---")
    api_key_input = st.text_input("🔑 Groq API Key (optional)", type="password",
                                   help="Get free key at console.groq.com")
    if api_key_input:
        GROQ_API_KEY = api_key_input

    st.markdown("---")
    if st.button("🌱 Load Sample Data"):
        seeded = seed_sample_data()
        if seeded:
            st.success("Sample data loaded!")
            st.rerun()
        else:
            st.info("Data already exists.")

    ai_status = "🟢 AI Active" if GROQ_API_KEY else "🟡 Mock AI Mode"
    st.markdown(f"**Status:** {ai_status}")

# ----------------------------
# HOME
# ----------------------------
if menu == "🏠 Home":
    st.title("⚙️ DevFlow AI")
    st.markdown("### AI-Powered Engineering Workflow & Resource Optimization")
    st.markdown("---")

    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("""
        #### What this system does:
        - 🗂️ **Workflow Engine** — Phases: Planning → Development → Testing → Feedback
        - 🤖 **AI Task Breakdown** — Intelligent project decomposition
        - ⚡ **Smart Allocation** — Assigns tasks based on skill, workload & performance scoring
        - 📊 **Real-time Dashboard** — KPIs, bottlenecks, and risk detection
        - 🔍 **AI Insights** — Productivity analysis and recommendations
        """)

    with col2:
        devs = cursor.execute("SELECT COUNT(*) FROM developers").fetchone()[0]
        tasks = cursor.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        ai_logs = cursor.execute("SELECT COUNT(*) FROM ai_logs").fetchone()[0]

        st.metric("👨‍💻 Developers", devs)
        st.metric("📋 Total Tasks", tasks)
        st.metric("🤖 AI Interactions", ai_logs)

    st.markdown("---")
    st.info("👈 Use the sidebar to navigate. Start by clicking **Load Sample Data** to see a demo!")

# ----------------------------
# DEVELOPERS
# ----------------------------
elif menu == "👨‍💻 Developers":
    st.title("👨‍💻 Developer Management")
    tab1, tab2 = st.tabs(["Add Developer", "View All"])

    with tab1:
        with st.form("dev_form"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Developer Name")
                skill = st.text_input("Skills (Python, React, SQL...)")
            with col2:
                workload = st.slider("Current Workload %", 0, 100, 30)
                performance = st.slider("Performance Score", 0, 100, 75)

            if st.form_submit_button("➕ Add Developer"):
                if name and skill:
                    cursor.execute(
                        "INSERT INTO developers(name, skill, workload, performance) VALUES(?,?,?,?)",
                        (name, skill, workload, performance)
                    )
                    conn.commit()
                    st.success(f"Developer **{name}** added!")
                else:
                    st.error("Name and skill are required.")

    with tab2:
        df = pd.read_sql_query("SELECT * FROM developers", conn)
        if len(df) == 0:
            st.info("No developers yet. Add some or load sample data.")
        else:
            # Color workload
            st.dataframe(
                df,
                column_config={
                    "workload": st.column_config.ProgressColumn("Workload %", min_value=0, max_value=100),
                    "performance": st.column_config.ProgressColumn("Performance", min_value=0, max_value=100),
                },
                use_container_width=True
            )

            # Quick chart
            fig = px.scatter(df, x="workload", y="performance",
                             text="name", color="performance",
                             color_continuous_scale="RdYlGn",
                             title="Developer Workload vs Performance",
                             labels={"workload": "Workload %", "performance": "Performance Score"})
            fig.update_traces(textposition="top center", marker_size=12)
            st.plotly_chart(fig, use_container_width=True)

# ----------------------------
# TASKS
# ----------------------------
elif menu == "📋 Tasks":
    st.title("📋 Task Management")
    tab1, tab2, tab3 = st.tabs(["Create Task", "View All", "Update Status"])

    with tab1:
        with st.form("task_form"):
            col1, col2 = st.columns(2)
            with col1:
                title = st.text_input("Task Title")
                skill = st.text_input("Required Skill")
            with col2:
                priority = st.selectbox("Priority", ["High", "Medium", "Low"])
                hours = st.number_input("Estimated Hours", 1, 200, 8)
                phase = st.selectbox("Phase", ["Planning", "Development", "Testing", "Feedback"])

            if st.form_submit_button("➕ Create Task"):
                if title and skill:
                    cursor.execute(
                        "INSERT INTO tasks(title, skill, priority, hours, assigned_to, status, phase, created_at) VALUES(?,?,?,?,?,?,?,?)",
                        (title, skill, priority, hours, "Unassigned", "Pending", phase, datetime.now().strftime("%Y-%m-%d %H:%M"))
                    )
                    conn.commit()
                    st.success(f"Task **{title}** created!")
                else:
                    st.error("Title and skill are required.")

    with tab2:
        df = pd.read_sql_query("SELECT * FROM tasks", conn)
        if len(df) == 0:
            st.info("No tasks yet.")
        else:
            # Filter
            status_filter = st.multiselect("Filter by Status", df["status"].unique().tolist(), default=df["status"].unique().tolist())
            filtered = df[df["status"].isin(status_filter)]

            st.dataframe(
                filtered[["id", "title", "skill", "priority", "hours", "assigned_to", "status", "phase"]],
                column_config={
                    "priority": st.column_config.SelectboxColumn("Priority", options=["High", "Medium", "Low"]),
                },
                use_container_width=True
            )

    with tab3:
        tasks_df = pd.read_sql_query("SELECT id, title, status, phase FROM tasks", conn)
        if len(tasks_df) > 0:
            task_options = {f"{row['title']} (#{row['id']})": row['id'] for _, row in tasks_df.iterrows()}
            selected_task_name = st.selectbox("Select Task", list(task_options.keys()))
            selected_task_id = task_options[selected_task_name]

            col1, col2 = st.columns(2)
            with col1:
                new_status = st.selectbox("New Status", ["Pending", "In Progress", "Completed", "Blocked"])
            with col2:
                new_phase = st.selectbox("New Phase", ["Planning", "Development", "Testing", "Feedback"])

            if st.button("Update Task"):
                completed_at = datetime.now().strftime("%Y-%m-%d %H:%M") if new_status == "Completed" else None
                cursor.execute(
                    "UPDATE tasks SET status=?, phase=?, completed_at=? WHERE id=?",
                    (new_status, new_phase, completed_at, selected_task_id)
                )
                conn.commit()
                st.success("Task updated!")

# ----------------------------
# AI BREAKDOWN
# ----------------------------
elif menu == "🤖 AI Breakdown":
    st.title("🤖 AI Project Task Breakdown")
    st.markdown("*Use AI to decompose your project into structured, phase-based subtasks*")

    col1, col2 = st.columns([2, 1])
    with col1:
        project = st.text_input("Project Name", placeholder="e.g. E-Commerce Platform")
        description = st.text_area("Project Description (optional)", placeholder="Describe the project scope...", height=100)
    with col2:
        team_size = st.number_input("Team Size", 1, 20, 4)
        tech_stack = st.text_input("Tech Stack", placeholder="React, Python, PostgreSQL")

    if st.button("🚀 Generate AI Breakdown", use_container_width=True):
        if project:
            with st.spinner("AI is analyzing your project..."):
                prompt = f"""
You are a senior software engineering manager. Break down the following project into detailed, actionable subtasks organized by development phase.

Project: {project}
Description: {description or 'Not provided'}
Team Size: {team_size}
Tech Stack: {tech_stack or 'Not specified'}

Provide subtasks organized under these phases:
1. Planning
2. Development
3. Testing
4. Feedback/Deployment

For each subtask include estimated hours and required skill. Format clearly.
"""
                response = call_groq(prompt)

                # Log AI interaction
                cursor.execute(
                    "INSERT INTO ai_logs(timestamp, developer, task_id, prompt, response, phase) VALUES(?,?,?,?,?,?)",
                    (datetime.now().strftime("%Y-%m-%d %H:%M"), "System", 0, prompt[:200], response[:500], "Planning")
                )
                conn.commit()

            st.markdown("### 📋 AI-Generated Task Breakdown")
            st.markdown(response)

            # Option to auto-create tasks from breakdown
            st.markdown("---")
            if st.button("➕ Auto-Create These Tasks in System"):
                default_tasks = [
                    ("Requirements Gathering", "Planning", "High", 8),
                    ("System Architecture Design", "Planning", "High", 12),
                    ("Database Schema Design", "Development", "High", 10),
                    ("Backend API Development", "Development", "High", 30),
                    ("Frontend Implementation", "Development", "High", 25),
                    ("Authentication Module", "Development", "High", 12),
                    ("Unit Testing", "Testing", "Medium", 10),
                    ("Integration Testing", "Testing", "Medium", 8),
                    ("Performance Testing", "Testing", "Low", 6),
                    ("CI/CD Setup", "Feedback", "Medium", 8),
                    ("Deployment", "Feedback", "High", 6),
                ]
                for t in default_tasks:
                    cursor.execute(
                        "INSERT INTO tasks(title, skill, priority, hours, assigned_to, status, phase, created_at, ai_assisted) VALUES(?,?,?,?,?,?,?,?,?)",
                        (t[0], tech_stack.split(",")[0].strip() if tech_stack else "General",
                         t[2], t[3], "Unassigned", "Pending", t[1],
                         datetime.now().strftime("%Y-%m-%d %H:%M"), 1)
                    )
                conn.commit()
                st.success(f"✅ {len(default_tasks)} tasks created from AI breakdown!")
        else:
            st.error("Please enter a project name.")

# ----------------------------
# AUTO ALLOCATE
# ----------------------------
elif menu == "⚡ Auto Allocate":
    st.title("⚡ Smart Task Allocation Engine")

    col1, col2, col3 = st.columns(3)
    devs_count = cursor.execute("SELECT COUNT(*) FROM developers").fetchone()[0]
    unassigned = cursor.execute("SELECT COUNT(*) FROM tasks WHERE assigned_to='Unassigned'").fetchone()[0]
    assigned = cursor.execute("SELECT COUNT(*) FROM tasks WHERE assigned_to!='Unassigned'").fetchone()[0]

    col1.metric("👨‍💻 Developers", devs_count)
    col2.metric("📋 Unassigned Tasks", unassigned)
    col3.metric("✅ Already Assigned", assigned)

    st.markdown("---")
    st.markdown("""
    #### Allocation Scoring Algorithm:
    | Factor | Weight | Logic |
    |--------|--------|-------|
    | Skill Match | 50 pts | Full match = 50, Partial = 25 |
    | Low Workload | 30 pts | (100 - workload%) × 0.3 |
    | High Performance | 20 pts | performance × 0.2 |
    """)

    if st.button("🚀 Run Auto Allocation", use_container_width=True):
        if devs_count == 0:
            st.error("Add developers first.")
        elif unassigned == 0:
            st.info("No unassigned tasks to allocate.")
        else:
            with st.spinner("Running allocation algorithm..."):
                allocated, error = auto_allocate_tasks()

            if error:
                st.error(error)
            elif allocated:
                st.success(f"✅ {len(allocated)} tasks allocated successfully!")
                alloc_df = pd.DataFrame(allocated)
                st.dataframe(alloc_df, use_container_width=True)

                # Visual breakdown
                fig = px.bar(alloc_df, x="Assigned To", title="Tasks Allocated Per Developer",
                             color="Score", color_continuous_scale="Blues")
                st.plotly_chart(fig, use_container_width=True)

# ----------------------------
# DASHBOARD
# ----------------------------
elif menu == "📊 Dashboard":
    st.title("📊 Real-Time Project Dashboard")

    tasks_df = pd.read_sql_query("SELECT * FROM tasks", conn)
    dev_df = pd.read_sql_query("SELECT * FROM developers", conn)
    ai_df = pd.read_sql_query("SELECT * FROM ai_logs", conn)

    if len(tasks_df) == 0:
        st.warning("No data yet. Load sample data from the sidebar.")
        st.stop()

    # --- KPI ROW ---
    total = len(tasks_df)
    completed = len(tasks_df[tasks_df["status"] == "Completed"])
    in_progress = len(tasks_df[tasks_df["status"] == "In Progress"])
    pending = len(tasks_df[tasks_df["status"] == "Pending"])
    blocked = len(tasks_df[tasks_df["status"] == "Blocked"]) if "Blocked" in tasks_df["status"].values else 0
    ai_assisted = len(tasks_df[tasks_df["ai_assisted"] == 1])
    completion_rate = round((completed / total) * 100, 1) if total > 0 else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("📋 Total Tasks", total)
    c2.metric("✅ Completed", completed, f"{completion_rate}%")
    c3.metric("🔄 In Progress", in_progress)
    c4.metric("⏳ Pending", pending)
    c5.metric("🤖 AI-Assisted", ai_assisted)

    st.markdown("---")

    # --- ROW 1: Status + Phase ---
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Task Status Distribution")
        fig1 = px.pie(tasks_df, names="status", hole=0.45,
                      color_discrete_sequence=px.colors.qualitative.Set3)
        fig1.update_layout(margin=dict(t=0, b=0))
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        st.markdown("#### Tasks by Workflow Phase")
        phase_counts = tasks_df["phase"].value_counts().reset_index()
        phase_counts.columns = ["Phase", "Count"]
        fig2 = px.funnel(phase_counts, x="Count", y="Phase",
                         color_discrete_sequence=["#3b82f6"])
        st.plotly_chart(fig2, use_container_width=True)

    # --- ROW 2: Workload + Priority ---
    col3, col4 = st.columns(2)

    with col3:
        st.markdown("#### Developer Workload")
        if len(dev_df) > 0:
            dev_df["color"] = dev_df["workload"].apply(
                lambda x: "🔴 Overloaded" if x > 75 else ("🟡 Busy" if x > 50 else "🟢 Available")
            )
            fig3 = px.bar(dev_df, x="name", y="workload",
                          color="color",
                          color_discrete_map={"🔴 Overloaded": "#ef4444", "🟡 Busy": "#f59e0b", "🟢 Available": "#22c55e"},
                          text="workload")
            fig3.update_traces(textposition="outside")
            fig3.update_layout(showlegend=True, yaxis_range=[0, 110])
            st.plotly_chart(fig3, use_container_width=True)

    with col4:
        st.markdown("#### Tasks by Priority")
        priority_df = tasks_df.groupby(["priority", "status"]).size().reset_index(name="count")
        fig4 = px.bar(priority_df, x="priority", y="count", color="status",
                      barmode="stack",
                      color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig4, use_container_width=True)

    # --- ROW 3: AI Usage + Dev Performance ---
    col5, col6 = st.columns(2)

    with col5:
        st.markdown("#### AI Interaction Logs")
        if len(ai_df) > 0:
            ai_phase = ai_df.groupby("phase").size().reset_index(name="count")
            fig5 = px.bar(ai_phase, x="phase", y="count",
                          title="AI Usage by Phase",
                          color="count", color_continuous_scale="Blues")
            st.plotly_chart(fig5, use_container_width=True)
        else:
            st.info("No AI interactions logged yet.")

    with col6:
        st.markdown("#### Developer Performance vs Workload")
        if len(dev_df) > 0:
            fig6 = px.scatter(dev_df, x="workload", y="performance",
                              size="tasks_completed" if "tasks_completed" in dev_df.columns else None,
                              text="name", color="performance",
                              color_continuous_scale="RdYlGn",
                              labels={"workload": "Workload %", "performance": "Performance Score"})
            fig6.update_traces(textposition="top center")
            st.plotly_chart(fig6, use_container_width=True)

    # --- RISK & BOTTLENECK ---
    st.markdown("---")
    st.markdown("#### ⚠️ Risk & Bottleneck Alerts")

    alerts = []
    if len(dev_df) > 0:
        overloaded = dev_df[dev_df["workload"] > 75]
        for _, d in overloaded.iterrows():
            alerts.append(("🔴 HIGH", f"{d['name']} is overloaded ({d['workload']}% workload)"))

    if blocked > 0:
        alerts.append(("🔴 HIGH", f"{blocked} task(s) are BLOCKED — needs immediate attention"))

    if pending > total * 0.4:
        alerts.append(("🟡 MEDIUM", f"High pending task ratio ({pending}/{total}) — consider rebalancing"))

    if len(tasks_df[tasks_df["assigned_to"] == "Unassigned"]) > 0:
        alerts.append(("🟡 MEDIUM", f"{len(tasks_df[tasks_df['assigned_to'] == 'Unassigned'])} tasks are unassigned"))

    if not alerts:
        st.success("✅ No critical risks detected. Team is well-balanced!")
    else:
        for level, msg in alerts:
            if "HIGH" in level:
                st.error(f"{level}: {msg}")
            else:
                st.warning(f"{level}: {msg}")

# ----------------------------
# AI INSIGHTS
# ----------------------------
elif menu == "🔍 AI Insights":
    st.title("🔍 AI-Powered Insights")
    st.markdown("*Ask AI anything about your team, tasks, or project health*")

    insight_type = st.selectbox("Choose Insight Type", [
        "Identify Bottlenecks & Risks",
        "Productivity Improvement Tips",
        "Task Rebalancing Recommendations",
        "AI Usage Analysis",
        "Custom Question"
    ])

    custom_q = ""
    if insight_type == "Custom Question":
        custom_q = st.text_area("Ask anything about your project...", height=100)

    if st.button("🤖 Generate Insight", use_container_width=True):
        tasks_df = pd.read_sql_query("SELECT * FROM tasks", conn)
        dev_df = pd.read_sql_query("SELECT * FROM developers", conn)

        context = f"""
Current Team Data:
- {len(dev_df)} developers
- {len(tasks_df)} total tasks
- {len(tasks_df[tasks_df['status']=='Completed'])} completed
- {len(tasks_df[tasks_df['status']=='In Progress'])} in progress
- {len(tasks_df[tasks_df['assigned_to']=='Unassigned'])} unassigned

Developer Workloads: {', '.join([f"{r['name']}:{r['workload']}%" for _, r in dev_df.iterrows()]) if len(dev_df) > 0 else 'No data'}
"""

        prompts = {
            "Identify Bottlenecks & Risks": f"{context}\n\nIdentify all bottlenecks, risks, and critical path issues. Be specific and actionable.",
            "Productivity Improvement Tips": f"{context}\n\nSuggest concrete productivity improvements for this team. Include AI tooling suggestions.",
            "Task Rebalancing Recommendations": f"{context}\n\nRecommend how to rebalance the workload. Which tasks should be moved between developers and why?",
            "AI Usage Analysis": f"{context}\n\nAnalyze the AI usage patterns and suggest how AI can be better leveraged in this workflow.",
        }

        prompt = custom_q if insight_type == "Custom Question" else prompts[insight_type]

        with st.spinner("AI is analyzing..."):
            response = call_groq(prompt, system="You are an expert engineering manager and AI optimization consultant.")

            cursor.execute(
                "INSERT INTO ai_logs(timestamp, developer, task_id, prompt, response, phase) VALUES(?,?,?,?,?,?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M"), "Manager", 0, prompt[:200], response[:500], "Analysis")
            )
            conn.commit()

        st.markdown("### 🤖 AI Analysis")
        st.markdown(response)

    # Show AI interaction history
    st.markdown("---")
    st.markdown("#### 📜 Recent AI Interaction History")
    ai_df = pd.read_sql_query("SELECT timestamp, developer, phase, prompt FROM ai_logs ORDER BY id DESC LIMIT 10", conn)
    if len(ai_df) > 0:
        ai_df["prompt"] = ai_df["prompt"].str[:80] + "..."
        st.dataframe(ai_df, use_container_width=True)
    else:
        st.info("No AI interactions logged yet.")