#!/bin/bash

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Verify gradle wrapper exists
if [ ! -f "./gradlew" ]; then
    log_error "gradlew not found in current directory"
    exit 1
fi

log_info "Building project with gradlew assemble..."
if ! ./gradlew assemble; then
    log_error "Gradle build failed"
    exit 1
fi

log_info "Finding -all JAR in build/libs..."
JAR_FILE=$(ls -1 build/libs/*-all.jar 2>/dev/null | head -1)

if [ -z "$JAR_FILE" ]; then
    log_error "No *-all.jar file found in build/libs directory"
    exit 1
fi

log_info "Found JAR: $JAR_FILE"
log_info "Starting bot..."

# Run with error handling
if java \
  -Xms512m \
  -Xmx512m \
  -XX:+UseG1GC \
  -XX:MaxGCPauseMillis=200 \
  -XX:+ParallelRefProcEnabled \
  -Dfile.encoding=UTF-8 \
  -jar "$JAR_FILE"; then
    log_info "Bot exited successfully"
else
    EXIT_CODE=$?
    log_error "Bot exited with code $EXIT_CODE"
    exit $EXIT_CODE
fi