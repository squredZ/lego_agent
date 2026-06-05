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
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Override logging level. Can also be set by config or LEGO_AGENT_LOG_LEVEL.",
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
        nargs="?",
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
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Print a JSON run result. Overrides cli.output_json.",
    )
    run_parser.add_argument(
        "--events",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include project events in human-readable output. Overrides cli.include_events.",
    )
    run_parser.add_argument(
        "--staffing-matches",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include planned role to staff profile matches. Overrides cli.include_staffing_matches.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "project" and args.project_command == "run":
        try:
            config = load_project_runtime_config(Path(args.config))
            log_level = _resolve_log_level(args.log_level, config.cli.log_level)
            _configure_logging(log_level)
            goal = _resolve_goal(args.goal, config.project.goal)
            output_json = _resolve_bool(args.json, config.cli.output_json)
            include_events = _resolve_bool(args.events, config.cli.include_events)
            include_staffing_matches = _resolve_bool(
                args.staffing_matches,
                config.cli.include_staffing_matches,
            )
            logger.info(
                "cli project run started",
                extra={
                    "config_path": args.config,
                    "json_output": output_json,
                    "include_events": include_events,
                    "include_staffing_matches": include_staffing_matches,
                    "goal_length": len(goal),
                },
            )
            runtime = create_project_runtime(config)
            run_result = runtime.run(goal)
        except Exception as exc:
            logger.exception("cli project run failed")
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if output_json:
            print(run_result.model_dump_json(indent=2))
        else:
            _print_human_result(
                run_result,
                include_events=include_events,
                include_staffing_matches=include_staffing_matches,
            )
        logger.info(
            "cli project run completed",
            extra={"project_id": run_result.project_id, "status": run_result.status.value},
        )
        return 0

    parser.error(f"unsupported command: {args.command}")
    return 2


def _resolve_log_level(cli_value: str | None, config_value: str | None) -> str:
    """Resolve log level from CLI, config, env var, then a quiet default."""
    return cli_value or config_value or os.environ.get("LEGO_AGENT_LOG_LEVEL", "WARNING")


def _resolve_goal(cli_value: str | None, config_value: str | None) -> str:
    """Use CLI goal when provided, otherwise fall back to config project.goal."""
    goal = cli_value or config_value
    if not goal:
        raise ValueError("project goal is required; pass it on the CLI or set project.goal in config")
    return goal


def _resolve_bool(cli_value: bool | None, config_value: bool) -> bool:
    """Let explicit CLI booleans override config defaults."""
    return config_value if cli_value is None else cli_value


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
    include_staffing_matches: bool = False,
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

    if include_staffing_matches and run_result.staffing_profile_resolution is not None:
        print()
        print("staffing profile matches:")
        for match in run_result.staffing_profile_resolution.matches:
            if match.matched:
                if match.source == "profile":
                    print(
                        f"- {match.planned_title} ({match.planned_role}) -> "
                        f"{match.profile_title} ({match.profile_name})"
                    )
                elif match.source == "dynamic":
                    print(f"- {match.planned_title} ({match.planned_role}) -> dynamic staff")
                else:
                    print(f"- {match.planned_title} ({match.planned_role}) -> {match.source}")
            else:
                print(f"- {match.planned_title} ({match.planned_role}) -> unresolved: {match.reason}")

    if include_events:
        print()
        print("events:")
        for event in run_result.events:
            actor = f" actor={event.actor_id}" if event.actor_id else ""
            task = f" task={event.task_id}" if event.task_id else ""
            print(f"- [{event.level.value}] {event.type}:{actor}{task} {event.message}")


if __name__ == "__main__":
    raise SystemExit(main())
