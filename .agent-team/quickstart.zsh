#!/bin/zsh
#
# quickstart — start (or rebuild) the six-seat Agent Team sessions.
#
# Owns session lifecycle only: charter check -> roster + topology ->
# permission modes -> Orca runtime -> prior-generation cleanup -> six creates.
# Any missing precondition fails closed with a navigable code; it never
# repairs worktrees or the charter mid-run.

set -u
set -o pipefail

readonly script_dir="${0:A:h}"
readonly helper="$script_dir/scripts/team_quickstart.py"
readonly project_dir="${PWD:A}"
readonly python_cli="${commands[python3]:A}"
readonly jq_cli=/usr/bin/jq

usage() {
  print -r -- "Usage: ${0:t} [--authorize-high-privilege <seat>=<parameter>]..."
}

typeset -a auth_args
while (( $# > 0 )); do
  case "$1" in
    --authorize-high-privilege)
      if (( $# < 2 )); then usage >&2; exit 2; fi
      auth_args+=(--authorize-high-privilege "$2")
      shift 2
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

result="$(/usr/bin/env -i \
  HOME="$HOME" USER="$(/usr/bin/id -un)" LOGNAME="$(/usr/bin/id -un)" \
  TMPDIR="${TMPDIR:-/tmp}" PATH='/usr/bin:/bin' LC_ALL=C \
  "$python_cli" -I -B "$helper" \
  --project "$project_dir" \
  --home "$HOME" \
  --orca-cli /Users/wzy/.homebrew/bin/orca \
  "${auth_args[@]}")"
exit_code=$?

print -r -- "$result" | "$jq_cli" '{ok, code, message, phases, nextStep, changesApplied}'
exit $exit_code
