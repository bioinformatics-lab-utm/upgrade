#!/usr/bin/env python3
"""
Simplified Pipeline Summary Generator - Phase 1
Works with current pipeline output structure
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any
import re

class SimplePipelineSummary:
    """Generate basic summary from current pipeline outputs"""
    
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
            'mags': {'total_bins': 0, 'high_quality': 0, 'medium_quality': 0, 'low_quality': 0, 'bins': []},
            'taxonomy': {'total_classified': 0, 'species': [], 'risk_assessment': {'high': 0, 'moderate': 0, 'low': 0}},
            'amr': {'total_arg_genes': 0, 'high_risk': 0, 'moderate_risk': 0, 'risk_score': 0, 'genes': []},
            'recommendations': []
        }
    
    def parse_nanoplot_stats(self) -> Dict[str, Any]:
        """Parse NanoPlot QC statistics"""
        # Try different possible paths
        possible_paths = [
            self.results_dir / '01_QC' / 'nanoplot' / f'{self.sample_id}_nanoplot' / f'{self.sample_id}_NanoStats.txt',
            self.results_dir / '01_QC' / 'nanoplot' / f'{self.sample_id}_nanoplot' / 'NanoStats.txt',
        ]
        
        stats_file = None
        for path in possible_paths:
            if path.exists():
                stats_file = path
                break
        
        if not stats_file:
            print(f"⚠️  NanoStats.txt not found in {possible_paths[0].parent}")
            return {}
        
        print(f"✓ Found NanoStats: {stats_file}")
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
        # Try to find stats JSON
        stats_files = list(self.results_dir.glob('**/stats/*_assembly_stats.json'))
        
        if not stats_files:
            print(f"⚠️  Assembly stats JSON not found")
            return {}
        
        stats_file = stats_files[0]
        print(f"✓ Found assembly stats: {stats_file}")
        
        with open(stats_file) as f:
            stats = json.load(f)
        
        # Calculate assembly quality score (0-100)
        n50 = stats.get('n50', 0)
        contigs = stats.get('contigs', 999)
        longest = stats.get('longest_contig', 0)
        gc = stats.get('gc_content', 0)
        
        quality_score = (
            min(n50 / 100000, 1.0) * 40 +
            min(10 / contigs, 1.0) * 20 +
            min(longest / 500000, 1.0) * 20 +
            (40 <= gc <= 60) * 20
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
    
    def parse_amr_genes(self) -> Dict[str, Any]:
        """Parse AMR gene detection from Abricate"""
        amr_genes = []
        
        # Find abricate results
        abricate_dir = self.results_dir / f'{self.sample_id}_{self.sample_id}' / 'abricate'
        
        if not abricate_dir.exists():
            print(f"⚠️  Abricate directory not found: {abricate_dir}")
            return {
                'total_arg_genes': 0,
                'high_risk': 0,
                'moderate_risk': 0,
                'risk_score': 0,
                'genes': []
            }
        
        print(f"✓ Found AMR directory: {abricate_dir}")
        
        # WHO critical priority AMR genes
        critical_genes = ['blaNDM', 'blaKPC', 'blaOXA-48', 'mcr', 'vanA', 'vanB']
        
        for tsv_file in abricate_dir.glob('*.tsv'):
            if tsv_file.stat().st_size == 0:
                continue
            
            try:
                with open(tsv_file) as f:
                    lines = f.readlines()
                
                # Skip header
                for line in lines[1:]:
                    if not line.strip() or line.startswith('#'):
                        continue
                    
                    parts = line.strip().split('\t')
                    if len(parts) < 6:
                        continue
                    
                    gene = parts[5] if len(parts) > 5 else 'Unknown'
                    
                    # Determine risk level
                    if any(crit in gene for crit in critical_genes):
                        risk = 'high'
                    else:
                        risk = 'moderate'
                    
                    amr_genes.append({
                        'gene': gene,
                        'bin': tsv_file.stem.replace('_card', '').replace('_ncbi', '').replace('_resfinder', '').replace('_argannot', ''),
                        'antibiotic': parts[10] if len(parts) > 10 else 'Unknown',
                        'risk_level': risk,
                        'identity': float(parts[9]) if len(parts) > 9 else 0,
                        'coverage': float(parts[8]) if len(parts) > 8 else 0,
                        'database': tsv_file.stem.split('_')[-1]
                    })
            except Exception as e:
                print(f"⚠️  Error parsing {tsv_file}: {e}")
                continue
        
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
    
    def calculate_overall_quality_score(self) -> float:
        """Calculate overall quality score for the analysis"""
        qc_score = 100 if self.summary['qc'].get('quality_status') == 'excellent' else 70 if self.summary['qc'].get('quality_status') == 'good' else 40
        assembly_score = self.summary['assembly'].get('quality_score', 0)
        
        overall = (qc_score * 0.3 + assembly_score * 0.7)
        return round(overall, 1)
    
    def generate_recommendations(self) -> list:
        """Generate actionable recommendations"""
        recs = []
        
        # QC recommendations
        if self.summary['qc'].get('quality_status') == 'poor':
            recs.append('⚠️ Poor read quality detected. Consider re-sequencing.')
        elif self.summary['qc'].get('quality_status') == 'excellent':
            recs.append('✅ Excellent read quality.')
        
        # Assembly recommendations
        assembly_quality = self.summary['assembly'].get('quality_score', 0)
        if assembly_quality < 60:
            recs.append('⚠️ Assembly quality is poor. Check input data quality.')
        elif assembly_quality >= 80:
            recs.append('✅ Excellent assembly quality. Ready for downstream analysis.')
        
        # AMR recommendations
        amr_risk = self.summary['amr'].get('risk_score', 0)
        if amr_risk >= 7:
            recs.append('🔴 CRITICAL: High AMR risk detected. Immediate action required.')
            recs.append('💊 Recommend carbapenem + colistin combination therapy.')
        elif amr_risk >= 4:
            recs.append('🟡 Moderate AMR risk. Monitor closely.')
        
        if self.summary['amr'].get('total_arg_genes', 0) == 0:
            recs.append('✅ No AMR genes detected.')
        
        return recs
    
    def generate(self) -> Dict[str, Any]:
        """Generate complete summary"""
        print(f"\n🔬 Generating summary for {self.sample_id}...")
        print(f"📁 Results directory: {self.results_dir}")
        
        # Parse all components
        print("\n1️⃣  Parsing QC stats...")
        self.summary['qc'] = self.parse_nanoplot_stats()
        
        print("\n2️⃣  Parsing assembly stats...")
        self.summary['assembly'] = self.parse_assembly_stats()
        
        print("\n3️⃣  Parsing AMR genes...")
        self.summary['amr'] = self.parse_amr_genes()
        
        # Calculate scores
        print("\n4️⃣  Calculating scores...")
        self.summary['quality_score'] = self.calculate_overall_quality_score()
        self.summary['amr_risk_score'] = self.summary['amr'].get('risk_score', 0)
        
        # Generate recommendations
        print("\n5️⃣  Generating recommendations...")
        self.summary['recommendations'] = self.generate_recommendations()
        
        print("\n✅ Summary generation complete!")
        return self.summary


def main():
    if len(sys.argv) < 3:
        print("Usage: python generate_summary_simple.py <results_dir> <sample_id>")
        sys.exit(1)
    
    results_dir = sys.argv[1]
    sample_id = sys.argv[2]
    
    generator = SimplePipelineSummary(results_dir, sample_id)
    summary = generator.generate()
    
    # Write JSON output
    output_dir = Path(results_dir) / '00_summary'
    output_dir.mkdir(exist_ok=True, parents=True)
    
    output_file = output_dir / f'{sample_id}_summary.json'
    
    with open(output_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n📄 Summary saved to: {output_file}")
    print(f"\n📊 Results:")
    print(f"   Quality Score: {summary['quality_score']}/100")
    print(f"   AMR Risk Score: {summary['amr_risk_score']}/10")
    print(f"   AMR Genes: {summary['amr'].get('total_arg_genes', 0)}")
    print(f"\n💡 Recommendations:")
    for rec in summary['recommendations']:
        print(f"   {rec}")


if __name__ == '__main__':
    main()
