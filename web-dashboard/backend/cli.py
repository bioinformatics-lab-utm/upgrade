#!/usr/bin/env python3
"""
UPGRADE CLI - Command Line Interface for Pipeline Management

Управление геномными пайплайнами через командную строку
"""

import sys
import os
import json
import argparse
from pathlib import Path
from typing import Optional, Dict, List
import asyncio
from datetime import datetime

# Добавляем путь к модулям
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncpg
import httpx
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.panel import Panel
from rich.tree import Tree
from rich import print as rprint
from rich.json import JSON

from config import Config

console = Console()


class UpgradeCLI:
    """CLI для управления UPGRADE пайплайнами"""
    
    def __init__(self, api_url: str = None, db_config: Dict = None):
        self.api_url = api_url or os.getenv('UPGRADE_API_URL', 'http://localhost:8000')
        
        # Читаем конфигурацию
        config = Config()
        self.db_config = db_config or {
            'host': config.POSTGRES_HOST,
            'port': config.POSTGRES_PORT,
            'database': config.POSTGRES_DB,
            'user': config.POSTGRES_USER,
            'password': config.POSTGRES_PASSWORD
        }
        self.db_pool = None
        
    async def init_db(self):
        """Инициализация подключения к БД"""
        if not self.db_pool:
            self.db_pool = await asyncpg.create_pool(**self.db_config, min_size=1, max_size=3)
    
    async def close_db(self):
        """Закрытие подключения к БД"""
        if self.db_pool:
            await self.db_pool.close()
    
    # ==================== SAMPLES ====================
    
    async def list_samples(self, limit: int = 50, status: str = None):
        """Список всех образцов"""
        await self.init_db()
        
        query = """
            SELECT 
                sample_id,
                sample_code,
                sample_type,
                location,
                collection_date,
                status,
                created_at
            FROM samples
            WHERE 1=1
        """
        params = []
        
        if status:
            query += " AND status = $1"
            params.append(status)
        
        query += " ORDER BY created_at DESC LIMIT $" + str(len(params) + 1)
        params.append(limit)
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        table = Table(title=f"📋 Samples ({len(rows)})", show_header=True, header_style="bold magenta")
        table.add_column("ID", style="cyan", width=8)
        table.add_column("Code", style="green", width=20)
        table.add_column("Type", width=15)
        table.add_column("Location", width=20)
        table.add_column("Date", width=12)
        table.add_column("Status", width=15)
        
        for row in rows:
            status_style = {
                'new': 'yellow',
                'processing': 'blue',
                'completed': 'green',
                'failed': 'red'
            }.get(row['status'], 'white')
            
            table.add_row(
                str(row['sample_id']),
                row['sample_code'],
                row['sample_type'] or '-',
                row['location'] or '-',
                row['collection_date'].strftime('%Y-%m-%d') if row['collection_date'] else '-',
                f"[{status_style}]{row['status']}[/{status_style}]"
            )
        
        console.print(table)
    
    async def get_sample(self, sample_code: str):
        """Получить детали образца"""
        await self.init_db()
        
        query = """
            SELECT * FROM samples WHERE sample_code = $1
        """
        
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, sample_code)
        
        if not row:
            console.print(f"[red]❌ Sample {sample_code} not found[/red]")
            return
        
        panel = Panel(
            f"[cyan]ID:[/cyan] {row['sample_id']}\n"
            f"[cyan]Code:[/cyan] {row['sample_code']}\n"
            f"[cyan]Type:[/cyan] {row['sample_type'] or 'N/A'}\n"
            f"[cyan]Location:[/cyan] {row['location'] or 'N/A'}\n"
            f"[cyan]Collection Date:[/cyan] {row['collection_date']}\n"
            f"[cyan]Status:[/cyan] {row['status']}\n"
            f"[cyan]Created:[/cyan] {row['created_at']}\n"
            f"[cyan]Notes:[/cyan] {row['notes'] or 'N/A'}",
            title=f"📊 Sample: {sample_code}",
            border_style="green"
        )
        console.print(panel)
    
    # ==================== PIPELINE RUNS ====================
    
    async def list_pipelines(
        self,
        limit: int = 50,
        status: str = None,
        sample_code: str = None,
        date_from: str = None,
        date_to: str = None
    ):
        """Список пайплайнов"""
        await self.init_db()
        
        query = """
            SELECT 
                pr.pipeline_id,
                pr.sample_id,
                pr.sample_name,
                pr.status,
                pr.pipeline_version,
                pr.started_at,
                pr.completed_at,
                pr.job_id,
                pr.pipeline_name
            FROM pipeline_runs pr
            WHERE 1=1
        """
        params = []
        param_count = 1
        
        if status:
            query += f" AND pr.status = ${param_count}"
            params.append(status)
            param_count += 1
        
        if sample_code:
            query += f" AND s.sample_code = ${param_count}"
            params.append(sample_code)
            param_count += 1
        
        if date_from:
            query += f" AND pr.started_at >= ${param_count}"
            params.append(datetime.fromisoformat(date_from))
            param_count += 1
        
        if date_to:
            query += f" AND pr.started_at <= ${param_count}"
            params.append(datetime.fromisoformat(date_to))
            param_count += 1
        
        query += f" ORDER BY pr.started_at DESC LIMIT ${param_count}"
        params.append(limit)
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        table = Table(
            title=f"🔬 Pipeline Runs ({len(rows)})",
            show_header=True,
            header_style="bold cyan"
        )
        table.add_column("Pipeline ID", style="yellow", width=12)
        table.add_column("Sample", style="green", width=20)
        table.add_column("Status", width=15)
        table.add_column("Version", width=10)
        table.add_column("Started", width=20)
        table.add_column("Run Name", width=25)
        
        for row in rows:
            status_emoji = {
                'queued': '⏳',
                'running': '▶️',
                'completed': '✅',
                'failed': '❌',
                'cancelled': '🚫'
            }.get(row['status'], '❓')
            
            status_style = {
                'queued': 'yellow',
                'running': 'blue',
                'completed': 'green',
                'failed': 'red',
                'cancelled': 'orange1'
            }.get(row['status'], 'white')
            
            table.add_row(
                str(row['pipeline_id']),
                row['sample_name'] or f"ID:{row['sample_id']}",
                f"{status_emoji} [{status_style}]{row['status']}[/{status_style}]",
                row['pipeline_version'] or '-',
                row['started_at'].strftime('%Y-%m-%d %H:%M') if row['started_at'] else '-',
                row['pipeline_name'] or '-'
            )
        
        console.print(table)
    
    async def get_pipeline(self, pipeline_id: int):
        """Получить детали пайплайна"""
        await self.init_db()
        
        query = """
            SELECT * FROM pipeline_runs WHERE pipeline_id = $1
        """
        
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, pipeline_id)
        
        if not row:
            console.print(f"[red]❌ Pipeline {pipeline_id} not found[/red]")
            return
        
        # Рассчитываем время выполнения
        runtime = None
        if row['started_at'] and row['completed_at']:
            delta = row['completed_at'] - row['started_at']
            runtime = f"{delta.total_seconds() / 60:.1f} min"
        
        status_emoji = {
            'queued': '⏳', 'running': '▶️', 'completed': '✅',
            'failed': '❌', 'cancelled': '🚫'
        }.get(row['status'], '❓')
        
        panel = Panel(
            f"{status_emoji} [bold cyan]Pipeline ID:[/bold cyan] {row['pipeline_id']}\n"
            f"[cyan]Sample:[/cyan] {row['sample_name']} (ID: {row['sample_id']})\n"
            f"[cyan]Status:[/cyan] {row['status']}\n"
            f"[cyan]Pipeline:[/cyan] {row['pipeline_name'] or 'N/A'}\n"
            f"[cyan]Version:[/cyan] {row['pipeline_version'] or 'N/A'}\n"
            f"[cyan]Started:[/cyan] {row['started_at']}\n"
            f"[cyan]Completed:[/cyan] {row['completed_at'] or 'N/A'}\n"
            f"[cyan]Runtime:[/cyan] {runtime or 'N/A'}\n"
            f"[cyan]Job ID:[/cyan] {row['job_id'] or 'N/A'}\n"
            f"[cyan]Results Path:[/cyan] {row['results_path'] or 'N/A'}\n"
            f"[cyan]Bronze Path:[/cyan] {row['bronze_path'] or 'N/A'}\n"
            f"[cyan]Silver Path:[/cyan] {row['silver_path'] or 'N/A'}\n"
            f"[cyan]Gold Path:[/cyan] {row['gold_path'] or 'N/A'}",
            title=f"🔬 Pipeline Run: {pipeline_id}",
            border_style="cyan"
        )
        console.print(panel)
    
    async def get_pipeline_progress(self, pipeline_id: int):
        """Получить прогресс пайплайна"""
        await self.init_db()
        
        query = """
            SELECT 
                stage,
                step,
                status,
                progress_percent,
                details,
                created_at
            FROM pipeline_progress_events
            WHERE pipeline_id = $1
            ORDER BY created_at ASC
        """
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, pipeline_id)
        
        if not rows:
            console.print(f"[yellow]⚠️ No progress events for pipeline {pipeline_id}[/yellow]")
            return
        
        tree = Tree(f"[bold cyan]Pipeline {pipeline_id} Progress[/bold cyan]")
        
        stages = {}
        for row in rows:
            stage = row['stage']
            if stage not in stages:
                stages[stage] = tree.add(f"[yellow]{stage}[/yellow]")
            
            status_emoji = {
                'started': '🔵',
                'in_progress': '⏳',
                'completed': '✅',
                'failed': '❌'
            }.get(row['status'], '❓')
            
            status_style = {
                'started': 'blue',
                'in_progress': 'yellow',
                'completed': 'green',
                'failed': 'red'
            }.get(row['status'], 'white')
            
            step_text = (
                f"{status_emoji} [{status_style}]{row['step']}[/{status_style}] "
                f"({row['progress_percent']}%) - "
                f"{row['created_at'].strftime('%H:%M:%S')}"
            )
            stages[stage].add(step_text)
        
        console.print(tree)
    
    async def start_pipeline(
        self,
        sample_code: str,
        fastq_files: List[str],
        skip_qc: bool = False,
        skip_assembly: bool = False
    ):
        """Запустить новый пайплайн"""
        console.print(f"[cyan]🚀 Starting pipeline for sample: {sample_code}[/cyan]")
        
        # Проверяем файлы
        for fastq_file in fastq_files:
            if not Path(fastq_file).exists():
                console.print(f"[red]❌ File not found: {fastq_file}[/red]")
                return
        
        # Через API
        async with httpx.AsyncClient() as client:
            files = []
            for fastq_file in fastq_files:
                files.append(('files', open(fastq_file, 'rb')))
            
            data = {
                'sample_code': sample_code,
                'skip_qc': str(skip_qc).lower(),
                'skip_assembly': str(skip_assembly).lower()
            }
            
            try:
                response = await client.post(
                    f"{self.api_url}/api/pipeline/upload",
                    files=files,
                    data=data,
                    timeout=300.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    console.print(f"[green]✅ Pipeline started![/green]")
                    console.print(f"[cyan]Pipeline ID: {result.get('pipeline_id')}[/cyan]")
                    console.print(f"[cyan]Job ID: {result.get('job_id')}[/cyan]")
                else:
                    console.print(f"[red]❌ Error: {response.text}[/red]")
            except Exception as e:
                console.print(f"[red]❌ Failed to start pipeline: {e}[/red]")
            finally:
                for _, file in files:
                    file.close()
    
    async def cancel_pipeline(self, pipeline_id: int):
        """Отменить пайплайн"""
        await self.init_db()
        
        console.print(f"[yellow]🚫 Cancelling pipeline {pipeline_id}...[/yellow]")
        
        query = """
            UPDATE pipeline_runs
            SET status = 'cancelled', completed_at = NOW()
            WHERE pipeline_id = $1
            RETURNING pipeline_id
        """
        
        async with self.db_pool.acquire() as conn:
            result = await conn.fetchval(query, pipeline_id)
        
        if result:
            console.print(f"[green]✅ Pipeline {pipeline_id} cancelled[/green]")
        else:
            console.print(f"[red]❌ Pipeline {pipeline_id} not found[/red]")
    
    # ==================== RESULTS ====================
    
    async def get_results(self, pipeline_id: int, output_format: str = 'table'):
        """Получить результаты пайплайна"""
        await self.init_db()
        
        # Получаем путь к результатам
        query = """
            SELECT results_path FROM pipeline_runs WHERE pipeline_id = $1
        """
        
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, pipeline_id)
        
        if not row or not row['results_path']:
            console.print(f"[red]❌ No results found for pipeline {pipeline_id}[/red]")
            return
        
        results_path = Path('/home/nicolaedrabcinski/upgrade/results') / row['results_path']
        summary_file = results_path / '00_summary' / f"{row['results_path']}_summary.json"
        
        if not summary_file.exists():
            console.print(f"[yellow]⚠️ Summary file not found: {summary_file}[/yellow]")
            return
        
        # Читаем summary
        with open(summary_file, 'r') as f:
            summary = json.load(f)
        
        if output_format == 'json':
            console.print(JSON(json.dumps(summary, indent=2)))
            return
        
        # Форматированный вывод
        console.print(Panel(
            f"[bold cyan]Pipeline ID:[/bold cyan] {pipeline_id}\n"
            f"[bold cyan]Sample:[/bold cyan] {summary.get('sample_code', 'N/A')}\n"
            f"[bold cyan]Version:[/bold cyan] {summary.get('pipeline_version', 'N/A')}",
            title="📊 Pipeline Results",
            border_style="green"
        ))
        
        # QC Metrics
        if 'qc_metrics' in summary:
            qc = summary['qc_metrics']
            console.print("\n[bold yellow]📈 QC Metrics[/bold yellow]")
            table = Table(show_header=False)
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            table.add_row("Total Reads", f"{qc.get('total_reads', 0):,}")
            table.add_row("Total Bases", f"{qc.get('total_bases', 0):,}")
            table.add_row("Mean Quality", f"{qc.get('mean_quality', 0):.1f}")
            table.add_row("Mean Read Length", f"{qc.get('mean_read_length', 0):.1f}")
            console.print(table)
        
        # Assembly Metrics
        if 'assembly_metrics' in summary:
            asm = summary['assembly_metrics']
            console.print("\n[bold yellow]🧬 Assembly Metrics[/bold yellow]")
            table = Table(show_header=False)
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            table.add_row("Total Length", f"{asm.get('total_length', 0):,} bp")
            table.add_row("Number of Contigs", str(asm.get('num_contigs', 0)))
            table.add_row("N50", f"{asm.get('n50', 0):,} bp")
            table.add_row("L50", str(asm.get('l50', 0)))
            console.print(table)
        
        # Taxonomy
        if 'taxonomy' in summary and summary['taxonomy']:
            console.print("\n[bold yellow]🦠 Top Taxa[/bold yellow]")
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Species", style="cyan")
            table.add_column("Reads", style="green")
            table.add_column("%", style="yellow")
            
            for taxon in summary['taxonomy'][:10]:
                table.add_row(
                    taxon.get('name', 'Unknown'),
                    f"{taxon.get('reads', 0):,}",
                    f"{taxon.get('percentage', 0):.2f}%"
                )
            console.print(table)
        
        # AMR Genes
        if 'amr' in summary and summary['amr']:
            console.print(f"\n[bold red]💊 AMR Genes Found: {len(summary['amr'])}[/bold red]")
            
            table = Table(show_header=True, header_style="bold red")
            table.add_column("Gene", style="cyan")
            table.add_column("Resistance", style="yellow")
            table.add_column("Identity", style="green")
            
            for amr in summary['amr'][:10]:
                table.add_row(
                    amr.get('gene', 'Unknown'),
                    amr.get('resistance_class', 'Unknown'),
                    f"{amr.get('identity', 0):.1f}%"
                )
            console.print(table)
        
        # Pathogens
        if 'pathogens' in summary and summary['pathogens']:
            console.print(f"\n[bold red]⚠️ Pathogens Detected: {len(summary['pathogens'])}[/bold red]")
            
            for pathogen in summary['pathogens']:
                console.print(
                    f"  • [red]{pathogen.get('name', 'Unknown')}[/red] - "
                    f"Risk: {pathogen.get('risk_level', 'Unknown')}"
                )
    
    async def export_results(self, pipeline_id: int, output_file: str):
        """Экспортировать результаты в файл"""
        await self.init_db()
        
        query = """
            SELECT results_path FROM pipeline_runs WHERE pipeline_id = $1
        """
        
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, pipeline_id)
        
        if not row or not row['results_path']:
            console.print(f"[red]❌ No results found for pipeline {pipeline_id}[/red]")
            return
        
        results_path = Path('/home/nicolaedrabcinski/upgrade/results') / row['results_path']
        summary_file = results_path / '00_summary' / f"{row['results_path']}_summary.json"
        
        if not summary_file.exists():
            console.print(f"[yellow]⚠️ Summary file not found[/yellow]")
            return
        
        # Копируем файл
        import shutil
        shutil.copy(summary_file, output_file)
        console.print(f"[green]✅ Results exported to: {output_file}[/green]")
    
    # ==================== STATISTICS ====================
    
    async def show_stats(self):
        """Показать общую статистику"""
        await self.init_db()
        
        async with self.db_pool.acquire() as conn:
            # Общая статистика
            total_samples = await conn.fetchval("SELECT COUNT(*) FROM samples")
            total_pipelines = await conn.fetchval("SELECT COUNT(*) FROM pipeline_runs")
            
            # По статусам
            pipeline_stats = await conn.fetch("""
                SELECT status, COUNT(*) as count
                FROM pipeline_runs
                GROUP BY status
                ORDER BY count DESC
            """)
            
            # Успешные пайплайны
            completed = await conn.fetchval(
                "SELECT COUNT(*) FROM pipeline_runs WHERE status = 'completed'"
            )
            
            # Средняя длительность
            avg_runtime = await conn.fetchval("""
                SELECT AVG(EXTRACT(EPOCH FROM (completed_at - started_at)) / 60)
                FROM pipeline_runs
                WHERE status = 'completed' AND completed_at IS NOT NULL
            """)
        
        panel = Panel(
            f"[bold cyan]Total Samples:[/bold cyan] {total_samples}\n"
            f"[bold cyan]Total Pipeline Runs:[/bold cyan] {total_pipelines}\n"
            f"[bold green]Completed:[/bold green] {completed}\n"
            f"[bold cyan]Average Runtime:[/bold cyan] {avg_runtime:.1f} min" if avg_runtime else "N/A",
            title="📊 System Statistics",
            border_style="cyan"
        )
        console.print(panel)
        
        # Таблица по статусам
        table = Table(title="Pipeline Status Distribution", show_header=True)
        table.add_column("Status", style="cyan", width=20)
        table.add_column("Count", style="green", width=10)
        table.add_column("Percentage", style="yellow", width=10)
        
        for row in pipeline_stats:
            percentage = (row['count'] / total_pipelines * 100) if total_pipelines > 0 else 0
            status_style = {
                'completed': 'green',
                'running': 'blue',
                'failed': 'red',
                'queued': 'yellow'
            }.get(row['status'], 'white')
            
            table.add_row(
                f"[{status_style}]{row['status']}[/{status_style}]",
                str(row['count']),
                f"{percentage:.1f}%"
            )
        
        console.print(table)


