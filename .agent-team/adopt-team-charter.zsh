#!/bin/zsh
#
# adopt-team-charter — adopt the canonical Agent Team charter into this project.
#
# Subcommands:
#   preview   read-only diff summary, write targets, backup plan, confirm digest
#   apply     backup + atomic replace, bound to a user-approved preview digest
#   check     version check: current vs expected contract, next-step command
#
# Normative rules live in .agent-team/TEAM.md; this entry implements only I/O.

set -u
set -o pipefail

readonly script_dir="${0:A:h}"
readonly helper="$script_dir/scripts/team_adopt.py"
readonly project_dir="${PWD:A}"
readonly python_cli="${commands[python3]:A}"
readonly jq_cli=/usr/bin/jq

usage() {
  print -r -- "Usage:"
  print -r -- "  ${0:t} preview [--asset <path>]"
  print -r -- "  ${0:t} apply --confirm-digest <hex> [--asset <path>]"
  print -r -- "  ${0:t} check [--asset <path>]"
}

typeset -a helper_args
subcommand=""
asset_path="/Users/wzy/.codex/skills/init-project-agent-team/assets/TEAM.md"

while (( $# > 0 )); do
  case "$1" in
    preview|apply|check)
      subcommand="$1"
      shift
      ;;
    --confirm-digest)
      if (( $# < 2 )); then usage >&2; exit 2; fi
      helper_args+=(--confirm-digest "$2")
      shift 2
      ;;
    --asset)
      if (( $# < 2 )); then usage >&2; exit 2; fi
      asset_path="$2"
      shift 2
      ;;
    --fresh-install)
      helper_args+=(--fresh-install)
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
if [[ "$subcommand" == "apply" ]] && ! print -r -- "$helper_args" | /usr/bin/grep -q -- '--confirm-digest'; then
  print -r -- "apply requires --confirm-digest from a user-approved preview" >&2
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
    --asset "$asset_path" \
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
    print -r -- "$result" | "$jq_cli" '{ok, code, project, charter, pointerTargets, migrationMap, proposedMeta, backupPlan, writeTargets, confirmDigest}'
    print -r -- "" >&2
    print -r -- "adopt-team-charter preview complete. Review the diff summary above;" >&2
    print -r -- "adoption requires the current user's explicit confirmation of this exact" >&2
    print -r -- "confirmDigest, the write targets, and the backup plan." >&2
    exit 0
    ;;
  apply)
    print -r -- "$result" | "$jq_cli" '{ok, code, message, changesApplied, changes, backups, rulesReloadRequired, nextStep}'
    if [[ $exit_code -ne 0 ]]; then
      print -r -- "adopt-team-charter apply failed: $exit_code" >&2
      exit $exit_code
    fi
    print -r -- "adopt-team-charter apply complete. Rules reload required: end this session" >&2
    print -r -- "and re-verify in a new session with: adopt-team-charter check" >&2
    exit 0
    ;;
  check)
    print -r -- "$result" | "$jq_cli" '{ok, code, current, expected, diffSummary, nextStep}'
    exit $exit_code
    ;;
esac
