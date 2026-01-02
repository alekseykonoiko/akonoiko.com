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


def generate_thumbnail(input_path: Path, output_dir: Path, max_size: int = 300) -> Path:
    """
    Generate a thumbnail for preview, preserving aspect ratio.

    Args:
        input_path: Path to the input image
        output_dir: Directory to save the thumbnail
        max_size: Maximum width or height in pixels

    Returns:
        Path to the generated thumbnail
    """
    img = Image.open(input_path)
    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    # Convert to RGB if necessary (for JPEG output)
    if img.mode in ('RGBA', 'LA', 'P'):
        # Create white background for transparent images
        background = Image.new('RGB', img.size, (25, 25, 25))  # Dark background matching theme
        if img.mode == 'P':
            img = img.convert('RGBA')
        if img.mode in ('RGBA', 'LA'):
            background.paste(img, mask=img.split()[-1])
            img = background
        else:
            img = img.convert('RGB')
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    thumb_path = output_dir / f"{input_path.stem}_thumb.jpg"
    img.save(thumb_path, 'JPEG', quality=85)
    return thumb_path


def apply_crop(img: Image.Image, crop_data: Dict) -> Image.Image:
    """
    Apply crop coordinates to an image.

    Args:
        img: PIL Image object
        crop_data: Dict with x, y, width, height (from Cropper.js)

    Returns:
        Cropped PIL Image
    """
    if not crop_data:
        return img

    x = int(crop_data.get('x', 0))
    y = int(crop_data.get('y', 0))
    width = int(crop_data.get('width', img.width))
    height = int(crop_data.get('height', img.height))

    # Ensure coordinates are within bounds
    x = max(0, min(x, img.width - 1))
    y = max(0, min(y, img.height - 1))
    width = min(width, img.width - x)
    height = min(height, img.height - y)

    return img.crop((x, y, x + width, y + height))


def crop_and_save_original(input_path: Path, output_path: Path, crop_data: Optional[Dict] = None) -> Dict:
    """
    Crop an image and save in its original format (no WebP conversion).

    Args:
        input_path: Path to the input image
        output_path: Path to save the cropped image
        crop_data: Optional crop coordinates

    Returns:
        Dict with processing stats
    """
    try:
        img = Image.open(input_path)
        original_dimensions = img.size
        original_format = img.format or 'JPEG'

        # Apply crop if specified
        if crop_data:
            img = apply_crop(img, crop_data)

        # Determine save format and options
        save_kwargs = {}
        if original_format.upper() in ('JPEG', 'JPG'):
            save_kwargs = {'quality': 95}
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
        elif original_format.upper() == 'PNG':
            save_kwargs = {'optimize': True}
        elif original_format.upper() == 'WEBP':
            save_kwargs = {'quality': 95, 'method': 6}

        img.save(output_path, format=original_format, **save_kwargs)

        original_size = input_path.stat().st_size
        output_size = output_path.stat().st_size

        return {
            'success': True,
            'original_name': input_path.name,
            'output_name': output_path.name,
            'output_path': output_path,
            'original_size': original_size,
            'output_size': output_size,
            'original_size_formatted': format_size(original_size),
            'output_size_formatted': format_size(output_size),
            'original_dimensions': original_dimensions,
            'final_dimensions': img.size,
            'cropped': crop_data is not None,
            'format': original_format,
        }

    except Exception as e:
        return {
            'success': False,
            'original_name': input_path.name,
            'error': str(e),
        }


def convert_to_webp(input_path: Path, output_dir: Path, quality: int = 80, max_dimension: Optional[int] = None, crop_data: Optional[Dict] = None) -> Dict:
    """
    Convert a single image to WebP format with optional cropping and resizing.

    Args:
        input_path: Path to the input image
        output_dir: Directory to save the WebP file
        quality: WebP quality (1-100), default 80
        max_dimension: Optional max width/height (maintains aspect ratio, never upscales)
        crop_data: Optional crop coordinates from Cropper.js

    Returns:
        Dict with conversion stats
    """
    try:
        img = Image.open(input_path)
        original_dimensions = img.size  # (width, height)

        # Apply crop first if specified
        cropped = False
        if crop_data:
            img = apply_crop(img, crop_data)
            cropped = True

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
            'cropped': cropped,
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
    max_dimension: Optional[int] = None,
    crops: Optional[Dict[str, Dict]] = None
) -> Dict:
    """
    Process all images in a directory, converting them to WebP.

    Args:
        input_dir: Directory containing input images
        output_dir: Directory to save WebP files
        quality: WebP quality (1-100)
        progress_callback: Optional callback(current, total, filename)
        max_dimension: Optional max width/height (maintains aspect ratio, never upscales)
        crops: Optional dict mapping filename to crop coordinates

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

        # Get crop data for this specific file
        crop_data = crops.get(image_path.name) if crops else None
        result = convert_to_webp(image_path, output_dir, quality, max_dimension, crop_data)
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


def process_images_crop_only(
    input_dir: Path,
    output_dir: Path,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    crops: Optional[Dict[str, Dict]] = None
) -> Dict:
    """
    Process images with crop only (no format conversion).

    Args:
        input_dir: Directory containing input images
        output_dir: Directory to save cropped images
        progress_callback: Optional callback(current, total, filename)
        crops: Optional dict mapping filename to crop coordinates

    Returns:
        Dict with processing results
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    images = find_images(input_dir)
    total = len(images)

    if total == 0:
        return {
            'success': False,
            'error': 'No supported images found',
            'files': [],
            'total_original_size': 0,
            'total_output_size': 0,
        }

    results = []
    total_original = 0
    total_output = 0

    for i, image_path in enumerate(images, 1):
        if progress_callback:
            progress_callback(i, total, image_path.name)

        crop_data = crops.get(image_path.name) if crops else None
        output_path = output_dir / image_path.name

        result = crop_and_save_original(image_path, output_path, crop_data)
        results.append(result)

        if result['success']:
            total_original += result['original_size']
            total_output += result['output_size']

    return {
        'success': True,
        'files': results,
        'total_files': total,
        'successful_files': sum(1 for r in results if r['success']),
        'failed_files': sum(1 for r in results if not r['success']),
        'total_original_size': total_original,
        'total_output_size': total_output,
        'total_original_formatted': format_size(total_original),
        'total_output_formatted': format_size(total_output),
    }


def create_result_zip(output_dir: Path, zip_path: Path, pattern: str = '*') -> Path:
    """Create a ZIP file from the output directory."""
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in output_dir.glob(pattern):
            if file.is_file() and file != zip_path:
                zipf.write(file, file.name)
    return zip_path
