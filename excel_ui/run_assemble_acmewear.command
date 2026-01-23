#!/bin/bash
# Wrapper: moved to excel_ui/assemble_per_store/run_assemble_acmewear.command
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/assemble_per_store/run_assemble_acmewear.command"
