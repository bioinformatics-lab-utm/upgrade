#!/usr/bin/env python3
"""
NCBI SRA Filter Explorer - Test available filters and data for UPGRADE project
Similar to ENA explorer but using NCBI SRA API
"""

import requests
import json
import time
from typing import Dict, List, Optional

class NCBISRAFilterExplorer:
    def __init__(self):
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        self.results = {}
        
    def search_sra(self, query: str, retmax: int = 1) -> int:
        """
        Search SRA using E-utilities
        Returns count of matching records
        """
        try:
            # Use esearch to get count
            search_url = f"{self.base_url}/esearch.fcgi"
            params = {
                'db': 'sra',
                'term': query,
                'retmax': retmax,
                'retmode': 'json'
            }
            
            response = requests.get(search_url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if 'esearchresult' in data and 'count' in data['esearchresult']:
                    count = int(data['esearchresult']['count'])
                    return count
                else:
                    print(f"Unexpected response format for query: {query}")
                    return 0
            else:
                print(f"HTTP {response.status_code} for query: {query}")
                return 0
                
        except Exception as e:
            print(f"Request failed for '{query}': {str(e)}")
            return 0
            
    def test_library_strategies(self):
        """Test different library strategies"""
        print("=== Library Strategies ===")
        strategies = [
            'WGS', 'WXS', 'RNA-Seq', 'miRNA-Seq', 'ChIP-Seq', 'ATAC-seq',
            'Bisulfite-Seq', 'AMPLICON', 'METAGENOMIC', 'METATRANSCRIPTOMIC',
            'Targeted-Capture', 'Hi-C', 'CUT&RUN'
        ]
        
        strategy_counts = {}
        for strategy in strategies:
            query = f'"{strategy}"[Strategy]'
            count = self.search_sra(query)
            strategy_counts[strategy] = count
            print(f"{strategy:<20}: {count if count > 0 else 0}")
            time.sleep(0.5)  # Be nice to NCBI
            
        self.results['library_strategies'] = strategy_counts
        
    def test_platforms(self):
        """Test different sequencing platforms"""
        print("\n=== Sequencing Platforms ===")
        platforms = [
            'ILLUMINA', 'OXFORD_NANOPORE', 'PACBIO_SMRT', 'ION_TORRENT',
            'HELICOS', 'ABI_SOLID', 'COMPLETE_GENOMICS', '454'
        ]
        
        platform_counts = {}
        for platform in platforms:
            query = f'"{platform}"[Platform]'
            count = self.search_sra(query)
            platform_counts[platform] = count
            print(f"{platform:<20}: {count if count > 0 else 0}")
            time.sleep(0.5)
            
        self.results['platforms'] = platform_counts
        
    def test_library_sources(self):
        """Test different library sources"""
        print("\n=== Library Sources ===")
        sources = [
            'GENOMIC', 'TRANSCRIPTOMIC', 'METAGENOMIC', 'METATRANSCRIPTOMIC',
            'SYNTHETIC', 'VIRAL_RNA', 'OTHER'
        ]
        
        source_counts = {}
        for source in sources:
            query = f'"{source}"[Source]'
            count = self.search_sra(query)
            source_counts[source] = count
            print(f"{source:<20}: {count if count > 0 else 0}")
            time.sleep(0.5)
            
        self.results['library_sources'] = source_counts
        
    def test_metagenomic_combinations(self):
        """Test metagenomic data with different platforms - key for UPGRADE"""
        print("\n=== Metagenomic Combinations for UPGRADE ===")
        
        combinations = {
            'All metagenomic': '"METAGENOMIC"[Source]',
            'Metagenomic + Illumina': '"METAGENOMIC"[Source] AND "ILLUMINA"[Platform]',
            'Metagenomic + Nanopore': '"METAGENOMIC"[Source] AND "OXFORD_NANOPORE"[Platform]',
            'Metagenomic strategy': '"METAGENOMIC"[Strategy]',
            'Metagenomic strategy + Illumina': '"METAGENOMIC"[Strategy] AND "ILLUMINA"[Platform]',
            'Metagenomic strategy + Nanopore': '"METAGENOMIC"[Strategy] AND "OXFORD_NANOPORE"[Platform]',
        }
        
        metagenomic_counts = {}
        for name, query in combinations.items():
            count = self.search_sra(query)
            metagenomic_counts[name] = count
            print(f"{name:<35}: {count if count > 0 else 0}")
            time.sleep(0.5)
            
        self.results['metagenomic_combinations'] = metagenomic_counts
        
    def test_geographic_filters(self):
        """Test geographic filtering - important for Romania/Moldova focus"""
        print("\n=== Geographic Filters Test ===")
        
        geo_queries = {
            'Romania samples': 'Romania[Country]',
            'Moldova samples': 'Moldova[Country]',
            'Eastern Europe': '("Romania"[Country] OR "Moldova"[Country] OR "Bulgaria"[Country])',
            'University samples': 'university[All Fields]',
            'Campus samples': 'campus[All Fields]',
            'Urban samples': 'urban[All Fields]'
        }
        
        geo_counts = {}
        for name, query in geo_queries.items():
            count = self.search_sra(query)
            geo_counts[name] = count
            print(f"{name:<25}: {count if count > 0 else 0}")
            time.sleep(0.5)
            
        self.results['geographic_filters'] = geo_counts
        
    def test_antimicrobial_resistance(self):
        """Test AMR-related data - core focus of UPGRADE"""
        print("\n=== Antimicrobial Resistance Data ===")
        
        amr_queries = {
            'Antimicrobial resistance': 'antimicrobial resistance[All Fields]',
            'Antibiotic resistance': 'antibiotic resistance[All Fields]',
            'AMR': 'AMR[All Fields]',
            'Resistance genes': 'resistance genes[All Fields]',
            'ARG': 'ARG[All Fields]',
            'Beta-lactamase': 'beta-lactamase[All Fields]',
            'ESBL': 'ESBL[All Fields]',
            'Carbapenemase': 'carbapenemase[All Fields]',
            'ESCAPE pathogens': 'ESCAPE[All Fields]',
            'Acinetobacter': 'Acinetobacter[Organism]',
            'Pseudomonas': 'Pseudomonas[Organism]'
        }
        
        amr_counts = {}
        for name, query in amr_queries.items():
            count = self.search_sra(query)
            amr_counts[name] = count
            print(f"{name:<25}: {count if count > 0 else 0}")
            time.sleep(0.5)
            
        self.results['amr_data'] = amr_counts
        
    def test_environmental_samples(self):
        """Test environmental sample types relevant to UPGRADE"""
        print("\n=== Environmental Samples ===")
        
        env_queries = {
            'Wastewater': 'wastewater[All Fields]',
            'Sewage': 'sewage[All Fields]',
            'Campus environment': 'campus environment[All Fields]',
            'University environment': 'university environment[All Fields]',
            'Public spaces': 'public spaces[All Fields]',
            'Environmental surveillance': 'environmental surveillance[All Fields]',
            'Surface samples': 'surface samples[All Fields]',
            'Door handles': 'door handles[All Fields]',
            'Restaurant surfaces': 'restaurant surfaces[All Fields]',
            'Laboratory surfaces': 'laboratory surfaces[All Fields]'
        }
        
        env_counts = {}
        for name, query in env_queries.items():
            count = self.search_sra(query)
            env_counts[name] = count
            print(f"{name:<25}: {count if count > 0 else 0}")
            time.sleep(0.5)
            
        self.results['environmental_samples'] = env_counts
        
    def test_combined_upgrade_queries(self):
        """Test queries combining multiple UPGRADE project interests"""
        print("\n=== Combined UPGRADE Queries ===")
        
        combined_queries = {
            'Metagenomic + AMR': '"METAGENOMIC"[Source] AND antimicrobial resistance[All Fields]',
            'Environmental + AMR': 'environmental[All Fields] AND antimicrobial resistance[All Fields]',
            'Nanopore + Metagenomic': '"OXFORD_NANOPORE"[Platform] AND "METAGENOMIC"[Source]',
            'University + Metagenomic': 'university[All Fields] AND "METAGENOMIC"[Source]',
            'Surveillance + Pathogen': 'surveillance[All Fields] AND pathogen[All Fields]',
            'Campus + Microbial': 'campus[All Fields] AND microbial[All Fields]'
        }
        
        combined_counts = {}
        for name, query in combined_queries.items():
            count = self.search_sra(query)
            combined_counts[name] = count
            print(f"{name:<25}: {count if count > 0 else 0}")
            time.sleep(0.5)
            
        self.results['combined_upgrade_queries'] = combined_counts
        
    def get_sample_details(self, query: str, retmax: int = 5):
        """Get sample details for a specific query"""
        try:
            # First search
            search_url = f"{self.base_url}/esearch.fcgi"
            search_params = {
                'db': 'sra',
                'term': query,
                'retmax': retmax,
                'retmode': 'json'
            }
            
            search_response = requests.get(search_url, params=search_params, timeout=30)
            if search_response.status_code != 200:
                return []
                
            search_data = search_response.json()
            if 'esearchresult' not in search_data or 'idlist' not in search_data['esearchresult']:
                return []
                
            ids = search_data['esearchresult']['idlist']
            if not ids:
                return []
                
            # Get summaries
            summary_url = f"{self.base_url}/esummary.fcgi"
            summary_params = {
                'db': 'sra',
                'id': ','.join(ids[:retmax]),
                'retmode': 'json'
            }
            
            summary_response = requests.get(summary_url, params=summary_params, timeout=30)
            if summary_response.status_code != 200:
                return []
                
            summary_data = summary_response.json()
            samples = []
            
            if 'result' in summary_data:
                for id_key, sample_data in summary_data['result'].items():
                    if id_key != 'uids' and isinstance(sample_data, dict):
                        samples.append({
                            'accession': sample_data.get('accession', 'N/A'),
                            'title': sample_data.get('title', 'N/A')[:100],
                            'platform': sample_data.get('platform', 'N/A'),
                            'strategy': sample_data.get('strategy', 'N/A')
                        })
                        
            return samples
            
        except Exception as e:
            print(f"Error getting sample details: {str(e)}")
            return []
            
    def run_full_exploration(self):
        """Run complete exploration"""
        print("NCBI SRA Filter Explorer - Discovering available data for UPGRADE")
        print("=" * 70)
        
        self.test_library_strategies()
        self.test_platforms()
        self.test_library_sources()
        self.test_metagenomic_combinations()
        self.test_geographic_filters()
        self.test_antimicrobial_resistance()
        self.test_environmental_samples()
        self.test_combined_upgrade_queries()
        
        # Summary
        print("\n=== SUMMARY ===")
        total_strategies = sum(1 for count in self.results.get('library_strategies', {}).values() if count > 0)
        total_platforms = sum(1 for count in self.results.get('platforms', {}).values() if count > 0)
        total_amr = sum(1 for count in self.results.get('amr_data', {}).values() if count > 0)
        
        print(f"Library strategies with data: {total_strategies}")
        print(f"Platforms with data: {total_platforms}")
        print(f"AMR-related datasets: {total_amr}")
        
        # Show some example datasets
        print("\n=== Example Relevant Datasets ===")
        relevant_queries = [
            '"METAGENOMIC"[Source] AND "ILLUMINA"[Platform]',
            'antimicrobial resistance[All Fields] AND environmental[All Fields]',
            '"OXFORD_NANOPORE"[Platform] AND "METAGENOMIC"[Source]'
        ]
        
        for query in relevant_queries:
            samples = self.get_sample_details(query, 3)
            if samples:
                print(f"\nQuery: {query}")
                for sample in samples:
                    print(f"  {sample['accession']}: {sample['title']}")
                    print(f"    Platform: {sample['platform']}, Strategy: {sample['strategy']}")
            time.sleep(1)
        
        print("\n=== Recommendations for UPGRADE ===")
        print("1. NCBI SRA has extensive metagenomic data")
        print("2. Good AMR-related datasets available")
        print("3. Both Illumina and Nanopore data present")
        print("4. Consider focusing on environmental + AMR combinations")
        print("5. University/campus data is limited but present")
        
        # Save results
        with open('ncbi_sra_exploration.json', 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"\nDetailed results saved to: ncbi_sra_exploration.json")

if __name__ == "__main__":
    explorer = NCBISRAFilterExplorer()
    explorer.run_full_exploration()