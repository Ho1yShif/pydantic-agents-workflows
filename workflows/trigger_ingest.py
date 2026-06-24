"""Trigger the ingestion fan-out workflow.

Run by a Render cron job (Workflows have no built-in scheduling) to refresh the
documentation corpus on a cadence. Also handy to run once manually after the
first Workflow deploy to seed the database.

Requires ``RENDER_API_KEY`` and ``WORKFLOW_SLUG`` in the environment.
"""

import os
import sys

from render_sdk import Render


def main() -> None:
    workflow_slug = os.environ.get("WORKFLOW_SLUG")
    if not workflow_slug:
        sys.exit("WORKFLOW_SLUG is not set")

    render = Render()  # reads RENDER_API_KEY from the environment
    task_run = render.workflows.start_task(f"{workflow_slug}/ingest_all", [])
    print(f"Triggered {workflow_slug}/ingest_all -> run {task_run.id}")


if __name__ == "__main__":
    main()