def main():
    parser = argparse.ArgumentParser(
        description='UPGRADE CLI - Genomic Pipeline Management',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all samples
  upgrade-cli samples list

  # Get sample details
  upgrade-cli samples get SAMPLE001

  # List pipeline runs
  upgrade-cli pipelines list --status completed --limit 10

  # Get pipeline details
  upgrade-cli pipelines get 42

  # View pipeline progress
  upgrade-cli pipelines progress 42

  # Start new pipeline
  upgrade-cli pipelines start SAMPLE001 file1.fastq file2.fastq

  # Cancel pipeline
  upgrade-cli pipelines cancel 42

  # Get pipeline results
  upgrade-cli results get 42

  # Export results to JSON
  upgrade-cli results export 42 output.json

  # Show system statistics
  upgrade-cli stats
        """
    )
    
    parser.add_argument('--api-url', help='API URL (default: http://localhost:8000)')
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # SAMPLES
    samples_parser = subparsers.add_parser('samples', help='Sample management')
    samples_sub = samples_parser.add_subparsers(dest='action')
    
    samples_list = samples_sub.add_parser('list', help='List samples')
    samples_list.add_argument('--limit', type=int, default=50, help='Max results')
    samples_list.add_argument('--status', help='Filter by status')
    
    samples_get = samples_sub.add_parser('get', help='Get sample details')
    samples_get.add_argument('sample_code', help='Sample code')
    
    # PIPELINES
    pipelines_parser = subparsers.add_parser('pipelines', help='Pipeline management')
    pipelines_sub = pipelines_parser.add_subparsers(dest='action')
    
    pipelines_list = pipelines_sub.add_parser('list', help='List pipeline runs')
    pipelines_list.add_argument('--limit', type=int, default=50, help='Max results')
    pipelines_list.add_argument('--status', help='Filter by status')
    pipelines_list.add_argument('--sample', help='Filter by sample code')
    pipelines_list.add_argument('--date-from', help='Start date (YYYY-MM-DD)')
    pipelines_list.add_argument('--date-to', help='End date (YYYY-MM-DD)')
    
    pipelines_get = pipelines_sub.add_parser('get', help='Get pipeline details')
    pipelines_get.add_argument('pipeline_id', type=int, help='Pipeline ID')
    
    pipelines_progress = pipelines_sub.add_parser('progress', help='View pipeline progress')
    pipelines_progress.add_argument('pipeline_id', type=int, help='Pipeline ID')
    
    pipelines_start = pipelines_sub.add_parser('start', help='Start new pipeline')
    pipelines_start.add_argument('sample_code', help='Sample code')
    pipelines_start.add_argument('fastq_files', nargs='+', help='FASTQ files')
    pipelines_start.add_argument('--skip-qc', action='store_true', help='Skip QC')
    pipelines_start.add_argument('--skip-assembly', action='store_true', help='Skip assembly')
    
    pipelines_cancel = pipelines_sub.add_parser('cancel', help='Cancel pipeline')
    pipelines_cancel.add_argument('pipeline_id', type=int, help='Pipeline ID')
    
    # RESULTS
    results_parser = subparsers.add_parser('results', help='Results management')
    results_sub = results_parser.add_subparsers(dest='action')
    
    results_get = results_sub.add_parser('get', help='Get pipeline results')
    results_get.add_argument('pipeline_id', type=int, help='Pipeline ID')
    results_get.add_argument('--format', choices=['table', 'json'], default='table', help='Output format')
    
    results_export = results_sub.add_parser('export', help='Export results')
    results_export.add_argument('pipeline_id', type=int, help='Pipeline ID')
    results_export.add_argument('output_file', help='Output file path')
    
    # STATS
    stats_parser = subparsers.add_parser('stats', help='Show system statistics')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Создаем CLI
    cli = UpgradeCLI(api_url=args.api_url)
    
    # Выполняем команду
    try:
        if args.command == 'samples':
            if args.action == 'list':
                asyncio.run(cli.list_samples(limit=args.limit, status=args.status))
            elif args.action == 'get':
                asyncio.run(cli.get_sample(args.sample_code))
        
        elif args.command == 'pipelines':
            if args.action == 'list':
                asyncio.run(cli.list_pipelines(
                    limit=args.limit,
                    status=args.status,
                    sample_code=args.sample,
                    date_from=args.date_from,
                    date_to=args.date_to
                ))
            elif args.action == 'get':
                asyncio.run(cli.get_pipeline(args.pipeline_id))
            elif args.action == 'progress':
                asyncio.run(cli.get_pipeline_progress(args.pipeline_id))
            elif args.action == 'start':
                asyncio.run(cli.start_pipeline(
                    args.sample_code,
                    args.fastq_files,
                    args.skip_qc,
                    args.skip_assembly
                ))
            elif args.action == 'cancel':
                asyncio.run(cli.cancel_pipeline(args.pipeline_id))
        
        elif args.command == 'results':
            if args.action == 'get':
                asyncio.run(cli.get_results(args.pipeline_id, args.format))
            elif args.action == 'export':
                asyncio.run(cli.export_results(args.pipeline_id, args.output_file))
        
        elif args.command == 'stats':
            asyncio.run(cli.show_stats())
    
    finally:
        asyncio.run(cli.close_db())


if __name__ == '__main__':
    main()
