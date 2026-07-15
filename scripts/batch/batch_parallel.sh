#!/bin/bash
#
# Batch Parallel Pipeline Processing
# Обрабатывает несколько FASTQ образцов параллельно
#
# Usage:
#   ./scripts/batch_parallel.sh <samples_dir> [max_concurrent] [batch_name]
#
# Examples:
#   ./scripts/batch_parallel.sh data/samples/ 3
#   ./scripts/batch_parallel.sh data/samples/ 4 december_batch
#

set -euo pipefail

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция вывода с timestamp
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] SUCCESS:${NC} $1"
}

warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

# Проверка аргументов
if [ $# -lt 1 ]; then
    error "Missing required argument"
    echo ""
    echo "Usage: $0 <samples_dir> [max_concurrent] [batch_name]"
    echo ""
    echo "Arguments:"
    echo "  samples_dir       Directory containing FASTQ files (.fastq or .fq)"
    echo "  max_concurrent    Maximum number of concurrent pipelines (default: 3)"
    echo "  batch_name        Name for this batch run (default: batch_YYYYMMDD_HHMMSS)"
    echo ""
    echo "Examples:"
    echo "  $0 data/samples/ 3"
    echo "  $0 data/samples/ 4 december_batch"
    echo "  $0 data/ena_downloads/ 2 ena_test"
    exit 1
fi

SAMPLES_DIR="$1"
MAX_CONCURRENT="${2:-3}"
BATCH_NAME="${3:-batch_$(date +%Y%m%d_%H%M%S)}"

# Проверка директории с образцами
if [ ! -d "$SAMPLES_DIR" ]; then
    error "Samples directory not found: $SAMPLES_DIR"
    exit 1
fi

# Проверка наличия cli_pipeline_run.sh
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPELINE_SCRIPT="$SCRIPT_DIR/cli_pipeline_run.sh"

if [ ! -f "$PIPELINE_SCRIPT" ]; then
    error "Pipeline script not found: $PIPELINE_SCRIPT"
    exit 1
fi

# Подсчёт образцов
SAMPLE_COUNT=$(find "$SAMPLES_DIR" -name "*.fastq" -o -name "*.fq" | wc -l)

if [ "$SAMPLE_COUNT" -eq 0 ]; then
    error "No FASTQ files found in $SAMPLES_DIR"
    exit 1
fi

# Вывод информации
log "============================================="
log "Batch Processing: ${BATCH_NAME}"
log "============================================="
log "Samples directory: $SAMPLES_DIR"
log "Total samples: $SAMPLE_COUNT"
log "Max concurrent: $MAX_CONCURRENT"
log "Pipeline script: $PIPELINE_SCRIPT"
log "Server capacity: 64 CPUs, 125 GB RAM, NVIDIA L4 GPU"
log "============================================="

# Создание директории для логов batch-обработки
BATCH_LOG_DIR="logs/batch_${BATCH_NAME}"
mkdir -p "$BATCH_LOG_DIR"
log "Batch logs: $BATCH_LOG_DIR"

# Список образцов
log ""
log "Queued samples:"
SAMPLE_NUM=1
while IFS= read -r sample; do
    sample_name=$(basename "$sample" | sed 's/\.[^.]*$//')
    log "  [$SAMPLE_NUM] $sample_name"
    ((SAMPLE_NUM++))
done < <(find "$SAMPLES_DIR" -name "*.fastq" -o -name "*.fq" | sort)

log ""
log "Starting parallel processing..."
log "============================================="

# Создание temporary file для отслеживания результатов
RESULTS_FILE="$BATCH_LOG_DIR/results.txt"
> "$RESULTS_FILE"

# Функция обработки одного образца
process_sample() {
    local sample="$1"
    local batch_name="$2"
    local log_dir="$3"
    
    sample_name=$(basename "$sample" | sed 's/\.[^.]*$//')
    pipeline_name="${batch_name}_${sample_name}"
    
    log_file="$log_dir/${sample_name}.log"
    error_file="$log_dir/${sample_name}.err"
    
    local start_time=$(date +%s)
    
    log "▶ Starting: $sample_name (pipeline: $pipeline_name)"
    
    # Запуск pipeline
    if "$PIPELINE_SCRIPT" "$sample" "$pipeline_name" > "$log_file" 2> "$error_file"; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        local minutes=$((duration / 60))
        local seconds=$((duration % 60))
        
        success "✓ Completed: $sample_name (${minutes}m ${seconds}s)"
        echo "SUCCESS|$sample_name|$pipeline_name|$duration" >> "$RESULTS_FILE"
    else
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        
        error "✗ Failed: $sample_name (after ${duration}s)"
        error "  See logs: $log_file, $error_file"
        echo "FAILED|$sample_name|$pipeline_name|$duration" >> "$RESULTS_FILE"
    fi
}

export -f process_sample
export -f log
export -f error
export -f success
export RED GREEN YELLOW BLUE NC
export PIPELINE_SCRIPT
export BATCH_LOG_DIR

# Параллельная обработка с помощью xargs
find "$SAMPLES_DIR" -name "*.fastq" -o -name "*.fq" | sort | \
xargs -P "$MAX_CONCURRENT" -I {} bash -c "process_sample '{}' '$BATCH_NAME' '$BATCH_LOG_DIR'"

# Итоговый отчёт
log ""
log "============================================="
log "Batch Processing Complete: ${BATCH_NAME}"
log "============================================="

# Подсчёт результатов
TOTAL=$(wc -l < "$RESULTS_FILE")
SUCCESS_COUNT=$(grep -c "^SUCCESS" "$RESULTS_FILE" || echo 0)
FAILED_COUNT=$(grep -c "^FAILED" "$RESULTS_FILE" || echo 0)

log "Total processed: $TOTAL"
success "Successful: $SUCCESS_COUNT"
if [ "$FAILED_COUNT" -gt 0 ]; then
    error "Failed: $FAILED_COUNT"
fi

# Статистика времени выполнения
if [ "$SUCCESS_COUNT" -gt 0 ]; then
    log ""
    log "Timing Statistics (successful runs):"
    
    TOTAL_DURATION=0
    MIN_DURATION=999999
    MAX_DURATION=0
    
    while IFS='|' read -r status sample pipeline duration; do
        if [ "$status" = "SUCCESS" ]; then
            TOTAL_DURATION=$((TOTAL_DURATION + duration))
            
            if [ "$duration" -lt "$MIN_DURATION" ]; then
                MIN_DURATION=$duration
            fi
            
            if [ "$duration" -gt "$MAX_DURATION" ]; then
                MAX_DURATION=$duration
            fi
        fi
    done < "$RESULTS_FILE"
    
    AVG_DURATION=$((TOTAL_DURATION / SUCCESS_COUNT))
    
    log "  Fastest: $((MIN_DURATION / 60))m $((MIN_DURATION % 60))s"
    log "  Slowest: $((MAX_DURATION / 60))m $((MAX_DURATION % 60))s"
    log "  Average: $((AVG_DURATION / 60))m $((AVG_DURATION % 60))s"
    log "  Total parallel time: See below"
fi

# Вывод списка failed samples
if [ "$FAILED_COUNT" -gt 0 ]; then
    log ""
    warning "Failed samples:"
    grep "^FAILED" "$RESULTS_FILE" | while IFS='|' read -r status sample pipeline duration; do
        warning "  - $sample (pipeline: $pipeline)"
        warning "    Log: $BATCH_LOG_DIR/${sample}.log"
        warning "    Error: $BATCH_LOG_DIR/${sample}.err"
    done
fi

log ""
log "Detailed results: $RESULTS_FILE"
log "Batch logs: $BATCH_LOG_DIR"
log "============================================="

# Возврат кода ошибки если были failed samples
if [ "$FAILED_COUNT" -gt 0 ]; then
    exit 1
else
    exit 0
fi
