from __future__ import annotations

import argparse
from pathlib import Path

from lego_agent.project.config import load_project_runtime_config
from lego_agent.project.runtime import create_project_runtime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lego-agent")
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "project" and args.project_command == "run":
        config = load_project_runtime_config(Path(args.config))
        runtime = create_project_runtime(config)
        run_result = runtime.run(args.goal)
        if args.json:
            print(run_result.model_dump_json(indent=2))
        else:
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
        return 0

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
