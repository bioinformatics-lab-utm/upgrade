#!/usr/bin/env python3
"""
ENA Filter Explorer - исследование доступных фильтров и подсчет данных
"""

import requests
import urllib3
import json
from collections import defaultdict, Counter

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ENAFilterExplorer:
    def __init__(self):
        self.portal_url = "https://www.ebi.ac.uk/ena/portal/api"
        
    def _make_request(self, endpoint, params):
        """Безопасный запрос с обработкой ошибок"""
        try:
            url = f"{self.portal_url}/{endpoint}"
            response = requests.get(url, params=params, verify=False, timeout=30)
            
            if response.status_code == 200:
                return response.text
            else:
                print(f"HTTP {response.status_code}: {response.text[:200]}")
                return None
                
        except Exception as e:
            print(f"Request failed: {e}")
            return None
    
    def count_records(self, query, result_type='read_run'):
        """Подсчет количества записей по запросу"""
        
        params = {
            'result': result_type,
            'query': query,
            'format': 'json',
            'limit': 0,  # Только подсчет, без данных
            'fields': 'run_accession'
        }
        
        # Сначала пробуем получить count
        count_params = params.copy()
        count_params['format'] = 'json'
        count_params['limit'] = 1
        
        result = self._make_request('search', count_params)
        if result:
            try:
                import json
                data = json.loads(result)
                if isinstance(data, list):
                    return len(data) if len(data) == 1 else "1000+"
                else:
                    return "unknown"
            except:
                pass
        
        return 0
    
    def explore_library_strategies(self):
        """Исследование доступных library strategies"""
        
        print("=== Library Strategies ===")
        
        strategies = [
            'WGS',
            'AMPLICON', 
            'RNA-Seq',
            'ChIP-Seq',
            'ATAC-seq',
            'Bisulfite-Seq',
            'CUT&RUN',
            'Hi-C',
            'METAGENOMIC',
            'METATRANSCRIPTOMIC'
        ]
        
        results = {}
        
        for strategy in strategies:
            query = f'library_strategy="{strategy}"'
            count = self.count_records(query)
            results[strategy] = count
            print(f"{strategy:20}: {count}")
        
        return results
    
    def explore_platforms(self):
        """Исследование доступных платформ секвенирования"""
        
        print("\n=== Sequencing Platforms ===")
        
        platforms = [
            'ILLUMINA',
            'OXFORD_NANOPORE', 
            'PACBIO_SMRT',
            'ION_TORRENT',
            'HELICOS',
            'ABI_SOLID',
            'COMPLETE_GENOMICS'
        ]
        
        results = {}
        
        for platform in platforms:
            query = f'platform="{platform}"'
            count = self.count_records(query)
            results[platform] = count
            print(f"{platform:20}: {count}")
        
        return results
    
    def explore_library_sources(self):
        """Исследование источников библиотек"""
        
        print("\n=== Library Sources ===")
        
        sources = [
            'GENOMIC',
            'TRANSCRIPTOMIC', 
            'METAGENOMIC',
            'METATRANSCRIPTOMIC',
            'SYNTHETIC',
            'VIRAL_RNA',
            'OTHER'
        ]
        
        results = {}
        
        for source in sources:
            query = f'library_source="{source}"'
            count = self.count_records(query)
            results[source] = count
            print(f"{source:20}: {count}")
        
        return results
    
    def explore_metagenomic_combinations(self):
        """Исследование метагеномных комбинаций для UPGRADE"""
        
        print("\n=== Metagenomic Combinations for UPGRADE ===")
        
        combinations = [
            ('library_strategy="METAGENOMIC"', 'All metagenomic'),
            ('library_strategy="METAGENOMIC" AND platform="ILLUMINA"', 'Metagenomic + Illumina'),
            ('library_strategy="METAGENOMIC" AND platform="OXFORD_NANOPORE"', 'Metagenomic + Nanopore'),
            ('library_source="METAGENOMIC"', 'Metagenomic source'),
            ('library_source="METAGENOMIC" AND platform="ILLUMINA"', 'Metagenomic source + Illumina'),
            ('library_source="METAGENOMIC" AND platform="OXFORD_NANOPORE"', 'Metagenomic source + Nanopore'),
        ]
        
        results = {}
        
        for query, description in combinations:
            count = self.count_records(query)
            results[description] = count
            print(f"{description:35}: {count}")
        
        return results
    
    def test_geographic_filters(self):
        """Тестирование географических фильтров"""
        
        print("\n=== Geographic Filters Test ===")
        
        # Тестируем разные варианты географических запросов
        geo_tests = [
            ('geo_loc_name="Romania"', 'Romania exact match'),
            ('geo_loc_name="Moldova"', 'Moldova exact match'), 
            ('country="Romania"', 'Romania by country field'),
            ('country="Moldova"', 'Moldova by country field'),
        ]
        
        results = {}
        
        for query, description in geo_tests:
            count = self.count_records(query)
            results[description] = count
            print(f"{description:25}: {count}")
        
        return results
    
    def search_environmental_samples(self, limit=10):
        """Поиск environmental samples с метаданными"""
        
        print(f"\n=== Environmental Samples (top {limit}) ===")
        
        # Пробуем найти environmental samples
        queries = [
            'library_strategy="METAGENOMIC"',
            'library_source="METAGENOMIC"',
            'library_source="ENVIRONMENTAL"'
        ]
        
        for query in queries:
            params = {
                'result': 'read_run',
                'query': query,
                'format': 'tsv', 
                'limit': limit,
                'fields': 'run_accession,sample_accession,library_strategy,library_source,platform,instrument_model'
            }
            
            result = self._make_request('search', params)
            
            if result and len(result.strip()) > 0:
                print(f"\nQuery: {query}")
                lines = result.strip().split('\n')
                print(f"Found {len(lines)-1} samples:")
                
                # Показываем первые несколько строк
                for line in lines[:6]:  # Header + 5 samples
                    print(f"  {line}")
                
                if len(lines) > 6:
                    print(f"  ... and {len(lines)-6} more")
                
                return result
        
        print("No environmental samples found with tested queries")
        return None
    
    def get_available_fields(self):
        """Получение списка доступных полей"""
        
        print("\n=== Available Fields Test ===")
        
        # Тестируем запрос с максимальным количеством полей
        all_fields = [
            'run_accession', 'sample_accession', 'experiment_accession', 'study_accession',
            'library_strategy', 'library_source', 'library_selection', 'library_layout',
            'platform', 'instrument_model', 'instrument_platform',
            'fastq_ftp', 'fastq_galaxy', 'fastq_aspera', 'fastq_bytes',
            'sample_title', 'sample_description', 
            'country', 'geo_loc_name', 'collection_date',
            'host', 'isolation_source', 'environment_biome'
        ]
        
        # Пробуем запрос с 1 sample чтобы проверить какие поля работают
        params = {
            'result': 'read_run',
            'query': 'library_strategy="WGS"',
            'format': 'tsv',
            'limit': 1,
            'fields': ','.join(all_fields)
        }
        
        result = self._make_request('search', params)
        
        if result:
            lines = result.strip().split('\n')
            if len(lines) >= 1:
                headers = lines[0].split('\t')
                print(f"Available fields ({len(headers)}):")
                
                for i, field in enumerate(headers, 1):
                    print(f"  {i:2d}. {field}")
                
                return headers
        
        return []

