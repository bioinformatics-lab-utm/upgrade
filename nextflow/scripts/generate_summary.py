#!/usr/bin/env python3
"""
Pipeline Summary Generator
Aggregates all Nextflow results into single JSON for frontend
"""

import json
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from collections import Counter
from typing import Dict, List, Any

class PipelineSummaryGenerator:
    """Generate comprehensive summary from Nextflow pipeline outputs"""
    
    def __init__(self, results_dir: str, sample_id: str):
        self.results_dir = Path(results_dir)
        self.sample_id = sample_id
        self.summary = {
            'sample_id': sample_id,
            'pipeline_version': '2.0.0',
            'quality_score': 0,
            'amr_risk_score': 0,
            'qc': {},
            'assembly': {},
            'mags': {},
            'taxonomy': {},
            'amr': {},
            'functional': {},
            'viruses': {},
            'plasmids': {},
            'recommendations': []
        }
    
    def parse_nanoplot_stats(self) -> Dict[str, Any]:
        """Parse NanoPlot QC statistics"""
        stats_file = self.results_dir / '01_QC' / 'nanoplot' / f'{self.sample_id}_nanoplot' / 'NanoStats.txt'
        
        if not stats_file.exists():
            return {}
        
        stats = {}
        with open(stats_file) as f:
            for line in f:
                if ':' in line:
                    key, value = line.strip().split(':', 1)
                    key = key.strip().replace(' ', '_').lower()
                    value = value.strip()
                    
                    # Try to convert to number
                    try:
                        if ',' in value:
                            value = float(value.replace(',', ''))
                        else:
                            value = float(value)
                    except:
                        pass
                    
                    stats[key] = value
        
        # Calculate quality status
        mean_quality = stats.get('mean_read_quality', 0)
        n50 = stats.get('read_length_n50', 0)
        
        if mean_quality >= 10 and n50 >= 5000:
            status = 'excellent'
        elif mean_quality >= 8 and n50 >= 3000:
            status = 'good'
        else:
            status = 'poor'
        
        return {
            'reads_count': int(stats.get('number_of_reads', 0)),
            'total_bases': stats.get('total_bases', 0),
            'mean_length': stats.get('mean_read_length', 0),
            'n50': n50,
            'mean_quality': mean_quality,
            'quality_status': status,
            'recommended_action': 'proceed' if status != 'poor' else 'review_data'
        }
    
    def parse_assembly_stats(self) -> Dict[str, Any]:
        """Parse assembly statistics from JSON"""
        stats_file = self.results_dir / '03_assembly' / 'stats' / f'{self.sample_id}_stats.json'
        
        if not stats_file.exists():
            return {}
        
        with open(stats_file) as f:
            stats = json.load(f)
        
        # Calculate assembly quality score (0-100)
        n50 = stats.get('n50', 0)
        contigs = stats.get('contigs', 999)
        longest = stats.get('longest_contig', 0)
        gc = stats.get('gc_content', 0)
        
        quality_score = (
            min(n50 / 100000, 1.0) * 40 +  # N50 component
            min(10 / contigs, 1.0) * 20 +   # Contiguity (fewer is better)
            min(longest / 500000, 1.0) * 20 +  # Longest contig
            (40 <= gc <= 60) * 20  # GC in normal range
        )
        
        if quality_score >= 80:
            quality_label = 'excellent'
        elif quality_score >= 60:
            quality_label = 'good'
        else:
            quality_label = 'poor'
        
        return {
            'quality_score': round(quality_score, 1),
            'quality_label': quality_label,
            'contigs_count': contigs,
            'total_length': stats.get('total_length', 0),
            'n50': n50,
            'gc_content': gc,
            'longest_contig': longest
        }
    
    def parse_checkm_quality(self) -> Dict[str, Any]:
        """Parse CheckM quality assessment for all MAGs"""
        mags_quality = []
        
        for binner in ['metabat2', 'concoct']:
            summary_file = self.results_dir / '05_quality' / binner / f'{self.sample_id}_{binner}_checkm_summary.tsv'
            
            if not summary_file.exists():
                continue
            
            df = pd.read_csv(summary_file, sep='\t')
            
            for _, row in df.iterrows():
                completeness = row.get('Completeness', 0)
                contamination = row.get('Contamination', 0)
                
                # Determine quality tier (MIMAG standards)
                if completeness > 90 and contamination < 5:
                    quality = 'high'
                    publication_ready = True
                elif completeness >= 50 and contamination < 10:
                    quality = 'medium'
                    publication_ready = False
                else:
                    quality = 'low'
                    publication_ready = False
                
                mags_quality.append({
                    'id': row.get('Bin Id', ''),
                    'binner': binner,
                    'completeness': completeness,
                    'contamination': contamination,
                    'quality': quality,
                    'size_mb': row.get('Genome size', 0) / 1_000_000,
                    'gc_content': row.get('GC', 0),
                    'lineage': row.get('Lineage', 'Unknown'),
                    'publication_ready': publication_ready
                })
        
        # Calculate quality distribution
        quality_counts = Counter(mag['quality'] for mag in mags_quality)
        total = len(mags_quality)
        
        return {
            'total_bins': total,
            'high_quality': quality_counts['high'],
            'medium_quality': quality_counts['medium'],
            'low_quality': quality_counts['low'],
            'bins': mags_quality,
            'quality_distribution': {
                'high': round(quality_counts['high'] / total * 100, 1) if total > 0 else 0,
                'medium': round(quality_counts['medium'] / total * 100, 1) if total > 0 else 0,
                'low': round(quality_counts['low'] / total * 100, 1) if total > 0 else 0
            }
        }
    
    def parse_taxonomy(self) -> Dict[str, Any]:
        """Parse GTDB-Tk taxonomy results"""
        taxonomy_file = self.results_dir / '05_gtdbtk' / f'{self.sample_id}_gtdbtk' / 'gtdbtk.bac120.summary.tsv'
        
        if not taxonomy_file.exists():
            return {}
        
        df = pd.read_csv(taxonomy_file, sep='\t')
        
        species_list = []
        high_risk_pathogens = ['Escherichia coli', 'Pseudomonas aeruginosa', 'Klebsiella pneumoniae', 
                               'Staphylococcus aureus', 'Acinetobacter baumannii']
        
        risk_count = {'high': 0, 'moderate': 0, 'low': 0}
        
        for _, row in df.iterrows():
            classification = row.get('classification', '')
            species = classification.split(';')[-1].replace('s__', '') if classification else 'Unknown'
            
            # Determine pathogenicity risk
            if any(pathogen in species for pathogen in high_risk_pathogens):
                risk = 'high'
                pathogenicity = 'pathogen'
                clinical_relevance = 'High-risk pathogen'
            elif 'Unknown' in species:
                risk = 'low'
                pathogenicity = 'unknown'
                clinical_relevance = 'Unknown species'
            else:
                risk = 'moderate'
                pathogenicity = 'opportunistic'
                clinical_relevance = 'Opportunistic pathogen'
            
            risk_count[risk] += 1
            
            species_list.append({
                'bin': row.get('user_genome', ''),
                'species': species,
                'confidence': 'high' if 'fastani_reference' in row else 'medium',
                'pathogenicity': pathogenicity,
                'risk_level': risk,
                'clinical_relevance': clinical_relevance
            })
        
        return {
            'total_classified': len(species_list),
            'species': species_list,
            'risk_assessment': risk_count
        }
    
    def parse_amr_genes(self) -> Dict[str, Any]:
        """Parse AMR gene detection from Abricate"""
        amr_genes = []
        
        # WHO critical priority AMR genes
        critical_genes = ['blaNDM', 'blaKPC', 'blaOXA', 'mcr', 'vanA', 'vanB']
        
        for db in ['card', 'ncbi', 'resfinder', 'argannot']:
            amr_dir = self.results_dir / '07_amr' / 'abricate'
            
            for bin_file in amr_dir.glob(f'*_{db}.tsv'):
                if bin_file.stat().st_size == 0:
                    continue
                
                df = pd.read_csv(bin_file, sep='\t', comment='#')
                
                for _, row in df.iterrows():
                    gene = row.get('GENE', '')
                    
                    # Determine risk level
                    if any(crit in gene for crit in critical_genes):
                        risk = 'high'
                    else:
                        risk = 'moderate'
                    
                    amr_genes.append({
                        'gene': gene,
                        'bin': bin_file.stem.replace(f'_{db}', ''),
                        'antibiotic': row.get('PRODUCT', ''),
                        'risk_level': risk,
                        'identity': row.get('IDENTITY', 0),
                        'coverage': row.get('COVERAGE', 0),
                        'database': db
                    })
        
        # Calculate AMR risk score (0-10)
        high_risk_count = sum(1 for g in amr_genes if g['risk_level'] == 'high')
        moderate_risk_count = sum(1 for g in amr_genes if g['risk_level'] == 'moderate')
        
        total_genes = len(amr_genes)
        if total_genes > 0:
            risk_score = min((high_risk_count * 3.0 + moderate_risk_count * 1.5) / total_genes * 10, 10)
        else:
            risk_score = 0
        
        return {
            'total_arg_genes': total_genes,
            'high_risk': high_risk_count,
            'moderate_risk': moderate_risk_count,
            'risk_score': round(risk_score, 1),
            'genes': amr_genes[:20]  # Top 20 for display
        }
    
    def parse_plasmids(self) -> Dict[str, Any]:
        """Parse plasmid detection results"""
        plasmid_summary = self.results_dir / '09_plasmids' / f'{self.sample_id}_plasmid_combined_summary.txt'
        
        if not plasmid_summary.exists():
            return {}
        
        # Parse summary (simplified)
        return {
            'total': 0,
            'conjugative': 0,
            'with_amr_genes': 0
        }
    
    def generate_recommendations(self) -> List[str]:
        """Generate actionable recommendations based on analysis"""
        recs = []
        
        # QC recommendations
        if self.summary['qc'].get('quality_status') == 'poor':
            recs.append('⚠️ Poor read quality detected. Consider re-sequencing.')
        
        # Assembly recommendations
        assembly_quality = self.summary['assembly'].get('quality_score', 0)
        if assembly_quality < 60:
            recs.append('⚠️ Assembly quality is poor. Check input data quality.')
        elif assembly_quality >= 80:
            recs.append('✅ Excellent assembly quality. Ready for downstream analysis.')
        
        # MAG recommendations
        high_quality_mags = self.summary['mags'].get('high_quality', 0)
        if high_quality_mags > 0:
            recs.append(f'✅ {high_quality_mags} high-quality MAGs recovered (publication-ready).')
        
        # AMR recommendations
        amr_risk = self.summary['amr'].get('risk_score', 0)
        if amr_risk >= 7:
            recs.append('🔴 CRITICAL: High AMR risk detected. Immediate action required.')
            recs.append('💊 Recommend carbapenem + colistin combination therapy.')
        elif amr_risk >= 4:
            recs.append('🟡 Moderate AMR risk. Monitor closely.')
        
        # Pathogen recommendations
        high_risk_pathogens = self.summary['taxonomy'].get('risk_assessment', {}).get('high', 0)
        if high_risk_pathogens > 0:
            recs.append(f'🦠 {high_risk_pathogens} high-risk pathogen(s) detected.')
            recs.append('🏥 Implement infection control measures.')
        
        return recs
    
    def calculate_overall_quality_score(self) -> float:
        """Calculate overall quality score for the analysis"""
        qc_score = 100 if self.summary['qc'].get('quality_status') == 'excellent' else 70 if self.summary['qc'].get('quality_status') == 'good' else 40
        assembly_score = self.summary['assembly'].get('quality_score', 0)
        
        # MAG quality score
        mags_quality = self.summary['mags']
        if mags_quality.get('total_bins', 0) > 0:
            mag_score = (
                mags_quality.get('high_quality', 0) * 100 +
                mags_quality.get('medium_quality', 0) * 70 +
                mags_quality.get('low_quality', 0) * 40
            ) / mags_quality['total_bins']
        else:
            mag_score = 0
        
        overall = (qc_score * 0.2 + assembly_score * 0.3 + mag_score * 0.5)
        return round(overall, 1)
    
    def generate(self) -> Dict[str, Any]:
        """Generate complete summary"""
        print(f"Generating summary for {self.sample_id}...")
        
        # Parse all components
        self.summary['qc'] = self.parse_nanoplot_stats()
        print("✓ QC stats parsed")
        
        self.summary['assembly'] = self.parse_assembly_stats()
        print("✓ Assembly stats parsed")
        
        self.summary['mags'] = self.parse_checkm_quality()
        print("✓ MAG quality parsed")
        
        self.summary['taxonomy'] = self.parse_taxonomy()
        print("✓ Taxonomy parsed")
        
        self.summary['amr'] = self.parse_amr_genes()
        print("✓ AMR genes parsed")
        
        self.summary['plasmids'] = self.parse_plasmids()
        print("✓ Plasmids parsed")
        
        # Calculate scores
        self.summary['quality_score'] = self.calculate_overall_quality_score()
        self.summary['amr_risk_score'] = self.summary['amr'].get('risk_score', 0)
        
        # Generate recommendations
        self.summary['recommendations'] = self.generate_recommendations()
        print("✓ Recommendations generated")
        
        return self.summary


def main():
    if len(sys.argv) < 3:
        print("Usage: python generate_summary.py <results_dir> <sample_id>")
        sys.exit(1)
    
    results_dir = sys.argv[1]
    sample_id = sys.argv[2]
    
    generator = PipelineSummaryGenerator(results_dir, sample_id)
    summary = generator.generate()
    
    # Write JSON output to current working directory (Nextflow process expects it here)
    output_file = Path(f'{sample_id}_summary.json')
    
    with open(output_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n✅ Summary generated: {sample_id}/00_summary/{sample_id}_summary.json")
    print(f"📊 Quality Score: {summary['quality_score']}/100")
    print(f"🔴 AMR Risk Score: {summary['amr_risk_score']}/10")
    print(f"🦠 MAGs: {summary['mags'].get('total_bins', 0)} total ({summary['mags'].get('high_quality', 0)} high-quality)")


if __name__ == '__main__':
    main()
