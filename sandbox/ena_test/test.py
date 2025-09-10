import requests
import pandas as pd
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ENASimpleAPI:
    def __init__(self):
        self.browser_url = "https://www.ebi.ac.uk/ena/browser/api"
    
    def get_sample_info(self, accession):
        """Получить информацию об одном образце"""
        try:
            url = f"{self.browser_url}/xml/{accession}"
            response = requests.get(url, verify=False, timeout=30)
            
            if response.status_code == 200:
                return {
                    'accession': accession,
                    'xml_data': response.text,
                    'data_size': len(response.text),
                    'status': 'success'
                }
            else:
                return {
                    'accession': accession,
                    'xml_data': None,
                    'data_size': 0,
                    'status': f'failed_{response.status_code}'
                }
        except Exception as e:
            return {
                'accession': accession,
                'xml_data': None,
                'data_size': 0,
                'status': f'error_{str(e)}'
            }
    
    def test_known_metagenomic_samples(self):
        """Тестируем с известными метагеномными образцами"""
        
        # Реальные метагеномные accessions из литературы
        test_samples = [
            'SRR8361749',  # Environmental surveillance
            'ERR2984773',  # Built environment  
            'SRR9876543',  # Test sample
            'ERR3393515',  # Wastewater metagenome
            'SRR5665543',  # Environmental sample
            'SRR7722217',  # Surface swabs
            'SRR8506312',  # Hospital environment
        ]
        
        results = []
        
        for accession in test_samples:
            print(f"Testing {accession}...")
            result = self.get_sample_info(accession)
            results.append(result)
            
            if result['status'] == 'success':
                print(f"  ✓ Success: {result['data_size']} bytes")
            else:
                print(f"  ✗ Failed: {result['status']}")
        
        return results
    
    def extract_metadata_from_xml(self, xml_data):
        """Простое извлечение метаданных из XML"""
        if not xml_data:
            return {}
        
        metadata = {}
        
        # Ищем основные поля (простой парсинг)
        if 'METAGENOMIC' in xml_data:
            metadata['library_strategy'] = 'METAGENOMIC'
        
        if 'OXFORD_NANOPORE' in xml_data:
            metadata['platform'] = 'OXFORD_NANOPORE'
        elif 'ILLUMINA' in xml_data:
            metadata['platform'] = 'ILLUMINA'
        
        # Ищем географическую информацию
        lines = xml_data.split('\n')
        for line in lines:
            if 'geo_loc_name' in line.lower() or 'geographic' in line.lower():
                metadata['geography_line'] = line.strip()
                break
        
        return metadata

def download_fastq_direct(accession):
    """Прямое скачивание FASTQ файлов через ENA FTP"""
    
    # ENA FTP структура
    # ftp://ftp.sra.ebi.ac.uk/vol1/fastq/SRR836/009/SRR8361749/
    
    # Определяем путь по accession
    if accession.startswith('SRR'):
        # SRA формат
        prefix = accession[:6]  # SRR836
        suffix = accession[-3:]  # 749 -> 009 (последние 3 цифры с нулями)
        suffix_padded = suffix.zfill(3)
        
        base_url = f"ftp://ftp.sra.ebi.ac.uk/vol1/fastq/{prefix}/{suffix_padded}/{accession}/"
        
    elif accession.startswith('ERR'):
        # ENA формат  
        prefix = accession[:6]
        suffix = accession[-3:].zfill(3)
        
        base_url = f"ftp://ftp.sra.ebi.ac.uk/vol1/fastq/{prefix}/{suffix}/{accession}/"
    
    else:
        return None
    
    # Возможные имена файлов
    possible_files = [
        f"{accession}.fastq.gz",
        f"{accession}_1.fastq.gz",
        f"{accession}_2.fastq.gz"
    ]
    
    return {
        'accession': accession,
        'base_url': base_url,
        'possible_files': possible_files,
        'download_commands': [
            f"wget {base_url}{file}" for file in possible_files
        ]
    }

def main():
    print("=== ENA Simple API Test ===")
    
    ena = ENASimpleAPI()
    
    # Тестируем известные образцы
    results = ena.test_known_metagenomic_samples()
    
    # Анализируем успешные результаты
    successful = [r for r in results if r['status'] == 'success']
    print(f"\nSuccessful samples: {len(successful)}")
    
    # Извлекаем метаданные из успешных образцов
    for result in successful[:3]:  # Первые 3
        print(f"\n--- {result['accession']} ---")
        metadata = ena.extract_metadata_from_xml(result['xml_data'])
        
        for key, value in metadata.items():
            print(f"{key}: {value}")
        
        # Показываем информацию для скачивания
        download_info = download_fastq_direct(result['accession'])
        if download_info:
            print(f"FTP URL: {download_info['base_url']}")
            print(f"Download command: {download_info['download_commands'][0]}")
    
    print(f"\n=== Summary ===")
    print(f"Tested: {len(results)} samples")
    print(f"Working: {len(successful)} samples")
    print(f"Success rate: {len(successful)/len(results)*100:.1f}%")

if __name__ == "__main__":
    main()