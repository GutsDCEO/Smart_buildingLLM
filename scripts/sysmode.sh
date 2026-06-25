#!/bin/bash

# ==============================================================================
# sysmode.sh - Smart Building AI Context & Memory Swapper
# Managed under /Users/mac/Smart_buildingLLM/scripts/sysmode.sh
# ==============================================================================

# Styling & Colors (Premium Glassmorphism Vibes)
RESET="\033[0m"
BOLD="\033[1m"
CYAN="\033[38;5;45m"
MAGENTA="\033[38;5;197m"
GREEN="\033[38;5;82m"
YELLOW="\033[38;5;220m"
GRAY="\033[38;5;244m"
RED="\033[38;5;196m"

# Header
show_header() {
    echo -e "${BOLD}${CYAN}┌────────────────────────────────────────────────────────┐${RESET}"
    echo -e "${BOLD}${CYAN}│                  ⚙️  SYSTEM MODE CONTROLLER             │${RESET}"
    echo -e "${BOLD}${CYAN}└────────────────────────────────────────────────────────┘${RESET}"
}

# RAM stats collector
print_ram_usage() {
    echo -e "${BOLD}${GRAY}[📊 Memory Status]${RESET}"
    if [ "$(uname)" = "Darwin" ]; then
        # macOS specific memory check
        local mem_info=$(top -l 1 | grep "PhysMem:")
        echo -e "  ${GRAY}${mem_info}${RESET}"
    else
        free -h | awk 'NR==2{printf "  Used: %s / Total: %s\n", $3, $2}'
    fi
}

# Unload an Ollama model instantly
unload_model() {
    local model=$1
    echo -e "  ${GRAY}Purging ${model} from RAM...${RESET}"
    curl -s -X POST http://localhost:11434/api/generate \
        -H "Content-Type: application/json" \
        -d "{\"model\": \"${model}\", \"keep_alive\": 0}" > /dev/null
}

# Warm up/Pre-load an Ollama model
warmup_model() {
    local model=$1
    echo -e "  ${CYAN}Warming up ${model} in memory...${RESET}"
    # Send a fast empty request to trigger a background load with infinite keep-alive
    curl -s -X POST http://localhost:11434/api/generate \
        -H "Content-Type: application/json" \
        -d "{\"model\": \"${model}\", \"prompt\": \"\", \"keep_alive\": -1}" > /dev/null
}

