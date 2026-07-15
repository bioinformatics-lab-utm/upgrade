#!/usr/bin/env python3
"""
Nextflow Trace Analyzer

Analyzes Nextflow trace files to identify performance bottlenecks and optimization opportunities.

Features:
- Parse all trace files in results directory
- Identify slowest processes
- Calculate resource utilization (CPU, memory)
- Detect inefficient tasks
- Generate optimization recommendations

Usage:
    python scripts/analyze_nextflow_trace.py [--output reports/trace_analysis.json]
"""
import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict
import csv
from datetime import datetime


def parse_args():
    parser = argparse.ArgumentParser(description="Analyze Nextflow trace files for performance bottlenecks")
    parser.add_argument('--results-dir', type=str, default='results', help='Results directory with trace files')
    parser.add_argument('--output', type=str, default='reports/nextflow_trace_analysis.json', help='Output JSON report')
    parser.add_argument('--top-n', type=int, default=10, help='Number of top slowest processes to show')
    return parser.parse_args()


def parse_trace_file(trace_file: Path) -> List[Dict]:
    """Parse a single Nextflow trace file"""
    tasks = []
    
    try:
        with open(trace_file, 'r') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                # Parse duration and realtime to seconds
                duration_str = row.get('duration', '0s')
                realtime_str = row.get('realtime', '0s')
                
                duration_sec = parse_duration(duration_str)
                realtime_sec = parse_duration(realtime_str)
                
                # Parse CPU and memory usage
                cpu_pct = parse_percentage(row.get('%cpu', '0%'))
                mem_pct = parse_percentage(row.get('%mem', '0%'))
                
                # Parse memory values
                rss = parse_memory(row.get('rss', '0 MB'))
                vmem = parse_memory(row.get('vmem', '0 MB'))
                peak_rss = parse_memory(row.get('peak_rss', '0 MB'))
                
                task = {
                    'task_id': row.get('task_id'),
                    'process': row.get('process'),
                    'tag': row.get('tag'),
                    'status': row.get('status'),
                    'exit': row.get('exit'),
                    'duration_sec': duration_sec,
                    'realtime_sec': realtime_sec,
                    'cpu_pct': cpu_pct,
                    'mem_pct': mem_pct,
                    'rss_mb': rss,
                    'vmem_mb': vmem,
                    'peak_rss_mb': peak_rss,
                    'cpus': int(row.get('cpus', 1)),
                    'trace_file': str(trace_file)
                }
                tasks.append(task)
                
    except Exception as e:
        print(f"Error parsing {trace_file}: {e}")
    
    return tasks


def parse_duration(duration_str: str) -> float:
    """Convert duration string like '1m 30s' or '2h 15m' or '500ms' to seconds"""
    if not duration_str or duration_str == '-':
        return 0.0
    
    total_seconds = 0.0
    
    # Handle single value with unit (e.g., '500ms', '30s', '5m')
    duration_str = duration_str.strip()
    if ' ' not in duration_str:
        # Single unit
        if duration_str.endswith('ms'):
            try:
                return float(duration_str[:-2]) / 1000
            except ValueError:
                return 0.0
        elif duration_str.endswith('s'):
            try:
                return float(duration_str[:-1])
            except ValueError:
                return 0.0
        elif duration_str.endswith('m'):
            try:
                return float(duration_str[:-1]) * 60
            except ValueError:
                return 0.0
        elif duration_str.endswith('h'):
            try:
                return float(duration_str[:-1]) * 3600
            except ValueError:
                return 0.0
        elif duration_str.endswith('d'):
            try:
                return float(duration_str[:-1]) * 86400
            except ValueError:
                return 0.0
    
    # Handle multiple parts (e.g., '1m 30s')
    parts = duration_str.strip().split()
    
    for part in parts:
        part = part.strip()
        try:
            if part.endswith('ms'):
                total_seconds += float(part[:-2]) / 1000
            elif part.endswith('d'):
                total_seconds += float(part[:-1]) * 86400
            elif part.endswith('h'):
                total_seconds += float(part[:-1]) * 3600
            elif part.endswith('m'):
                total_seconds += float(part[:-1]) * 60
            elif part.endswith('s'):
                total_seconds += float(part[:-1])
        except ValueError:
            continue
    
    return total_seconds


