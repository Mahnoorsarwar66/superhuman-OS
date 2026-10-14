from superhuman.memory.store import context_for
import os
from datetime import datetime
from pathlib import Path

from openai import OpenAI

from superhuman.agents.registry import get_agent_prompt
from superhuman.core.router import route_task


OUTPUT_DIR = Path("data") / "outputs"


def run_superhuman_task(task_id: int, title: str, details: str = "") -> dict:
    route = route_task(title, details)

    if route.approval_required:
        return {
            "status": "needs_approval",
            "route": route,
            "output_path": None,
            "content": (
                "This task appears to involve an external or consequential action. "
                "Superhuman OS will not execute it without explicit approval."
            ),
        }

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found in .env")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)

    system_prompt = get_agent_prompt(route.agent)

    user_prompt = f"""
You are working inside Superhuman OS for Mahnoor Sarwar.

Task ID: {task_id}
Task title: {title}
Task details: {details}

Routing decision:
- Workstream: {route.workstream}
- Agent: {route.agent}
- Risk level: {route.risk_level}
- Approval required: {route.approval_required}
- Routing reason: {route.reason}

Reference context for this workstream:
{context_for(route.workstream)}

Produce a useful first deliverable.

Required format:
1. Executive summary
2. What I understood
3. Recommended approach
4. Detailed output
5. Missing information or assumptions
6. Next best actions for Mahnoor
7. Quality check before human review

Important:
- Do not claim to have performed external actions.
- Do not invent sources or statistics.
- If research is needed, say exactly what needs to be verified.
- Produce work that can be reviewed, edited, and improved.
"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
    
    )

    content = response.choices[0].message.content

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"task_{task_id}_{route.workstream}_{timestamp}.md"

    output_path.write_text(
        f"# Superhuman OS Task {task_id}\n\n"
        f"## Title\n{title}\n\n"
        f"## Workstream\n{route.workstream}\n\n"
        f"## Agent\n{route.agent}\n\n"
        f"## Risk Level\n{route.risk_level}\n\n"
        f"## Approval Required\n{route.approval_required}\n\n"
        f"## Routing Reason\n{route.reason}\n\n"
        f"---\n\n"
        f"{content}\n",
        encoding="utf-8",
    )

    return {
        "status": "needs_review",
        "route": route,
        "output_path": str(output_path),
        "content": content,
    }