# Check currently loaded models
get_loaded_models() {
    local active=$(curl -s http://localhost:11434/api/ps)
    if [ -n "$active" ] && echo "$active" | grep -q "models"; then
        echo "$active" | jq -r '.models[].name' 2>/dev/null || echo "None"
    else
        # Fallback to ollama ps command if jq is missing or endpoint structure differs
        local list=$(ollama ps 2>/dev/null | tail -n +2 | awk '{print $1}')
        if [ -n "$list" ]; then
            echo "$list"
        else
            echo "None"
        fi
    fi
}

# Docker status
is_docker_running() {
    if docker info >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

status_action() {
    show_header
    echo ""

    # 1. Check Docker status
    echo -e "${BOLD}🐳 Docker Engine Status:${RESET}"
    if is_docker_running; then
        local count=$(docker ps -q | wc -l | xargs)
        echo -e "  ${GREEN}● RUNNING${RESET} (${count} active containers)"
        docker ps --format "    - {{.Names}} ({{.Status}})"
    else
        echo -e "  ${RED}○ STOPPED${RESET}"
    fi
    echo ""

    # 2. Check Ollama Status
    echo -e "${BOLD}🦙 Ollama Active Models:${RESET}"
    local loaded=$(get_loaded_models)
    if [ "$loaded" = "None" ] || [ -z "$loaded" ]; then
        echo -e "  ${GRAY}No models currently loaded in RAM${RESET}"
    else
        for m in $loaded; do
            echo -e "  ${GREEN}● ${m}${RESET} (Active in Memory)"
        done
    fi
    echo ""

    # 3. Memory usage
    print_ram_usage
    echo ""
}

dev_mode() {
    show_header
    echo -e "\n${BOLD}${YELLOW}🔄 Switching to DEV MODE (Docker Running + Qwen3 4B)...${RESET}\n"

    # Step 1: Purge heavy models first to ensure room for Docker startup
    echo -e "${BOLD}[1/3] Optimizing Ollama RAM Allocation...${RESET}"
    unload_model "qwen3:8b"
    echo -e "  ${GREEN}✓ Qwen3 8B purged.${RESET}"
    echo ""

    # Step 2: Start Docker Desktop
    echo -e "${BOLD}[2/3] Booting Docker VM...${RESET}"
    if is_docker_running; then
        echo -e "  ${GREEN}✓ Docker is already running.${RESET}"
    else
        echo -e "  Opening Docker Desktop application..."
        open -a Docker
        echo -n "  Waiting for Docker daemon to become responsive..."
        while ! is_docker_running; do
            echo -n "."
            sleep 1
        done
        echo -e "\n  ${GREEN}✓ Docker is fully operational!${RESET}"
    fi
    echo ""

    # Step 3: Warm up Qwen3 4B
    echo -e "${BOLD}[3/3] Warming up target LLM...${RESET}"
    warmup_model "qwen3:4b"
    echo -e "  ${GREEN}✓ Qwen3 4B is now warm and ready for low-latency coding!${RESET}"
    echo ""

    status_action
}

brain_mode() {
    show_header
    echo -e "\n${BOLD}${MAGENTA}🧠 Switching to BRAIN MODE (Docker Killed + Qwen3 8B)...${RESET}\n"

    # Step 1: Purge dev model
    echo -e "${BOLD}[1/3] Clearing Dev Model...${RESET}"
    unload_model "qwen3:4b"
    echo -e "  ${GREEN}✓ Qwen3 4B purged.${RESET}"
    echo ""

    # Step 2: Shut down Docker Desktop completely
    echo -e "${BOLD}[2/3] Terminating Docker VM & Reclaiming RAM...${RESET}"
    if ! is_docker_running && ! pgrep -x "Docker" >/dev/null; then
        echo -e "  ${GREEN}✓ Docker is already shut down.${RESET}"
    else
        echo -e "  Gracefully shutting down Docker services..."
        # If in a docker-compose directory, shut down services first (optional but clean)
        if [ -f "/Users/mac/Smart_buildingLLM/docker-compose.yml" ]; then
            docker-compose -f /Users/mac/Smart_buildingLLM/docker-compose.yml down >/dev/null 2>&1
        fi

        # Quit the Docker App completely to kill the Hypervisor VM and reclaim 4GB+ RAM
        osascript -e 'quit app "Docker"'
        echo -n "  Waiting for macOS to reclaim Docker VM memory..."
        while pgrep -x "Docker" >/dev/null || is_docker_running; do
            echo -n "."
            sleep 1
        done
        echo -e "\n  ${GREEN}✓ Docker Desktop closed. Memory fully reclaimed!${RESET}"
    fi
    echo ""

    # Step 3: Warm up Qwen3 8B
    echo -e "${BOLD}[3/3] Pre-loading High-Reasoning Brain...${RESET}"
    warmup_model "qwen3:8b"
    echo -e "  ${GREEN}✓ Qwen3 8B loaded into RAM. Ready for Obsidian Vault thinking!${RESET}"
    echo ""

    status_action
}

# Main routing logic
case "$1" in
    dev)
        dev_mode
        ;;
    brain)
        brain_mode
        ;;
    status|""|help)
        status_action
        ;;
    *)
        echo -e "${RED}Unknown command: $1${RESET}"
        echo -e "Usage: sysmode [dev|brain|status]"
        exit 1
        ;;
esac
