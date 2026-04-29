import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px

# ----------------------------
# DATABASE
# ----------------------------
conn = sqlite3.connect("project.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS developers(
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
skill TEXT,
workload INTEGER,
performance INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS tasks(
id INTEGER PRIMARY KEY AUTOINCREMENT,
title TEXT,
skill TEXT,
priority TEXT,
hours INTEGER,
assigned_to TEXT,
status TEXT
)
""")

conn.commit()

# ----------------------------
# PAGE CONFIG
# ----------------------------
st.set_page_config(
    page_title="AI Workflow Optimizer",
    page_icon="🚀",
    layout="wide"
)

st.title("🚀 AI Engineering Workflow Optimizer")
st.caption("Smart task allocation • Productivity tracking • Resource optimization")

# ----------------------------
# SIDEBAR
# ----------------------------
menu = st.sidebar.radio(
    "Navigation",
    ["🏠 Home", "👨‍💻 Add Developer", "📌 Add Task", "🤖 Auto Allocate", "📊 Dashboard", "🧠 AI Breakdown"]
)

# ----------------------------
# HOME
# ----------------------------
if menu == "🏠 Home":
    st.subheader("Welcome")
    st.write("""
This system helps software teams:
- Manage developers
- Create tasks
- Automatically assign work
- Track productivity
- Optimize resources
- Use AI to break down projects
    """)

# ----------------------------
# ADD DEVELOPER
# ----------------------------
elif menu == "👨‍💻 Add Developer":
    st.subheader("Add Developer")

    with st.form("dev_form"):
        name = st.text_input("Developer Name")
        skill = st.text_input("Skills (Python, React, SQL...)")
        workload = st.slider("Current Workload %", 0, 100, 30)
        performance = st.slider("Performance Score", 0, 100, 75)

        submit = st.form_submit_button("Add Developer")

        if submit:
            cursor.execute(
                "INSERT INTO developers(name, skill, workload, performance) VALUES(?,?,?,?)",
                (name, skill, workload, performance)
            )
            conn.commit()
            st.success("Developer added successfully!")

    df = pd.read_sql_query("SELECT * FROM developers", conn)
    st.dataframe(df, use_container_width=True)

# ----------------------------
# ADD TASK
# ----------------------------
elif menu == "📌 Add Task":
    st.subheader("Create Task")

    with st.form("task_form"):
        title = st.text_input("Task Title")
        skill = st.text_input("Required Skill")
        priority = st.selectbox("Priority", ["High", "Medium", "Low"])
        hours = st.number_input("Estimated Hours", 1, 100, 5)

        submit = st.form_submit_button("Create Task")

        if submit:
            cursor.execute("""
            INSERT INTO tasks(title, skill, priority, hours, assigned_to, status)
            VALUES(?,?,?,?,?,?)
            """, (title, skill, priority, hours, "Unassigned", "Pending"))
            conn.commit()
            st.success("Task created!")

    df = pd.read_sql_query("SELECT * FROM tasks", conn)
    st.dataframe(df, use_container_width=True)

# ----------------------------
# AUTO ALLOCATION
# ----------------------------
elif menu == "🤖 Auto Allocate":
    st.subheader("Smart Task Allocation")

    devs = cursor.execute("SELECT * FROM developers").fetchall()
    tasks = cursor.execute("SELECT * FROM tasks WHERE assigned_to='Unassigned'").fetchall()

    if len(devs) == 0:
        st.warning("Please add developers first.")

    elif len(tasks) == 0:
        st.info("No unassigned tasks available.")

    else:
        allocated = []

        for task in tasks:
            best_dev = None
            best_score = -1

            for dev in devs:
                score = 0

                # Skill match
                if task[2].lower() in dev[2].lower():
                    score += 50

                # Lower workload better
                score += (100 - dev[3])

                # Higher performance better
                score += dev[4]

                if score > best_score:
                    best_score = score
                    best_dev = dev

            cursor.execute(
                "UPDATE tasks SET assigned_to=? WHERE id=?",
                (best_dev[1], task[0])
            )

            allocated.append((task[1], best_dev[1]))

        conn.commit()

        st.success("Tasks allocated successfully!")

        alloc_df = pd.DataFrame(allocated, columns=["Task", "Assigned To"])
        st.dataframe(alloc_df, use_container_width=True)

# ----------------------------
# DASHBOARD
# ----------------------------
elif menu == "📊 Dashboard":
    st.subheader("Analytics Dashboard")

    tasks_df = pd.read_sql_query("SELECT * FROM tasks", conn)
    dev_df = pd.read_sql_query("SELECT * FROM developers", conn)

    col1, col2, col3 = st.columns(3)

    col1.metric("Total Tasks", len(tasks_df))
    col2.metric("Developers", len(dev_df))
    col3.metric("Pending Tasks", len(tasks_df[tasks_df["status"] == "Pending"]))

    if len(tasks_df) > 0:

        # Status Pie
        fig1 = px.pie(tasks_df, names="status", title="Task Status")
        st.plotly_chart(fig1, use_container_width=True)

        # Tasks per Developer
        fig2 = px.bar(tasks_df, x="assigned_to", title="Tasks Per Developer")
        st.plotly_chart(fig2, use_container_width=True)

    if len(dev_df) > 0:
        fig3 = px.bar(dev_df, x="name", y="workload", title="Developer Workload %")
        st.plotly_chart(fig3, use_container_width=True)

# ----------------------------
# AI BREAKDOWN
# ----------------------------
elif menu == "🧠 AI Breakdown":
    st.subheader("AI Project Task Breakdown")

    project = st.text_input("Enter Project Name")

    if st.button("Generate Breakdown"):

        subtasks = [
            "Requirement Analysis",
            "UI/UX Design",
            "Database Design",
            "Frontend Development",
            "Backend APIs",
            "Authentication Module",
            "Testing & QA",
            "Deployment"
        ]

        st.success(f"Suggested Tasks for {project}")

        for i, task in enumerate(subtasks, 1):
            st.write(f"{i}. {task}")