def parse_percentage(pct_str: str) -> float:
    """Parse percentage string like '123.4%' to float"""
    if not pct_str or pct_str == '-':
        return 0.0
    return float(pct_str.rstrip('%'))


def parse_memory(mem_str: str) -> float:
    """Parse memory string like '1.5 GB' to MB"""
    if not mem_str or mem_str == '-':
        return 0.0
    
    parts = mem_str.strip().split()
    if len(parts) < 2:
        return 0.0
    
    value = float(parts[0])
    unit = parts[1].upper()
    
    if unit == 'GB':
        return value * 1024
    elif unit == 'MB':
        return value
    elif unit == 'KB':
        return value / 1024
    elif unit == 'B':
        return value / (1024 * 1024)
    
    return value


def analyze_tasks(tasks: List[Dict]) -> Dict:
    """Analyze tasks to identify bottlenecks and inefficiencies"""
    if not tasks:
        return {}
    
    # Filter completed tasks
    completed = [t for t in tasks if t['status'] == 'COMPLETED']
    failed = [t for t in tasks if t['status'] != 'COMPLETED']
    
    # Sort by duration
    slowest = sorted(completed, key=lambda x: x['duration_sec'], reverse=True)[:10]
    
    # Calculate total runtime
    total_duration = sum(t['duration_sec'] for t in completed)
    
    # Group by process
    by_process = {}
    for task in completed:
        proc = task['process']
        if proc not in by_process:
            by_process[proc] = []
        by_process[proc].append(task)
    
    # Calculate per-process stats
    process_stats = {}
    for proc, proc_tasks in by_process.items():
        total_time = sum(t['duration_sec'] for t in proc_tasks)
        avg_time = total_time / len(proc_tasks)
        avg_cpu = sum(t['cpu_pct'] for t in proc_tasks) / len(proc_tasks)
        avg_mem = sum(t['mem_pct'] for t in proc_tasks) / len(proc_tasks)
        max_mem = max(t['peak_rss_mb'] for t in proc_tasks)
        
        process_stats[proc] = {
            'count': len(proc_tasks),
            'total_time_sec': total_time,
            'avg_time_sec': avg_time,
            'avg_cpu_pct': avg_cpu,
            'avg_mem_pct': avg_mem,
            'max_memory_mb': max_mem,
            'pct_of_total': (total_time / total_duration * 100) if total_duration > 0 else 0
        }
    
    # Identify inefficiencies
    inefficient = []
    for task in completed:
        # Low CPU utilization (<50% average)
        if task['cpu_pct'] < 50 and task['duration_sec'] > 10:
            inefficient.append({
                'task_id': task['task_id'],
                'process': task['process'],
                'issue': 'Low CPU utilization',
                'cpu_pct': task['cpu_pct'],
                'duration_sec': task['duration_sec']
            })
        
        # High memory usage (>80%)
        if task['mem_pct'] > 80:
            inefficient.append({
                'task_id': task['task_id'],
                'process': task['process'],
                'issue': 'High memory usage',
                'mem_pct': task['mem_pct'],
                'peak_rss_mb': task['peak_rss_mb']
            })
    
    return {
        'summary': {
            'total_tasks': len(tasks),
            'completed': len(completed),
            'failed': len(failed),
            'total_runtime_sec': total_duration,
            'total_runtime_hours': total_duration / 3600
        },
        'slowest_tasks': [
            {
                'process': t['process'],
                'tag': t['tag'],
                'duration_sec': t['duration_sec'],
                'duration_min': t['duration_sec'] / 60,
                'cpu_pct': t['cpu_pct'],
                'mem_pct': t['mem_pct'],
                'peak_rss_mb': t['peak_rss_mb']
            }
            for t in slowest
        ],
        'process_stats': process_stats,
        'inefficient_tasks': inefficient[:20],  # Top 20 inefficiencies
        'failed_tasks': [
            {
                'process': t['process'],
                'tag': t['tag'],
                'status': t['status'],
                'exit': t['exit']
            }
            for t in failed
        ]
    }


