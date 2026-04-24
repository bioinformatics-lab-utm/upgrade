"""
FASTQ File Validation Utility
Validates FASTQ files before pipeline submission
"""
import gzip
import io
import re
from pathlib import Path
from typing import Any, Tuple, List, Dict


class FASTQValidationError(Exception):
    """Raised when FASTQ validation fails"""
    pass


def validate_fastq_filename(filename: str) -> Tuple[bool, str]:
    """
    Validate FASTQ filename format

    Args:
        filename: Name of the file

    Returns:
        (is_valid, error_message)
    """
    valid_extensions = [
        '.fastq', '.fq',
        '.fastq.gz', '.fq.gz',
        '.fastq.gzip', '.fq.gzip'
    ]

    filename_lower = filename.lower()

    # Check if it has a valid extension
    has_valid_ext = any(filename_lower.endswith(ext) for ext in valid_extensions)

    if not has_valid_ext:
        return False, f"Invalid file extension. Expected one of: {', '.join(valid_extensions)}"

    return True, ""


def validate_fastq_content(file_obj, max_reads_check: int = 100) -> Tuple[bool, str]:
    """
    Validate FASTQ file content structure

    FASTQ format has 4 lines per read:
    1. Header line (starts with @)
    2. Sequence line
    3. Plus line (starts with +)
    4. Quality line (same length as sequence)

    Args:
        file_obj: File-like object with FASTQ content
        max_reads_check: Maximum number of reads to validate (for performance)

    Returns:
        (is_valid, error_message)
    """
    try:
        # Reset to beginning
        file_obj.seek(0)

        # Check if gzipped
        magic = file_obj.read(2)
        file_obj.seek(0)

        is_gzipped = (magic == b'\x1f\x8b')

        # Open appropriately
        if is_gzipped:
            import gzip
            f = gzip.open(file_obj, 'rt')
        else:
            f = file_obj
            if hasattr(f, 'read'):
                # If it's a binary file, wrap in text mode
                try:
                    content = f.read(100)
                    if isinstance(content, bytes):
                        file_obj.seek(0)
                        import io
                        f = io.TextIOWrapper(file_obj, encoding='utf-8', errors='ignore')
                    else:
                        file_obj.seek(0)
                except Exception:
                    file_obj.seek(0)

        reads_checked = 0
        line_num = 0

        while reads_checked < max_reads_check:
            # Read 4 lines (1 read)
            header = f.readline()
            if not header:
                # End of file
                break

            line_num += 1

            # Validate header line
            if not header.startswith('@'):
                return False, f"Line {line_num}: FASTQ header must start with '@', got: {header[:50]}"

            # Read sequence line
            sequence = f.readline()
            line_num += 1
            if not sequence:
                return False, f"Line {line_num}: Unexpected end of file (missing sequence)"

            sequence = sequence.strip()
            if not sequence:
                return False, f"Line {line_num}: Empty sequence line"

            # Validate sequence contains only valid nucleotides
            valid_nucleotides = set('ATCGNatcgn')
            if not all(c in valid_nucleotides for c in sequence):
                return False, f"Line {line_num}: Invalid nucleotide characters in sequence"

            # Read plus line
            plus_line = f.readline()
            line_num += 1
            if not plus_line:
                return False, f"Line {line_num}: Unexpected end of file (missing + line)"

            if not plus_line.startswith('+'):
                return False, f"Line {line_num}: Separator line must start with '+', got: {plus_line[:50]}"

            # Read quality line
            quality = f.readline()
            line_num += 1
            if not quality:
                return False, f"Line {line_num}: Unexpected end of file (missing quality scores)"

            quality = quality.strip()
            if len(quality) != len(sequence):
                return False, f"Line {line_num}: Quality length ({len(quality)}) doesn't match sequence length ({len(sequence)})"

            reads_checked += 1

        # Close if we opened gzip wrapper
        if is_gzipped:
            f.close()

        if reads_checked == 0:
            return False, "File appears to be empty or not in FASTQ format"

        return True, f"Valid FASTQ file ({reads_checked} reads checked)"

    except Exception as e:
        return False, f"Error reading FASTQ file: {str(e)}"
    finally:
        # Reset file pointer for later use
        try:
            file_obj.seek(0)
        except Exception:
            pass


def validate_fastq_file_size(file_size: int, min_size: int = 100, max_size: int = 10 * 1024**3) -> Tuple[bool, str]:
    """
    Validate FASTQ file size

    Args:
        file_size: Size in bytes
        min_size: Minimum size in bytes (default 100 bytes)
        max_size: Maximum size in bytes (default 10GB)

    Returns:
        (is_valid, error_message)
    """
    if file_size < min_size:
        return False, f"File too small ({file_size} bytes). Minimum is {min_size} bytes"

    if file_size > max_size:
        max_gb = max_size / (1024**3)
        actual_gb = file_size / (1024**3)
        return False, f"File too large ({actual_gb:.2f} GB). Maximum is {max_gb:.2f} GB"

    return True, ""


def validate_fastq_files(files: List) -> Dict[str, Any]:
    """
    Validate multiple FASTQ files

    Args:
        files: List of file objects from Sanic request.files

    Returns:
        Dict with validation results:
        {
            'valid': bool,
            'errors': List[str],
            'warnings': List[str],
            'files_validated': int,
            'total_size': int
        }
    """
    errors = []
    warnings = []
    total_size = 0

    if not files:
        errors.append("No files provided")
        return {
            'valid': False,
            'errors': errors,
            'warnings': warnings,
            'files_validated': 0,
            'total_size': 0
        }

    for idx, file_obj in enumerate(files, 1):
        # Handle both file objects and strings
        if isinstance(file_obj, str):
            filename = file_obj
            file_body = None  # Will need to read from disk
        else:
            filename = file_obj.name
            file_body = file_obj.body

        # Validate filename
        valid_name, name_error = validate_fastq_filename(filename)
        if not valid_name:
            errors.append(f"File {idx} ({filename}): {name_error}")
            continue

        # Get file body
        if file_body is None:
            # String path provided - read from disk for tests
            try:
                with open(filename, 'rb') as f:
                    file_body = io.BytesIO(f.read())
            except FileNotFoundError:
                errors.append(f"File {idx} ({filename}): File not found")
                continue
            except Exception as e:
                errors.append(f"File {idx} ({filename}): Error reading file: {str(e)}")
                continue

        # Get file size
        if isinstance(file_body, bytes):
            file_size = len(file_body)
            # Convert bytes to BytesIO for uniform handling
            file_body = io.BytesIO(file_body)
        else:
            # It's a file-like object
            file_body.seek(0, 2)  # Seek to end
            file_size = file_body.tell()
            file_body.seek(0)  # Reset

        total_size += file_size

        # Validate file size
        valid_size, size_error = validate_fastq_file_size(file_size)
        if not valid_size:
            errors.append(f"File {idx} ({filename}): {size_error}")
            continue

        # Validate content (first 100 reads for performance)
        valid_content, content_msg = validate_fastq_content(file_body, max_reads_check=100)
        if not valid_content:
            errors.append(f"File {idx} ({filename}): {content_msg}")
        else:
            # Add as info message
            if "reads checked" in content_msg:
                warnings.append(f"File {idx} ({filename}): {content_msg}")

    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings,
        'files_validated': len(files),
        'total_size': total_size
    }
