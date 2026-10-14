import argparse
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from superhuman.core.orchestrator import run_superhuman_task
from superhuman.core.router import route_task


DB_PATH = Path("data") / "superhuman.db"


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT,
                agent TEXT,
                title TEXT NOT NULL,
                details TEXT,
                status TEXT NOT NULL,
                output_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    print("Superhuman OS database initialized.")


def add_task(project, title, details):
    route = route_task(title, details)
    now = datetime.now().isoformat(timespec="seconds")

    selected_project = project if project else route.workstream

    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tasks
            (project, agent, title, details, status, output_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                selected_project,
                route.agent,
                title,
                details,
                "pending",
                None,
                now,
                now,
            ),
        )
        task_id = cursor.lastrowid

    print(f"Task #{task_id} created.")
    print(f"Workstream: {selected_project}")
    print(f"Agent: {route.agent}")
    print(f"Approval required: {route.approval_required}")


def list_tasks():
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, project, agent, title, status, updated_at
            FROM tasks
            ORDER BY id DESC
            """
        ).fetchall()

    if not rows:
        print("No tasks found.")
        return

    for row in rows:
        task_id, project, agent, title, status, updated_at = row
        print(f"#{task_id} [{status}] {project} / {agent} - {title} ({updated_at})")


def show_task(task_id):
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, project, agent, title, details, status, output_path, created_at, updated_at
            FROM tasks
            WHERE id = ?
            """,
            (task_id,),
        ).fetchone()

    if not row:
        print(f"Task #{task_id} not found.")
        return

    (
        task_id,
        project,
        agent,
        title,
        details,
        status,
        output_path,
        created_at,
        updated_at,
    ) = row

    print(f"Task #{task_id}")
    print(f"Project: {project}")
    print(f"Agent: {agent}")
    print(f"Title: {title}")
    print(f"Details: {details}")
    print(f"Status: {status}")
    print(f"Output path: {output_path}")
    print(f"Created: {created_at}")
    print(f"Updated: {updated_at}")

    if output_path and Path(output_path).exists():
        print("\n--- Output preview ---\n")
        content = Path(output_path).read_text(encoding="utf-8")
        print(content[:3000])


def run_task(task_id):
    load_dotenv()

    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, title, details
            FROM tasks
            WHERE id = ?
            """,
            (task_id,),
        ).fetchone()

    if not row:
        print(f"Task #{task_id} not found.")
        return

    _, title, details = row

    result = run_superhuman_task(task_id=task_id, title=title, details=details or "")
    route = result["route"]
    now = datetime.now().isoformat(timespec="seconds")

    with connect() as conn:
        conn.execute(
            """
            UPDATE tasks
            SET project = ?, agent = ?, status = ?, output_path = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                route.workstream,
                route.agent,
                result["status"],
                result["output_path"],
                now,
                task_id,
            ),
        )

    print(f"Task #{task_id} completed with status: {result['status']}")
    print(f"Workstream: {route.workstream}")
    print(f"Agent: {route.agent}")
    print(f"Output: {result['output_path']}")


def route_preview(title, details):
    route = route_task(title, details)
    print("Routing preview")
    print(f"Workstream: {route.workstream}")
    print(f"Agent: {route.agent}")
    print(f"Risk level: {route.risk_level}")
    print(f"Approval required: {route.approval_required}")
    print(f"Reason: {route.reason}")


def auto_task(title, details):
    init_db()
    add_task(None, title, details)

    with connect() as conn:
        task_id = conn.execute("SELECT MAX(id) FROM tasks").fetchone()[0]

    run_task(task_id)


def main():
    parser = argparse.ArgumentParser(description="Superhuman OS command line interface")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init")

    add = sub.add_parser("add")
    add.add_argument("--project", default=None)
    add.add_argument("--title", required=True)
    add.add_argument("--details", default="")

    sub.add_parser("list")

    show = sub.add_parser("show")
    show.add_argument("task_id", type=int)

    run = sub.add_parser("run")
    run.add_argument("task_id", type=int)

    route = sub.add_parser("route")
    route.add_argument("--title", required=True)
    route.add_argument("--details", default="")

    auto = sub.add_parser("auto")
    auto.add_argument("title")
    auto.add_argument("--details", default="")

    args = parser.parse_args()

    if args.command == "init":
        init_db()
    elif args.command == "add":
        init_db()
        add_task(args.project, args.title, args.details)
    elif args.command == "list":
        init_db()
        list_tasks()
    elif args.command == "show":
        init_db()
        show_task(args.task_id)
    elif args.command == "run":
        init_db()
        run_task(args.task_id)
    elif args.command == "route":
        route_preview(args.title, args.details)
    elif args.command == "auto":
        auto_task(args.title, args.details)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()