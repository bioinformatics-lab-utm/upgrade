#!/bin/bash
set -e

echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║      🚀 ТЕСТ NEXTFLOW PIPELINE НА SRR11836760                      ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo

SAMPLE_ID="SRR11836760"
INPUT_DIR="data/${SAMPLE_ID}/raw"
OUTPUT_DIR="results/${SAMPLE_ID}_test"

echo "📊 ПАРАМЕТРЫ ТЕСТА:"
echo "   • Семпл: $SAMPLE_ID"
echo "   • Входные данные: $INPUT_DIR"
echo "   • Выходная директория: $OUTPUT_DIR"
echo "   • FASTQ размер: 448M"
echo

# Проверка входных файлов
echo "🔍 Проверка входных файлов..."
if [ ! -f "$INPUT_DIR/${SAMPLE_ID}.fastq.gz" ]; then
    echo "❌ FASTQ.gz не найден!"
    exit 1
fi

ls -lh "$INPUT_DIR/${SAMPLE_ID}.fastq.gz"
echo "✅ FASTQ файл найден"
echo

# Запуск Nextflow
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 ЗАПУСК NEXTFLOW PIPELINE..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

nextflow run nextflow/main.nf \
    --input_dir "$INPUT_DIR" \
    --outdir "$OUTPUT_DIR" \
    --flye_mode '--nano-raw' \
    --flye_genome_size '5m' \
    --flye_meta true \
    --threads 32 \
    -with-report "${OUTPUT_DIR}/nextflow_report.html" \
    -with-timeline "${OUTPUT_DIR}/nextflow_timeline.html" \
    -with-dag "${OUTPUT_DIR}/nextflow_dag.html" \
    -resume

echo
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║                        ✅ ТЕСТ ЗАВЕРШЕН                            ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo
echo "📊 РЕЗУЛЬТАТЫ:"
du -sh "$OUTPUT_DIR"
echo
echo "📋 ОТЧЕТЫ:"
ls -lh "${OUTPUT_DIR}"/*.html 2>/dev/null || echo "Отчеты будут созданы после завершения"
echo
echo "🔍 ПРОВЕРИТЬ РЕЗУЛЬТАТЫ:"
echo "   • Assembly: $OUTPUT_DIR/assembly/"
echo "   • Bins: $OUTPUT_DIR/bins/"
echo "   • QC: $OUTPUT_DIR/qc/"
echo "   • AMR: $OUTPUT_DIR/amr/"

