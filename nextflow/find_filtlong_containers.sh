#!/bin/bash

# Скрипт для поиска рабочих контейнеров Filtlong
# Автор: Assistant
# Версия: 1.0

set -euo pipefail

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Поиск рабочих контейнеров Filtlong ===${NC}"
echo

# Функция для проверки наличия команд
check_dependencies() {
    local deps=("curl" "jq" "docker")
    local missing=()
    
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            missing+=("$dep")
        fi
    done
    
    if [ ${#missing[@]} -ne 0 ]; then
        echo -e "${RED}Отсутствуют зависимости: ${missing[*]}${NC}"
        echo "Установите их перед запуском скрипта"
        exit 1
    fi
}

# Функция для получения тегов из Quay.io
get_quay_tags() {
    local repo="$1"
    echo -e "${YELLOW}Получение тегов из quay.io/${repo}...${NC}"
    
    local url="https://quay.io/api/v1/repository/${repo}/tag/"
    local response
    
    if response=$(curl -s "$url" 2>/dev/null); then
        if echo "$response" | jq -e '.tags' >/dev/null 2>&1; then
            echo "$response" | jq -r '.tags[].name' | grep -E '^[0-9]' | sort -V | tail -10
        else
            echo -e "${RED}Ошибка получения тегов или репозиторий не найден${NC}"
            return 1
        fi
    else
        echo -e "${RED}Ошибка подключения к quay.io${NC}"
        return 1
    fi
}

# Функция для получения тегов из Docker Hub
get_dockerhub_tags() {
    local repo="$1"
    echo -e "${YELLOW}Получение тегов из Docker Hub ${repo}...${NC}"
    
    local url="https://registry.hub.docker.com/v2/repositories/${repo}/tags/"
    local response
    
    if response=$(curl -s "$url" 2>/dev/null); then
        if echo "$response" | jq -e '.results' >/dev/null 2>&1; then
            echo "$response" | jq -r '.results[].name' | grep -E '^[0-9]|latest' | sort -V | tail -10
        else
            echo -e "${RED}Ошибка получения тегов или репозиторий не найден${NC}"
            return 1
        fi
    else
        echo -e "${RED}Ошибка подключения к Docker Hub${NC}"
        return 1
    fi
}

# Функция для тестирования контейнера
test_container() {
    local image="$1"
    echo -e "${BLUE}Тестирование: ${image}${NC}"
    
    # Попытка скачать образ
    if docker pull "$image" >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Образ успешно скачан${NC}"
        
        # Тест команды filtlong --help
        if docker run --rm "$image" filtlong --help >/dev/null 2>&1; then
            echo -e "${GREEN}✓ Команда filtlong работает${NC}"
            
            # Получение версии
            local version
            version=$(docker run --rm "$image" filtlong --version 2>/dev/null | head -1 || echo "unknown")
            echo -e "${GREEN}✓ Версия: ${version}${NC}"
            
            echo -e "${GREEN}✓ КОНТЕЙНЕР РАБОЧИЙ: ${image}${NC}"
            echo "---"
            return 0
        else
            echo -e "${RED}✗ Команда filtlong не работает${NC}"
            echo "---"
            return 1
        fi
    else
        echo -e "${RED}✗ Ошибка скачивания образа${NC}"
        echo "---"
        return 1
    fi
}

# Функция для поиска в Bioconda
search_bioconda() {
    echo -e "${YELLOW}Поиск в Bioconda...${NC}"
    local url="https://api.anaconda.org/package/bioconda/filtlong"
    local response
    
    if response=$(curl -s "$url" 2>/dev/null); then
        if echo "$response" | jq -e '.versions' >/dev/null 2>&1; then
            echo "Доступные версии в Bioconda:"
            echo "$response" | jq -r '.versions[]' | sort -V | tail -5
        fi
    fi
    echo
}

# Основная функция
main() {
    check_dependencies
    
    echo -e "${BLUE}Начинаем поиск рабочих контейнеров...${NC}"
    echo
    
    # Массив репозиториев для проверки
    local repositories=(
        "biocontainers/filtlong"
        "staphb/filtlong"
        "quay.io/biocontainers/filtlong"
    )
    
    # Массив для хранения рабочих контейнеров
    local working_containers=()
    
    # Поиск в Quay.io biocontainers
    echo -e "${YELLOW}=== Поиск в Quay.io Biocontainers ===${NC}"
    if tags=$(get_quay_tags "biocontainers/filtlong"); then
        echo "Найденные теги:"
        echo "$tags"
        echo
        
        # Тестируем последние несколько тегов
        while read -r tag; do
            if [ -n "$tag" ]; then
                if test_container "quay.io/biocontainers/filtlong:$tag"; then
                    working_containers+=("quay.io/biocontainers/filtlong:$tag")
                fi
            fi
        done <<< "$(echo "$tags" | tail -3)"
    fi
    
    echo
    
    # Поиск в Docker Hub staphb
    echo -e "${YELLOW}=== Поиск в Docker Hub (staphb) ===${NC}"
    if tags=$(get_dockerhub_tags "staphb/filtlong"); then
        echo "Найденные теги:"
        echo "$tags"
        echo
        
        # Тестируем последние несколько тегов
        while read -r tag; do
            if [ -n "$tag" ]; then
                if test_container "staphb/filtlong:$tag"; then
                    working_containers+=("staphb/filtlong:$tag")
                fi
            fi
        done <<< "$(echo "$tags" | tail -3)"
    fi
    
    echo
    
    # Тестируем дополнительные известные варианты
    echo -e "${YELLOW}=== Тестирование дополнительных вариантов ===${NC}"
    additional_images=(
        "quay.io/biocontainers/filtlong:0.2.1--h9a82719_1"
        "quay.io/biocontainers/filtlong:0.2.1--hec16e2b_1" 
        "staphb/filtlong:latest"
        "staphb/filtlong:0.2.1"
        "biocontainers/filtlong:v0.2.1_cv1"
    )
    
    for image in "${additional_images[@]}"; do
        if test_container "$image"; then
            working_containers+=("$image")
        fi
    done
    
    # Поиск в Bioconda
    search_bioconda
    
    # Итоговый отчет
    echo -e "${BLUE}=== ИТОГОВЫЙ ОТЧЕТ ===${NC}"
    if [ ${#working_containers[@]} -gt 0 ]; then
        echo -e "${GREEN}Найдены рабочие контейнеры:${NC}"
        for container in "${working_containers[@]}"; do
            echo -e "${GREEN}✓ $container${NC}"
        done
        echo
        echo -e "${YELLOW}Рекомендация для Nextflow config:${NC}"
        echo "process {"
        echo "    withName: 'FILTLONG' {"
        echo "        container = '${working_containers[0]}'"
        echo "    }"
        echo "}"
        echo
        echo -e "${YELLOW}Или для Docker команды:${NC}"
        echo "docker run --rm ${working_containers[0]} filtlong --help"
    else
        echo -e "${RED}Рабочие контейнеры не найдены!${NC}"
        echo -e "${YELLOW}Попробуйте установить Filtlong через conda:${NC}"
        echo "conda install -c bioconda filtlong"
    fi
}

# Опции командной строки
case "${1:-}" in
    -h|--help)
        echo "Использование: $0 [опции]"
        echo "Опции:"
        echo "  -h, --help     Показать эту справку"
        echo "  -t, --test     Тестировать только указанный образ"
        echo
        echo "Примеры:"
        echo "  $0                                    # Полный поиск"
        echo "  $0 -t staphb/filtlong:latest         # Тест конкретного образа"
        exit 0
        ;;
    -t|--test)
        if [ $# -lt 2 ]; then
            echo -e "${RED}Ошибка: укажите образ для тестирования${NC}"
            exit 1
        fi
        check_dependencies
        test_container "$2"
        exit $?
        ;;
    "")
        main
        ;;
    *)
        echo -e "${RED}Неизвестная опция: $1${NC}"
        echo "Используйте -h для справки"
        exit 1
        ;;
esac