#!/bin/zsh
#
# message — inject or verify Team message identity envelopes.
#
# Subcommands:
#   keys <seat>        generate one seat Ed25519 key pair in ~/.agent-team/keys/<project>/
#   inject <json-file> build a signed envelope from agent-provided fields
#   verify <json-file> verify an envelope against roster + public keys
#
# Sender identity is never taken from message content: it comes from --seat
# plus the roster. A model's self-reported identity is never trusted.

set -u
set -o pipefail

readonly script_dir="${0:A:h}"
readonly helper="$script_dir/scripts/team_identity.py"
readonly project_dir="${PWD:A}"
readonly python_cli="${commands[python3]:A}"
readonly jq_cli=/usr/bin/jq
readonly keys_dir="${AGENT_TEAM_KEYS_DIR:-$HOME/.agent-team/keys/${project_dir:t}}"
readonly roster_path="$project_dir/.agent-team/roster.json"

usage() {
  print -r -- "Usage:"
  print -r -- "  ${0:t} keys <seat-key>"
  print -r -- "  ${0:t} inject <seat-key> <recipient-seat> <private-key-path> <agent-fields.json>"
  print -r -- "  ${0:t} verify <envelope.json>"
  print -r -- "  ${0:t} roster-update <seat-key> <fingerprint>"
}

subcommand=""
typeset -a helper_args

while (( $# > 0 )); do
  case "$1" in
    keys|inject|verify|roster-update)
      subcommand="$1"
      shift
      break
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

case "$subcommand" in
  keys)
    if (( $# < 1 )); then usage >&2; exit 2; fi
    helper_args=(--seat "$1" --keys-dir "$keys_dir")
    ;;
  inject)
    if (( $# < 4 )); then usage >&2; exit 2; fi
    helper_args=(--seat "$1" --recipient "$2" --private-key "$3" --input "$4" \
      --project "$project_dir" --roster-path "$roster_path")
    ;;
  verify)
    if (( $# < 1 )); then usage >&2; exit 2; fi
    helper_args=(--envelope "$1" --roster-path "$roster_path" --keys-dir "$keys_dir")
    ;;
  roster-update)
    if (( $# < 2 )); then usage >&2; exit 2; fi
    helper_args=(--seat "$1" --fingerprint "$2" --roster-path "$roster_path")
    ;;
esac

result="$(/usr/bin/env -i \
  HOME="$HOME" USER="$(/usr/bin/id -un)" LOGNAME="$(/usr/bin/id -un)" \
  TMPDIR="${TMPDIR:-/tmp}" PATH='/usr/bin:/bin' LC_ALL=C \
  "$python_cli" -I -B "$helper" \
  --subcommand "$subcommand" \
  "${helper_args[@]}")"
exit_code=$?

print -r -- "$result" | "$jq_cli" '{ok, code, message, seat, publicKeyFingerprint, errors, envelope, nextStep}'
exit $exit_code
