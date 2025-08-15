#!/bin/bash
set -euo pipefail

# Get directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &>/dev/null && pwd )"

# Try to source .env from parent directory
ENV_FILE="${SCRIPT_DIR}/../.env"

if [ -f "$ENV_FILE" ]; then
  echo "Loading env from $ENV_FILE"
  # shellcheck disable=SC1090
  source "$ENV_FILE"
else
  echo "Warning: $ENV_FILE not found, using default vars"
fi

# Set default environment variables if not already set
PROCESS_NAME="${PROCESS_NAME:-DDNet-Server}"
BASE_DIR="${BASE_DIR:-/home/ubuntu/ddnet-insta-server}"
CFG_DIR="${CFG_DIR:-/home/ubuntu/vanillecup_servers}"
LOG_FILE="${LOG_FILE:-/home/ubuntu/vanillecup_servers/log/launch_servers.log}"
INSTANCE_COUNT="${INSTANCE_COUNT:-1}"
COMMAND_BASE="${COMMAND_BASE:-${BASE_DIR}/DDNet-Server}"

# Print environment variables to verify (optional)
echo "Process Name: $PROCESS_NAME"
echo "Base Directory: $BASE_DIR"
echo "Config Directory: $CFG_DIR"
echo "Log File: $LOG_FILE"
echo "Instance Count: $INSTANCE_COUNT"
echo "Command Base: $COMMAND_BASE"

# Your server start command here, e.g.,
# $COMMAND_BASE


# Timestamp function for logging
timestamp() {
  date +"%Y-%m-%d %H:%M:%S"
}

echo "$(timestamp): Checking for process $PROCESS_NAME..." | tee -a "$LOG_FILE"

# Function to sanitize and normalize integer from pgrep output
sanitize_count() {
  local raw_count="$1"
  local clean_count
  clean_count=$(echo "$raw_count" | tr -d '\r\n' | tr -dc '0-9')
  echo "${clean_count:-0}"
}

# Count number of running instances (sanitized)
raw_running_count=$(pgrep -c -x "$PROCESS_NAME" 2>/dev/null || echo 0)
running_count=$(sanitize_count "$raw_running_count")

echo "$(timestamp): Running count (sanitized) = $running_count" | tee -a "$LOG_FILE"
echo "$(timestamp): Instance count configured = $INSTANCE_COUNT" | tee -a "$LOG_FILE"

# Validate INSTANCE_COUNT is numeric, else default to 1
if ! [[ "$INSTANCE_COUNT" =~ ^[0-9]+$ ]]; then
  echo "$(timestamp): Warning: INSTANCE_COUNT '$INSTANCE_COUNT' invalid, defaulting to 1." | tee -a "$LOG_FILE"
  INSTANCE_COUNT=1
fi

if (( running_count >= INSTANCE_COUNT )); then
  echo "$(timestamp): $PROCESS_NAME is running ($running_count instances)." | tee -a "$LOG_FILE"
else
  missing=$(( INSTANCE_COUNT - running_count ))
  echo "$(timestamp): $PROCESS_NAME running only $running_count instances; starting $missing missing." | tee -a "$LOG_FILE"

  # Start missing instances (to reach INSTANCE_COUNT)
  for i in $(seq 1 $missing); do
    cfg_file="cfg/autoexec${i}.cfg"
      if [[ ! -f "${CFG_DIR}/${cfg_file}" && "$i" -eq 1 ]]; then
      cfg_file="cfg/autoexec.cfg"
    fi

    echo "$(timestamp): Attempting to start instance $i with config file: $cfg_file" | tee -a "$LOG_FILE"

    # Check if server command exists and is executable
    if [[ ! -x "$COMMAND_BASE" ]]; then
      echo "$(timestamp): ERROR: Command '$COMMAND_BASE' not found or not executable!" | tee -a "$LOG_FILE"
      exit 1
    fi

    # Check if config file exists
    if [[ ! -f "$cfg_file" ]]; then
      echo "$(timestamp): WARNING: Config file '$cfg_file' does not exist." | tee -a "$LOG_FILE"
    fi

    echo "$(timestamp): Running command: nohup \"$COMMAND_BASE\" -f \"$cfg_file\" >> \"$LOG_FILE\" 2>&1 &" | tee -a "$LOG_FILE"
    (
        cd "$CFG_DIR" || exit 1
        nohup "$COMMAND_BASE" -f "$cfg_file" >> "$LOG_FILE" 2>&1 &
    )

    sleep 1  # slight delay to avoid race conditions
  done

  sleep 5  # give some time for processes to start

  raw_running_count_post=$(pgrep -c -x "$PROCESS_NAME" 2>/dev/null || echo 0)
  running_count_post=$(sanitize_count "$raw_running_count_post")

  echo "$(timestamp): Running count after start attempts (sanitized) = $running_count_post" | tee -a "$LOG_FILE"

  if (( running_count_post >= INSTANCE_COUNT )); then
    echo "$(timestamp): Successfully started $PROCESS_NAME instances: now $running_count_post running." | tee -a "$LOG_FILE"
  else
    echo "$(timestamp): Failed to start some $PROCESS_NAME instances. Running instances: $running_count_post" | tee -a "$LOG_FILE"
    exit 1
  fi
fi