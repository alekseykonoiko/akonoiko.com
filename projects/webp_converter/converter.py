"""
WebP Image Converter

Converts images to optimized WebP format for web and mobile production use.
Supports: JPG, JPEG, PNG, GIF, BMP, TIFF, WebP (re-optimization)
"""

from pathlib import Path
from typing import Callable, Optional, Dict, List
import zipfile
from PIL import Image


# Supported image extensions
SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.webp'}


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


def convert_to_webp(input_path: Path, output_dir: Path, quality: int = 80, max_dimension: Optional[int] = None) -> Dict:
    """
    Convert a single image to WebP format with optional resizing.

    Args:
        input_path: Path to the input image
        output_dir: Directory to save the WebP file
        quality: WebP quality (1-100), default 80
        max_dimension: Optional max width/height (maintains aspect ratio, never upscales)

    Returns:
        Dict with conversion stats
    """
    try:
        img = Image.open(input_path)
        original_dimensions = img.size  # (width, height)

        # Handle different image modes
        if img.mode in ('RGBA', 'LA'):
            # Keep alpha channel for transparency
            pass
        elif img.mode == 'P':
            # Convert palette mode, check for transparency
            if 'transparency' in img.info:
                img = img.convert('RGBA')
            else:
                img = img.convert('RGB')
        else:
            img = img.convert('RGB')

        # Resize if max_dimension specified and image is larger (never upscale)
        resized = False
        if max_dimension and max(img.size) > max_dimension:
            img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            resized = True

        # Generate output path
        output_path = output_dir / f"{input_path.stem}.webp"

        # Save as WebP with high quality compression
        # method=6 is slowest but best compression
        img.save(output_path, 'WEBP', quality=quality, method=6)

        original_size = input_path.stat().st_size
        webp_size = output_path.stat().st_size
        savings_percent = ((original_size - webp_size) / original_size * 100) if original_size > 0 else 0

        return {
            'success': True,
            'original_name': input_path.name,
            'webp_name': output_path.name,
            'webp_path': output_path,
            'original_size': original_size,
            'webp_size': webp_size,
            'original_size_formatted': format_size(original_size),
            'webp_size_formatted': format_size(webp_size),
            'savings_percent': round(savings_percent, 1),
            'original_dimensions': original_dimensions,
            'final_dimensions': img.size,
            'resized': resized,
        }

    except Exception as e:
        return {
            'success': False,
            'original_name': input_path.name,
            'error': str(e),
        }


def find_images(directory: Path) -> List[Path]:
    """Find all supported image files in a directory (recursive)."""
    images = []
    for ext in SUPPORTED_EXTENSIONS:
        images.extend(directory.rglob(f'*{ext}'))
        images.extend(directory.rglob(f'*{ext.upper()}'))
    return sorted(set(images))


def extract_zip(zip_path: Path, extract_dir: Path) -> None:
    """Extract a ZIP file to a directory."""
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)


def process_images(
    input_dir: Path,
    output_dir: Path,
    quality: int = 80,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    max_dimension: Optional[int] = None
) -> Dict:
    """
    Process all images in a directory, converting them to WebP.

    Args:
        input_dir: Directory containing input images
        output_dir: Directory to save WebP files
        quality: WebP quality (1-100)
        progress_callback: Optional callback(current, total, filename)
        max_dimension: Optional max width/height (maintains aspect ratio, never upscales)

    Returns:
        Dict with processing results
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find all images
    images = find_images(input_dir)
    total = len(images)

    if total == 0:
        return {
            'success': False,
            'error': 'No supported images found',
            'files': [],
            'total_original_size': 0,
            'total_webp_size': 0,
        }

    results = []
    total_original = 0
    total_webp = 0

    for i, image_path in enumerate(images, 1):
        if progress_callback:
            progress_callback(i, total, image_path.name)

        result = convert_to_webp(image_path, output_dir, quality, max_dimension)
        results.append(result)

        if result['success']:
            total_original += result['original_size']
            total_webp += result['webp_size']

    total_savings = ((total_original - total_webp) / total_original * 100) if total_original > 0 else 0

    return {
        'success': True,
        'files': results,
        'total_files': total,
        'successful_files': sum(1 for r in results if r['success']),
        'failed_files': sum(1 for r in results if not r['success']),
        'total_original_size': total_original,
        'total_webp_size': total_webp,
        'total_original_formatted': format_size(total_original),
        'total_webp_formatted': format_size(total_webp),
        'total_savings_percent': round(total_savings, 1),
    }


def create_result_zip(output_dir: Path, zip_path: Path) -> Path:
    """Create a ZIP file from the output directory."""
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for webp_file in output_dir.glob('*.webp'):
            zipf.write(webp_file, webp_file.name)
    return zip_path
