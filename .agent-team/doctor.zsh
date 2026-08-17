#!/bin/zsh
#
# team doctor --json — read-only Team self-check.
#
# Checks charter version, pointer consistency, approval matrix coverage,
# roster, topology, CLI profiles, Orca runtime, terminal readiness, and the
# embedded M4 identity cases. Non-zero exit when any check fails; every
# failure carries a next-step command. Zero mutation.

set -u
set -o pipefail

readonly script_dir="${0:A:h}"
readonly helper="$script_dir/scripts/team_doctor.py"
readonly project_dir="${PWD:A}"
readonly python_cli="${commands[python3]:A}"
readonly git_cli="${commands[git]:A}"
readonly jq_cli=/usr/bin/jq

usage() {
  print -r -- "Usage: ${0:t} [--json]"
}

while (( $# > 0 )); do
  case "$1" in
    --json)
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

typeset -a cli_args
for label in claude codex opencode claudex kimi; do
  if (( ${+commands[$label]} )); then
    cli_args+=("--cli-${label}" "${commands[$label]:A}")
  fi
done

result="$(/usr/bin/env -i \
  HOME="$HOME" USER="$(/usr/bin/id -un)" LOGNAME="$(/usr/bin/id -un)" \
  TMPDIR="${TMPDIR:-/tmp}" PATH='/usr/bin:/bin' LC_ALL=C \
  "$python_cli" -I -B "$helper" \
  --project "$project_dir" \
  --home "$HOME" \
  --git-cli "$git_cli" \
  --orca-cli /Users/wzy/.homebrew/bin/orca \
  "${cli_args[@]}")"
exit_code=$?

print -r -- "$result" | "$jq_cli" '{ok, code, checks: [.checks[] | {id, label, ok, code, detail, nextStep}], failingCount, nextStep}'
exit $exit_code
