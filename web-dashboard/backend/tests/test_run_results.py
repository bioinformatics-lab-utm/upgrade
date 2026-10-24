"""
Tests for the shared Nextflow result parsing (services/kraken_abundance.py,
services/run_results.py)
"""
import io

REPORT = "\n".join([
    " 10.00\t10\t10\tU\t0\tunclassified",
    " 90.00\t90\t0\tR\t1\troot",
    " 90.00\t90\t0\tR1\t131567\t  cellular organisms",
    " 90.00\t90\t0\tD\t2\t    Bacteria",
    " 60.00\t60\t0\tG\t1279\t      Staphylococcus",
    " 60.00\t60\t60\tS\t1280\t        Staphylococcus aureus",
    " 30.00\t30\t30\tG\t838\t      Prevotella",
])
# C/U, contig, taxid, length, k-mers
OUTPUT = "\n".join([
    "C\tcontig_1\t1280\t6000\t1280:10",   # species under Staphylococcus
    "C\tcontig_2\t1279\t1000\t1279:3",    # genus itself
    "C\tcontig_3\t838\t2000\t838:5",
    "C\tcontig_4\t2\t500\t2:2",           # Bacteria: above genus
    "U\tcontig_5\t0\t500\t0:9",
])


class TestKrakenAbundance:
    def test_genus_of_each_taxid(self):
        from services.kraken_abundance import genus_by_taxid

        genus = genus_by_taxid(io.StringIO(REPORT))

        assert genus['1280'] == 'Staphylococcus'
        assert genus['1279'] == 'Staphylococcus'
        assert genus['838'] == 'Prevotella'
        assert genus['2'] is None and genus['1'] is None

    def test_weighted_by_contig_length(self):
        """Test abundance is the genus share of all assembled bases"""
        from services.kraken_abundance import sample_genus_abundance

        result = sample_genus_abundance([(REPORT, io.StringIO(OUTPUT))])

        assert result['assembled_bp'] == 10000
        assert result['organisms'] == [
            {'name': 'Staphylococcus', 'abundance': 70.0, 'bp': 7000},
            {'name': 'Prevotella', 'abundance': 20.0, 'bp': 2000},
        ]

    def test_bins_weighted_by_size_not_equally(self):
        """Test a small bin does not count as much as a large one"""
        from services.kraken_abundance import sample_genus_abundance

        small = "C\tc1\t838\t100\t838:1"
        result = sample_genus_abundance([(REPORT, io.StringIO(OUTPUT)), (REPORT, io.StringIO(small))])

        prevotella = next(o for o in result['organisms'] if o['name'] == 'Prevotella')
        assert prevotella['bp'] == 2100
        assert prevotella['abundance'] == round(2100 / 10100 * 100, 2)


HEADER = ("#FILE\tSEQUENCE\tSTART\tEND\tSTRAND\tGENE\tCOVERAGE\tCOVERAGE_MAP\tGAPS\t%COVERAGE\t"
          "%IDENTITY\tDATABASE\tACCESSION\tPRODUCT\tRESISTANCE\n")


def _hit(gene, cov, ident, res='penam'):
    return f"b.fa\tc1\t1\t2\t+\t{gene}\t1-2/2\t==\t0/0\t{cov}\t{ident}\tcard\tACC1\tproduct text\t{res}\n"


class TestParseAbricateTables:
    def test_best_hit_per_gene_and_summary_skipped(self):
        from services.run_results import parse_abricate_tables

        tables = [
            HEADER + _hit('ErmA', 100.0, 99.0, 'lincosamide') + _hit('blaZ', 52.84, 96.89),
            HEADER + _hit('ErmA', 100.0, 100.0, 'lincosamide') + _hit('tetX', 90.0, 85.0, 'tetracycline'),
            "#FILE\tNUM_FOUND\tErmA\nb.fa\t1\t100.00\n",  # abricate --summary matrix
        ]

        genes = {g['gene']: g for g in parse_abricate_tables(tables)}

        assert set(genes) == {'ErmA', 'blaZ', 'tetX'}
        assert genes['ErmA']['identity'] == 100.0
        assert (genes['blaZ']['identity'], genes['blaZ']['coverage']) == (96.9, 52.8)
        assert genes['blaZ']['antibiotic_class'] == 'penam'
        assert genes['tetX']['risk_level'] == 'moderate'

    def test_classify_genus(self):
        from services.run_results import classify

        assert classify('Staphylococcus')[:2] == ('high', 'pathogen')
        assert classify('Pseudomonas')[:2] == ('medium', 'opportunistic')
        assert classify('Xylanibacter')[0] == 'low'


class TestStreamLines:
    def test_lines_split_across_chunks(self):
        """Test lines are rebuilt from a MinIO response read in chunks"""
        from unittest.mock import Mock
        from services.run_results import _stream_lines

        response = Mock()
        response.stream = Mock(return_value=iter([b"C\tc1\t1280\t60", b"00\tx\nU\tc2", b"\t0\t500\tx\n", b"C\tc3\t838\t5\tx"]))

        assert list(_stream_lines(response)) == [
            "C\tc1\t1280\t6000\tx", "U\tc2\t0\t500\tx", "C\tc3\t838\t5\tx",
        ]
