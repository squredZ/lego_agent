from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from lego_agent.core.models import ProjectRunResult
from lego_agent.project.config import load_project_runtime_config
from lego_agent.project.runtime import create_project_runtime

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lego-agent")
    parser.add_argument(
        "--log-level",
        default=os.environ.get("LEGO_AGENT_LOG_LEVEL", "WARNING"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set CLI logging level. Can also be set with LEGO_AGENT_LOG_LEVEL.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    project_parser = subparsers.add_parser("project", help="Project commands.")
    project_subparsers = project_parser.add_subparsers(
        dest="project_command",
        required=True,
    )
    run_parser = project_subparsers.add_parser("run", help="Run a project goal.")
    run_parser.add_argument(
        "goal",
        help="Project goal.",
    )
    run_parser.add_argument(
        "-c",
        "--config",
        default="configs/project_runtime.json",
        help="Path to project runtime config JSON.",
    )
    run_parser.add_argument(
        "--json",
        action="store_true",
        help="Print a JSON run result.",
    )
    run_parser.add_argument(
        "--events",
        action="store_true",
        help="Include project events in human-readable output.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.log_level)

    if args.command == "project" and args.project_command == "run":
        try:
            logger.info(
                "cli project run started",
                extra={
                    "config_path": args.config,
                    "json_output": args.json,
                    "include_events": args.events,
                    "goal_length": len(args.goal),
                },
            )
            config = load_project_runtime_config(Path(args.config))
            runtime = create_project_runtime(config)
            run_result = runtime.run(args.goal)
        except Exception as exc:
            logger.exception("cli project run failed")
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(run_result.model_dump_json(indent=2))
        else:
            _print_human_result(run_result, include_events=args.events)
        logger.info(
            "cli project run completed",
            extra={"project_id": run_result.project_id, "status": run_result.status.value},
        )
        return 0

    parser.error(f"unsupported command: {args.command}")
    return 2


def _configure_logging(level_name: str) -> None:
    """Configure CLI logging without affecting library users.

    Library modules only create named loggers. The command-line application is
    the boundary that decides whether those records should be printed.
    """
    logging.basicConfig(
        level=getattr(logging, level_name),
        format="%(levelname)s %(name)s: %(message)s",
    )


def _print_human_result(
    run_result: ProjectRunResult,
    *,
    include_events: bool = False,
) -> None:
    """Print compact CLI output for people.

    JSON output always contains the full event list. Human output keeps events
    hidden by default and shows them only when `--events` is requested.
    """
    print(f"project: {run_result.project_id}")
    print(f"manager: {run_result.manager_name} ({run_result.manager_id})")
    print(f"status: {run_result.status.value}")
    print()
    if run_result.result:
        print(f"summary: {run_result.result.summary}")
        print()
        print("staffing plan:")
        for role in run_result.result.staffing_plan.required_roles:
            print(f"- {role.title} ({role.role}): {role.task_focus}")
        print()
        print(run_result.result.final_output)
    elif run_result.error:
        print(f"error: {run_result.error.message}")

    if include_events:
        print()
        print("events:")
        for event in run_result.events:
            actor = f" actor={event.actor_id}" if event.actor_id else ""
            task = f" task={event.task_id}" if event.task_id else ""
            print(f"- [{event.level.value}] {event.type}:{actor}{task} {event.message}")


if __name__ == "__main__":
    raise SystemExit(main())