def main():
    explorer = ENAFilterExplorer()
    
    print("ENA Filter Explorer - Discovering available data and filters\n")
    
    # Исследуем основные фильтры
    strategies = explorer.explore_library_strategies()
    platforms = explorer.explore_platforms() 
    sources = explorer.explore_library_sources()
    
    # Специфично для метагеномики
    metagenomics = explorer.explore_metagenomic_combinations()
    
    # География
    geography = explorer.test_geographic_filters()
    
    # Доступные поля
    fields = explorer.get_available_fields()
    
    # Ищем примеры environmental samples
    samples = explorer.search_environmental_samples(5)
    
    # Резюме
    print(f"\n=== SUMMARY ===")
    print(f"Library strategies with data: {len([k for k,v in strategies.items() if v != 0])}")
    print(f"Platforms with data: {len([k for k,v in platforms.items() if v != 0])}")
    print(f"Available metadata fields: {len(fields)}")
    
    print(f"\n=== Recommendations for UPGRADE ===")
    if metagenomics.get('Metagenomic + Nanopore', 0) != 0:
        print(f"✓ Oxford Nanopore metagenomic data available: {metagenomics['Metagenomic + Nanopore']}")
    
    if metagenomics.get('Metagenomic + Illumina', 0) != 0:
        print(f"✓ Illumina metagenomic data available: {metagenomics['Metagenomic + Illumina']}")
    
    # Сохраняем результаты
    results = {
        'library_strategies': strategies,
        'platforms': platforms,
        'library_sources': sources,
        'metagenomic_combinations': metagenomics,
        'geographic_filters': geography,
        'available_fields': fields
    }
    
    with open('ena_filter_exploration.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nDetailed results saved to: ena_filter_exploration.json")

if __name__ == "__main__":
    main()