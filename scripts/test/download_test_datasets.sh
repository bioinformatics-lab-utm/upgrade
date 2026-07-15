#!/bin/bash
set -e

echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║           📥 ЗАГРУЗКА МЕТАГЕНОМНЫХ ONT ДАТАСЕТОВ                       ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
echo

# Переменные
DATA_DIR="/home/nicolaedrabcinski/upgrade/data"
THREADS=16

# Функция загрузки через docker
download_sra() {
    local accession=$1
    local output_dir=$2
    local description=$3
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📦 Загрузка: $description ($accession)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    mkdir -p "$output_dir"
    
    # Используем docker с SRA toolkit
    docker run --rm \
        -v "$DATA_DIR":/data \
        ncbi/sra-tools:latest \
        bash -c "cd /data && prefetch $accession && fasterq-dump $accession --outdir /data/$output_dir --threads $THREADS --progress"
    
    # Сжать FASTQ
    echo "🗜️  Сжатие FASTQ файлов..."
    pigz -p $THREADS "$output_dir"/*.fastq 2>/dev/null || echo "Уже сжато или нет файлов"
    
    # Показать результат
    echo "✅ Загружено:"
    ls -lh "$output_dir"
    echo
}

# ═══════════════════════════════════════════════════════════════════════════
# 1. ZymoBIOMICS Mock Community (быстрый тест)
# ═══════════════════════════════════════════════════════════════════════════
echo
echo "1️⃣  ZymoBIOMICS Mock Community (SRR13128014)"
echo "   • Размер: ~5 GB"
echo "   • Время загрузки: 20-30 минут"
echo "   • Состав: 8 бактерий + 2 дрожжей"
echo

read -p "Загрузить ZymoBIOMICS? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    download_sra "SRR13128014" "zymo_mock" "ZymoBIOMICS Mock Community"
fi

# ═══════════════════════════════════════════════════════════════════════════
# 2. Warwick Mock (альтернативный mock)
# ═══════════════════════════════════════════════════════════════════════════
echo
echo "2️⃣  Warwick Mock Community (SRR9328963)"
echo "   • Размер: ~3 GB"
echo "   • Время загрузки: 15-20 минут"
echo "   • Состав: 12 бактерий"
echo

read -p "Загрузить Warwick Mock? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    download_sra "SRR9328963" "warwick_mock" "Warwick Mock Community"
fi

# ═══════════════════════════════════════════════════════════════════════════
# 3. Human Gut Metagenome (production тест)
# ═══════════════════════════════════════════════════════════════════════════
echo
echo "3️⃣  Human Gut Metagenome (SRR8494940)"
echo "   • Размер: ~20 GB"
echo "   • Время загрузки: 2-3 часа"
echo "   • Состав: 500+ видов, реальные AMR гены"
echo

read -p "Загрузить Human Gut? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    download_sra "SRR8494940" "gut_metagenome" "Human Gut Metagenome"
fi

# ═══════════════════════════════════════════════════════════════════════════
# Дополнительно: Поиск CAMI с ONT
# ═══════════════════════════════════════════════════════════════════════════
echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 CAMI датасеты:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo "CAMI I & II в основном Illumina, НО есть интересные опции:"
echo
echo "• CAMI Toy Dataset (маленький для теста):"
echo "  wget https://data.cami-challenge.org/participate/CAMI_I_MEDIUM.tar.gz"
echo
echo "• Для ONT метагеномики лучше использовать:"
echo "  - ZymoBIOMICS (идеально для валидации)"
echo "  - Реальные gut/soil/water metagenomes с SRA"
echo

echo
echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║                         ✅ ЗАГРУЗКА ЗАВЕРШЕНА                          ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
echo
echo "📊 Загруженные датасеты:"
du -sh "$DATA_DIR"/zymo_mock 2>/dev/null || echo "  zymo_mock: не загружен"
du -sh "$DATA_DIR"/warwick_mock 2>/dev/null || echo "  warwick_mock: не загружен"
du -sh "$DATA_DIR"/gut_metagenome 2>/dev/null || echo "  gut_metagenome: не загружен"
echo
echo "🚀 Следующий шаг: запустить пайплайн"
echo "   nextflow run nextflow/main.nf --input_dir data/zymo_mock --outdir results/zymo_test"