def generate_recommendations(analysis: Dict) -> List[str]:
    """Generate optimization recommendations based on analysis"""
    recommendations = []
    
    process_stats = analysis.get('process_stats', {})
    
    # Identify top time consumers
    sorted_procs = sorted(process_stats.items(), key=lambda x: x[1]['pct_of_total'], reverse=True)
    
    if sorted_procs:
        top_proc = sorted_procs[0]
        if top_proc[1]['pct_of_total'] > 40:
            recommendations.append(
                f"⚠️ {top_proc[0]} consumes {top_proc[1]['pct_of_total']:.1f}% of total runtime "
                f"({top_proc[1]['total_time_sec']/3600:.1f}h). Consider optimizing this process."
            )
    
    # Check for low CPU utilization
    low_cpu_procs = [
        (proc, stats) for proc, stats in process_stats.items()
        if stats['avg_cpu_pct'] < 100 and stats['pct_of_total'] > 10
    ]
    
    if low_cpu_procs:
        for proc, stats in low_cpu_procs[:3]:
            recommendations.append(
                f"💡 {proc} has low CPU utilization ({stats['avg_cpu_pct']:.1f}%) "
                f"- consider reducing allocated CPUs or enabling parallel processing"
            )
    
    # Check for high memory usage
    high_mem_procs = [
        (proc, stats) for proc, stats in process_stats.items()
        if stats['max_memory_mb'] > 50000  # >50GB
    ]
    
    if high_mem_procs:
        for proc, stats in high_mem_procs[:3]:
            recommendations.append(
                f"⚠️ {proc} uses high memory (peak: {stats['max_memory_mb']/1024:.1f} GB) "
                f"- consider batch processing or memory optimization"
            )
    
    # Check for failed tasks
    failed_count = analysis['summary'].get('failed', 0)
    if failed_count > 0:
        recommendations.append(
            f"❌ {failed_count} tasks failed - investigate error logs and retry settings"
        )
    
    return recommendations


def main():
    args = parse_args()
    results_dir = Path(args.results_dir)
    output_file = Path(args.output)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Analyzing Nextflow trace files in {results_dir}")
    
    # Find all trace files
    trace_files = list(results_dir.glob('**/nextflow_trace.txt'))
    print(f"Found {len(trace_files)} trace files")
    
    if not trace_files:
        print("No trace files found!")
        return 1
    
    # Parse all trace files
    all_tasks = []
    for trace_file in trace_files:
        print(f"  Parsing: {trace_file}")
        tasks = parse_trace_file(trace_file)
        all_tasks.extend(tasks)
    
    print(f"\nTotal tasks parsed: {len(all_tasks)}")
    
    # Analyze
    analysis = analyze_tasks(all_tasks)
    recommendations = generate_recommendations(analysis)
    
    # Add recommendations to analysis
    analysis['recommendations'] = recommendations
    analysis['analysis_timestamp'] = datetime.now().isoformat()
    analysis['trace_files_analyzed'] = len(trace_files)
    
    # Write report
    with open(output_file, 'w') as f:
        json.dump(analysis, f, indent=2)
    
    print(f"\n✓ Analysis complete. Report saved to: {output_file}")
    
    # Print summary
    print("\n" + "="*80)
    print("PERFORMANCE ANALYSIS SUMMARY")
    print("="*80)
    
    summary = analysis['summary']
    print(f"\nTotal Tasks: {summary['total_tasks']}")
    print(f"Completed: {summary['completed']}")
    print(f"Failed: {summary['failed']}")
    print(f"Total Runtime: {summary['total_runtime_hours']:.2f} hours")
    
    print("\n--- TOP 5 SLOWEST PROCESSES ---")
    for i, task in enumerate(analysis['slowest_tasks'][:5], 1):
        print(f"{i}. {task['process']} ({task['tag']})")
        print(f"   Duration: {task['duration_min']:.1f} min | CPU: {task['cpu_pct']:.1f}% | "
              f"Memory: {task['peak_rss_mb']/1024:.1f} GB")
    
    print("\n--- PROCESS BREAKDOWN ---")
    proc_stats = sorted(analysis['process_stats'].items(), 
                       key=lambda x: x[1]['pct_of_total'], reverse=True)
    for proc, stats in proc_stats[:8]:
        print(f"{proc:20} | {stats['pct_of_total']:5.1f}% | "
              f"Avg: {stats['avg_time_sec']/60:6.1f}min | "
              f"CPU: {stats['avg_cpu_pct']:5.1f}% | "
              f"Mem: {stats['max_memory_mb']/1024:5.1f}GB")
    
    print("\n--- RECOMMENDATIONS ---")
    for rec in recommendations[:10]:
        print(f"  {rec}")
    
    print("\n" + "="*80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
