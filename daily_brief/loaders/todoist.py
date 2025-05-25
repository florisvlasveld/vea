"""
Todoist integration: fetch tasks due on or before the target date.
"""

import logging
from datetime import date, datetime
from itertools import chain
from typing import List, Set, Optional

from todoist_api_python.api import TodoistAPI

logger = logging.getLogger(__name__)


def flatten_items(items) -> List:
    """
    Flatten a nested list of items (used internally).
    """
    return list(chain.from_iterable(
        i if isinstance(i, list) else [i] for i in items
    ))


def get_project_id_by_name(api: TodoistAPI, name: str) -> Optional[str]:
    """
    Retrieve a project ID by its name.
    """
    try:
        raw_projects = list(api.get_projects())
        projects = flatten_items(raw_projects)

        for project in projects:
            if project.name.lower() == name.lower():
                return project.id

        logger.warning(f"No project found with name '{name}'")
        return None
    except Exception as e:
        logger.error("Failed to fetch projects from Todoist", exc_info=e)
        return None


def get_project_and_subproject_ids(api: TodoistAPI, root_project_id: str) -> Set[str]:
    """
    Given a root project ID, return a set containing it and all its subproject IDs.
    """
    try:
        raw_projects = list(api.get_projects())
        projects = flatten_items(raw_projects)
    except Exception as e:
        logger.error("Failed to fetch projects from Todoist", exc_info=e)
        return set()

    project_tree = {p.id: p.parent_id for p in projects}
    all_ids: Set[str] = set()

    def collect_subprojects(pid: str):
        all_ids.add(pid)
        for child_id, parent_id in project_tree.items():
            if parent_id == pid:
                collect_subprojects(child_id)

    collect_subprojects(root_project_id)
    return all_ids


def load_tasks(target_date: date, token: str, project_name: Optional[str] = None) -> List[dict]:
    """
    Load tasks from Todoist that are due on or before the target date.
    Optionally filter by a project name.
    """
    if not token:
        logger.warning("Todoist token not provided; skipping task loading.")
        return []

    api = TodoistAPI(token)

    project_ids: Optional[Set[str]] = None
    if project_name:
        root_project_id = get_project_id_by_name(api, project_name)
        if not root_project_id:
            return []
        project_ids = get_project_and_subproject_ids(api, root_project_id)

    try:
        raw_tasks = list(api.get_tasks())
        all_tasks = flatten_items(raw_tasks)
    except Exception as e:
        logger.error("Failed to fetch tasks from Todoist", exc_info=e)
        return []

    tasks = []
    for task in all_tasks:
        try:
            due_date = task.due.date if task.due else None
            if isinstance(due_date, datetime):
                due_date = due_date.date()

            include = bool(due_date and due_date <= target_date)
            if project_ids is not None:
                include = include and (task.project_id in project_ids)

            if include:
                adjusted_priority = 5 - task.priority
                tasks.append({
                    "content": task.content,
                    "description": task.description or "",
                    "due": due_date.isoformat(),
                    "project_id": task.project_id,
                    "priority": adjusted_priority,
                })
        except Exception as e:
            logger.warning(f"Skipping task due to error: {e}", exc_info=e)
            continue

    return tasks
