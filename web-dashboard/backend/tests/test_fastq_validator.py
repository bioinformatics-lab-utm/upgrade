"""
Unit tests for FASTQ file validation
"""
import unittest
import io
import gzip
from utils.fastq_validator import (
    validate_fastq_filename,
    validate_fastq_content,
    validate_fastq_file_size,
    FASTQValidationError
)


class TestFASTQFilenameValidation(unittest.TestCase):
    """Test FASTQ filename validation"""

    def test_valid_fastq_extensions(self):
        """Test valid FASTQ file extensions"""
        valid_names = [
            'sample.fastq',
            'sample.fq',
            'sample.fastq.gz',
            'sample.fq.gz',
            'sample_R1.fastq.gz',
            'test_data.FASTQ',  # case insensitive
        ]
        for filename in valid_names:
            valid, msg = validate_fastq_filename(filename)
            self.assertTrue(valid, f"Expected {filename} to be valid, but got: {msg}")

    def test_invalid_fastq_extensions(self):
        """Test invalid file extensions"""
        invalid_names = [
            'sample.txt',
            'sample.bam',
            'sample.sam',
            'sample.fasta',
            'sample.fa',
            'sample',  # no extension
        ]
        for filename in invalid_names:
            valid, msg = validate_fastq_filename(filename)
            self.assertFalse(valid, f"Expected {filename} to be invalid")
            self.assertIn('Invalid file extension', msg)


class TestFASTQContentValidation(unittest.TestCase):
    """Test FASTQ content validation"""

    def create_fastq_content(self, num_reads=5):
        """Helper to create valid FASTQ content"""
        fastq_lines = []
        for i in range(num_reads):
            fastq_lines.append(f"@READ_{i+1}")
            fastq_lines.append("ATCGATCGATCGATCG")
            fastq_lines.append("+")
            fastq_lines.append("IIIIIIIIIIIIIIII")
        return '\n'.join(fastq_lines) + '\n'

    def test_valid_fastq_content(self):
        """Test validation of valid FASTQ content"""
        content = self.create_fastq_content(10)
        file_obj = io.BytesIO(content.encode('utf-8'))

        valid, msg = validate_fastq_content(file_obj, max_reads_check=10)
        self.assertTrue(valid, f"Expected valid FASTQ, but got: {msg}")
        self.assertIn("reads checked", msg)

    def test_valid_gzipped_fastq(self):
        """Test validation of gzipped FASTQ content"""
        content = self.create_fastq_content(10)

        # Compress content
        compressed = io.BytesIO()
        with gzip.open(compressed, 'wt') as f:
            f.write(content)
        compressed.seek(0)

        valid, msg = validate_fastq_content(compressed, max_reads_check=10)
        self.assertTrue(valid, f"Expected valid gzipped FASTQ, but got: {msg}")

    def test_invalid_header(self):
        """Test detection of invalid header line"""
        content = ">READ_1\nATCGATCG\n+\nIIIIIIII\n"  # FASTA header instead of FASTQ
        file_obj = io.BytesIO(content.encode('utf-8'))

        valid, msg = validate_fastq_content(file_obj)
        self.assertFalse(valid)
        self.assertIn("must start with '@'", msg)

    def test_missing_plus_line(self):
        """Test detection of missing separator line"""
        content = "@READ_1\nATCGATCG\nIIIIIIII\n"  # Missing +
        file_obj = io.BytesIO(content.encode('utf-8'))

        valid, msg = validate_fastq_content(file_obj)
        self.assertFalse(valid)
        self.assertIn("must start with '+'", msg)

    def test_quality_length_mismatch(self):
        """Test detection of quality/sequence length mismatch"""
        content = "@READ_1\nATCGATCGATCG\n+\nIIII\n"  # Quality shorter than sequence
        file_obj = io.BytesIO(content.encode('utf-8'))

        valid, msg = validate_fastq_content(file_obj)
        self.assertFalse(valid)
        self.assertIn("doesn't match sequence length", msg)

    def test_invalid_nucleotides(self):
        """Test detection of invalid nucleotide characters"""
        content = "@READ_1\nATCGXYZ\n+\nIIIIIII\n"  # Invalid X, Y, Z
        file_obj = io.BytesIO(content.encode('utf-8'))

        valid, msg = validate_fastq_content(file_obj)
        self.assertFalse(valid)
        self.assertIn("Invalid nucleotide characters", msg)

    def test_empty_file(self):
        """Test detection of empty file"""
        content = ""
        file_obj = io.BytesIO(content.encode('utf-8'))

        valid, msg = validate_fastq_content(file_obj)
        self.assertFalse(valid)
        self.assertIn("empty", msg.lower())


class TestFASTQFileSizeValidation(unittest.TestCase):
    """Test FASTQ file size validation"""

    def test_valid_file_size(self):
        """Test valid file sizes"""
        valid_sizes = [
            1000,  # 1 KB
            1024 * 1024,  # 1 MB
            100 * 1024 * 1024,  # 100 MB
            1024 * 1024 * 1024,  # 1 GB
        ]
        for size in valid_sizes:
            valid, msg = validate_fastq_file_size(size)
            self.assertTrue(valid, f"Expected {size} bytes to be valid, but got: {msg}")

    def test_file_too_small(self):
        """Test detection of file too small"""
        valid, msg = validate_fastq_file_size(50, min_size=100)
        self.assertFalse(valid)
        self.assertIn("too small", msg)

    def test_file_too_large(self):
        """Test detection of file too large"""
        max_size = 10 * 1024**3  # 10 GB
        file_size = 15 * 1024**3  # 15 GB

        valid, msg = validate_fastq_file_size(file_size, max_size=max_size)
        self.assertFalse(valid)
        self.assertIn("too large", msg)


if __name__ == '__main__':
    unittest.main()
