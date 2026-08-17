#!/bin/zsh
#
# provision — create/verify the six-seat worktree topology, or deprovision it.
#
# Subcommands:
#   preview      read-only topology plan + pathsDigest (no mutation)
#   run          execute the plan bound to a user-approved pathsDigest
#   deprovision  remove roster-listed worktrees (refuses dirty worktrees;
#                requires --confirm; branches are never removed by default)
#
# Known CLI gaps fail closed with pending placeholders (main_attach_pending,
# team_create_cli_pending, employee_parent_create_cli_pending). Never bypassed.

set -u
set -o pipefail

readonly script_dir="${0:A:h}"
readonly helper="$script_dir/scripts/team_provision.py"
readonly project_dir="${PWD:A}"
readonly python_cli="${commands[python3]:A}"
readonly git_cli="${commands[git]:A}"
readonly jq_cli=/usr/bin/jq

usage() {
  print -r -- "Usage:"
  print -r -- "  ${0:t} preview [--base-dir <path>]"
  print -r -- "  ${0:t} run --confirm-paths-digest <hex> [--accepted-commit <sha>] [--leader-bootstrap-commit <sha>]"
  print -r -- "  ${0:t} deprovision --confirm [--remove-branches]"
}

typeset -a helper_args
subcommand=""

while (( $# > 0 )); do
  case "$1" in
    preview|run|deprovision)
      subcommand="$1"
      shift
      ;;
    --confirm-paths-digest)
      if (( $# < 2 )); then usage >&2; exit 2; fi
      helper_args+=(--confirm-paths-digest "$2")
      shift 2
      ;;
    --accepted-commit)
      if (( $# < 2 )); then usage >&2; exit 2; fi
      helper_args+=(--accepted-commit "$2")
      shift 2
      ;;
    --leader-bootstrap-commit)
      if (( $# < 2 )); then usage >&2; exit 2; fi
      helper_args+=(--leader-bootstrap-commit "$2")
      shift 2
      ;;
    --base-dir)
      if (( $# < 2 )); then usage >&2; exit 2; fi
      helper_args+=(--base-dir "$2")
      shift 2
      ;;
    --confirm)
      helper_args+=(--confirm)
      shift
      ;;
    --remove-branches)
      helper_args+=(--remove-branches)
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$subcommand" ]]; then
  usage >&2
  exit 2
fi

run_helper() {
  /usr/bin/env -i \
    HOME="$HOME" USER="$(/usr/bin/id -un)" LOGNAME="$(/usr/bin/id -un)" \
    TMPDIR="${TMPDIR:-/tmp}" PATH='/usr/bin:/bin' LC_ALL=C \
    "$python_cli" -I -B "$helper" \
    --project "$project_dir" \
    --subcommand "$subcommand" \
    --git-cli "$git_cli" \
    --orca-cli /Users/wzy/.homebrew/bin/orca \
    "$@"
}

result="$(run_helper "${helper_args[@]}")"
exit_code=$?

case "$subcommand" in
  preview)
    if [[ $exit_code -ne 0 ]]; then
      print -r -- "$result" >&2
      exit $exit_code
    fi
    print -r -- "$result" | "$jq_cli" '{ok, code, project, baseDir, main, seats, plannedCreates, conflicts, unrelatedWorktreesPreserved, firstBlockingCode, pathsDigest, nextStep}'
    print -r -- "provision preview complete. Review every absolute path above; creating" >&2
    print -r -- "worktrees requires the current user's explicit confirmation of this exact" >&2
    print -r -- "pathsDigest and of every path shown." >&2
    exit 0
    ;;
  run)
    print -r -- "$result" | "$jq_cli" '{ok, code, message, changesApplied, mutations, unrelatedWorktreesPreserved, rosterPublished, agentsStarted, nextStep}'
    exit $exit_code
    ;;
  deprovision)
    print -r -- "$result" | "$jq_cli" '{ok, code, message, changesApplied, dirtyWorktrees, removed, targets, branchesKept}'
    exit $exit_code
    ;;
esac
