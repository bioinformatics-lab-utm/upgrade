#!/bin/bash
set -e

echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║       🚀 ЗАПУСК NEXTFLOW PIPELINE - ZymoBIOMICS                        ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
echo

SAMPLE="ZYMO_TEST"
INPUT_DIR="/home/nicolaedrabcinski/upgrade/data/zymo_mock"
OUTPUT_DIR="/home/nicolaedrabcinski/upgrade/results/zymo_test"
LOG_FILE="/home/nicolaedrabcinski/upgrade/logs/zymo_pipeline.log"

mkdir -p logs
mkdir -p "$OUTPUT_DIR"

echo "📊 ПАРАМЕТРЫ:"
echo "   Sample: $SAMPLE"
echo "   Input: $INPUT_DIR"
echo "   Output: $OUTPUT_DIR"
echo "   Log: $LOG_FILE"
echo

# Проверка файлов
if [ ! -f "$INPUT_DIR/SRR13128014.fastq.gz" ]; then
    echo "❌ FASTQ файл не найден: $INPUT_DIR/SRR13128014.fastq.gz"
    exit 1
fi

echo "✅ FASTQ найден: $(ls -lh $INPUT_DIR/SRR13128014.fastq.gz | awk '{print $5}')"
echo

# Запуск в screen
SCREEN_NAME="nextflow_zymo"

# Убить существующую сессию если есть
screen -S "$SCREEN_NAME" -X quit 2>/dev/null || true

echo "🚀 Запуск Nextflow в screen сессии: $SCREEN_NAME"
echo "   Команда для подключения: screen -r $SCREEN_NAME"
echo

screen -dmS "$SCREEN_NAME" bash -c "
    cd /home/nicolaedrabcinski/upgrade && \
    nextflow run nextflow/main.nf \
        -profile docker \
        --input_dir '$INPUT_DIR' \
        --outdir '$OUTPUT_DIR' \
        --flye_genome_size '50m' \
        --flye_meta true \
        --threads 32 \
        -with-report '$OUTPUT_DIR/nextflow_report.html' \
        -with-timeline '$OUTPUT_DIR/nextflow_timeline.html' \
        -with-dag '$OUTPUT_DIR/nextflow_dag.html' \
        -resume 2>&1 | tee '$LOG_FILE'
"

sleep 2

echo "✅ Пайплайн запущен в фоне!"
echo

# Проверка что screen работает
if screen -list | grep -q "$SCREEN_NAME"; then
    echo "📊 СТАТУС:"
    echo "   ✅ Screen сессия активна: $SCREEN_NAME"
    screen -list | grep "$SCREEN_NAME"
    echo
    echo "📋 КОМАНДЫ:"
    echo "   • Подключиться: screen -r $SCREEN_NAME"
    echo "   • Отключиться: Ctrl+A, затем D"
    echo "   • Посмотреть лог: tail -f $LOG_FILE"
    echo "   • Остановить: screen -S $SCREEN_NAME -X quit"
    echo
else
    echo "❌ Screen сессия не запустилась"
    exit 1
fi

echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║                          ✅ ЗАПУЩЕНО!                                  ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
