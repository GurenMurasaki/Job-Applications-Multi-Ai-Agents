#!/bin/bash
# Stop Script for Job Application Agents
# This script stops the running agents gracefully or forcefully

set -e

SCRIPT_DIR="$(dirname "$0")"
PID_FILE="$SCRIPT_DIR/.agent.pid"
STOP_FILE="$SCRIPT_DIR/.stop_requested"

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --graceful    Stop after current job completes (default)"
    echo "  --force       Stop immediately (current job will resume on next start)"
    echo "  --status      Check if agents are running"
    echo "  -h, --help    Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0              # Graceful stop (finish current job, then stop)"
    echo "  $0 --graceful   # Same as above"
    echo "  $0 --force      # Force stop immediately"
    echo "  $0 --status     # Check running status"
}

check_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            return 0  # Running
        else
            # Stale PID file
            rm -f "$PID_FILE"
            return 1  # Not running
        fi
    fi
    return 1  # Not running
}

graceful_stop() {
    echo "=============================================="
    echo "  Requesting Graceful Stop"
    echo "=============================================="
    
    if ! check_running; then
        echo "No agents are currently running."
        rm -f "$STOP_FILE"
        exit 0
    fi
    
    PID=$(cat "$PID_FILE")
    echo "Agent is running with PID: $PID"
    echo "Requesting graceful shutdown..."
    echo "The agent will stop after completing the current job."
    
    # Create stop file (signal to the Python process)
    touch "$STOP_FILE"
    
    # Send SIGTERM for graceful shutdown
    kill -SIGTERM "$PID" 2>/dev/null || true
    
    echo ""
    echo "Stop request sent. Waiting for current job to complete..."
    echo "Use '$0 --status' to check if the agent has stopped."
    echo "Use '$0 --force' to force immediate stop if needed."
}

force_stop() {
    echo "=============================================="
    echo "  Force Stopping Agents"
    echo "=============================================="
    
    if ! check_running; then
        echo "No agents are currently running."
        rm -f "$STOP_FILE" "$PID_FILE"
        exit 0
    fi
    
    PID=$(cat "$PID_FILE")
    echo "Agent is running with PID: $PID"
    echo "Force stopping..."
    
    # Create stop file
    touch "$STOP_FILE"
    
    # Send SIGKILL for immediate termination
    kill -SIGKILL "$PID" 2>/dev/null || true
    
    # Wait a moment
    sleep 1
    
    # Clean up
    rm -f "$PID_FILE"
    
    echo ""
    echo "Agent force stopped."
    echo "NOTE: If a job was in progress, it will be resumed on next start."
    echo ""
    echo "The incomplete job's status.json tracks which stages are complete."
    echo "When you restart, the agent will continue from where it left off."
}

check_status() {
    echo "=============================================="
    echo "  Agent Status"
    echo "=============================================="
    
    if check_running; then
        PID=$(cat "$PID_FILE")
        echo "Status: RUNNING"
        echo "PID: $PID"
        
        if [ -f "$STOP_FILE" ]; then
            echo "Stop requested: YES (waiting for current job to complete)"
        else
            echo "Stop requested: NO"
        fi
    else
        echo "Status: NOT RUNNING"
        
        if [ -f "$STOP_FILE" ]; then
            echo "Cleaning up stale stop file..."
            rm -f "$STOP_FILE"
        fi
    fi
    
    echo ""
    
    # Show job processing status
    if [ -d "$SCRIPT_DIR/data/jobs" ]; then
        TOTAL_JOBS=$(find "$SCRIPT_DIR/data/jobs" -maxdepth 1 -type d | wc -l)
        TOTAL_JOBS=$((TOTAL_JOBS - 1))  # Exclude the jobs dir itself
        
        if [ "$TOTAL_JOBS" -gt 0 ]; then
            echo "Jobs in queue: $TOTAL_JOBS"
            echo "Run './start.sh --status' for detailed job status."
        else
            echo "No jobs in queue."
        fi
    fi
}

# Parse arguments
MODE="graceful"

while [[ $# -gt 0 ]]; do
    case $1 in
        --graceful)
            MODE="graceful"
            shift
            ;;
        --force)
            MODE="force"
            shift
            ;;
        --status)
            MODE="status"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Execute based on mode
case $MODE in
    graceful)
        graceful_stop
        ;;
    force)
        force_stop
        ;;
    status)
        check_status
        ;;
esac
