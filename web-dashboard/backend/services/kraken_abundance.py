"""
Genus abundance of a sample from the pipeline's per-bin Kraken2 results.

Kraken2 runs on the contigs of every bin (06_kraken2/<bin>_kraken2_output.txt,
one line per contig: C/U, contig id, taxid, contig length, k-mer hits) and
writes a report per bin (<bin>_kraken2_report.txt, the taxonomy tree with the
names). The bins (MetaBAT2 bins plus lowDepth / tooShort / unbinned) together
hold every contig of the assembly, so weighting each contig by its length gives
the share of the assembled bases that belongs to each genus.

Summing the bins' report percentages instead (the previous method) gives every
bin the same weight, so a one-contig bin counted as much as a 10 Mbp one.
"""
import io
from collections import defaultdict
from typing import Dict, Iterable, Optional


def genus_by_taxid(report_lines: Iterable[str]) -> Dict[str, Optional[str]]:
    """
    taxid -> name of its genus (None above genus level), from a Kraken2 report.

    Report columns: %, clade reads, taxon reads, rank code, taxid, name; the name
    is indented two spaces per tree level and lines are in depth-first order.
    """
    genus_of: Dict[str, Optional[str]] = {}
    path = []  # (depth, rank, name) from the root to the current line
    for line in report_lines:
        parts = line.rstrip('\n').split('\t')
        if len(parts) < 6:
            continue
        rank, taxid, raw_name = parts[3].strip(), parts[4].strip(), parts[5]
        depth = len(raw_name) - len(raw_name.lstrip(' '))
        while path and path[-1][0] >= depth:
            path.pop()
        path.append((depth, rank, raw_name.strip()))
        genus_of[taxid] = next((name for _, r, name in reversed(path) if r == 'G'), None)
    return genus_of


def add_bin(output_lines: Iterable[str], genus_of: Dict[str, Optional[str]],
            genus_bp: Dict[str, int]) -> int:
    """
    Add one bin's contigs to genus_bp (genus -> base pairs).

    Returns:
        the bin's total contig length (classified or not)
    """
    total = 0
    for line in output_lines:
        parts = line.split('\t', 4)
        if len(parts) < 4:
            continue
        length = parts[3].split('|')[0].strip()  # "len" (or "len1|len2" for pairs)
        if not length.isdigit():
            continue
        total += int(length)
        if parts[0] == 'C':
            genus = genus_of.get(parts[2].strip())
            if genus:
                genus_bp[genus] += int(length)
    return total


def sample_genus_abundance(bins, top: int = 15) -> Optional[dict]:
    """
    Args:
        bins: iterable of (report_text, output_text_stream) per bin
        top: how many genera to return

    Returns:
        {'organisms': [{'name', 'abundance' (% of assembled bases), 'bp'}],
         'assembled_bp', 'classified_genus_bp'}, or None without any contigs
    """
    genus_bp: Dict[str, int] = defaultdict(int)
    assembled = 0
    for report_text, output_stream in bins:
        genus_of = genus_by_taxid(io.StringIO(report_text))
        assembled += add_bin(output_stream, genus_of, genus_bp)
    if not assembled:
        return None
    ranked = sorted(genus_bp.items(), key=lambda item: -item[1])
    return {
        'organisms': [
            {'name': name, 'abundance': round(bp / assembled * 100, 2), 'bp': bp}
            for name, bp in ranked[:top]
        ],
        'assembled_bp': assembled,
        'classified_genus_bp': sum(genus_bp.values()),
    }
