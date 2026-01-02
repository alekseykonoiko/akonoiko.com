"""
WebP Converter Routes

FastHTML routes for the WebP image converter project.
"""

import asyncio
import shutil
import uuid
import json
from pathlib import Path
from typing import Dict, List
from urllib.parse import quote, unquote

from fasthtml.common import *
from starlette.responses import FileResponse
from starlette.datastructures import UploadFile

from .converter import (
    process_images,
    process_images_crop_only,
    extract_zip,
    find_images,
    create_result_zip,
    generate_thumbnail,
    SUPPORTED_EXTENSIONS,
)


# Shared state for tracking conversion progress
conversion_state: Dict[str, Dict] = {}

# Temp directories
TEMP_DIR = Path(__file__).parent.parent.parent / 'temp'
UPLOADS_DIR = TEMP_DIR / 'webp_uploads'
RESULTS_DIR = TEMP_DIR / 'webp_results'
THUMBNAILS_DIR = TEMP_DIR / 'webp_thumbnails'


def setup_routes(rt):
    """Setup WebP converter routes. Returns dict of route references."""

    @rt('/webp_converter')
    def webp_converter(auth):
        """Main WebP converter page."""

        # Supported formats display
        formats = ', '.join(sorted(ext.upper().lstrip('.') for ext in SUPPORTED_EXTENSIONS))

        # Size presets for dropdown
        size_presets = [
            ('', 'Original size'),
            ('2048', 'Max 2048px'),
            ('1920', 'Max 1920px'),
            ('1280', 'Max 1280px'),
            ('1024', 'Max 1024px'),
            ('512', 'Max 512px'),
            ('256', 'Max 256px'),
            ('128', 'Max 128px'),
            ('64', 'Max 64px'),
            ('custom', 'Custom...'),
        ]

        # Upload section
        upload_section = Div(
            H3("Upload Images", cls="text-xl font-semibold text-primary mb-4"),
            P(f"Supported formats: {formats}", cls="text-secondary text-sm mb-6"),

            Form(
                hx_post=upload_webp_images,
                hx_target="#upload-result",
                hx_encoding="multipart/form-data",
                cls="space-y-4",
                id="upload-form"
            )(
                # Drag & drop zone with file inputs
                Div(
                    Div(
                        Span("Drop images here or click to browse", cls="text-primary block mb-2"),
                        Span("Files, ZIP archives, or folders", cls="text-secondary text-sm"),
                        cls="text-center py-8"
                    ),
                    # Hidden file input (handles both files and folders)
                    Input(
                        type="file",
                        name="files",
                        multiple=True,
                        accept=",".join(SUPPORTED_EXTENSIONS) + ",.zip",
                        cls="absolute inset-0 opacity-0 cursor-pointer",
                        id="file-input"
                    ),
                    # Folder input - uses same name="files" so both work with one handler
                    Input(
                        type="file",
                        name="files",
                        multiple=True,
                        cls="hidden",
                        id="folder-input",
                        **{"webkitdirectory": True}
                    ),
                    cls="relative rounded-xl cursor-pointer transition-all duration-200 hover:border-[#555]",
                    style="background-color: #232323; border: 2px dashed #3a3a3a;",
                    id="drop-zone"
                ),

                # Folder upload button
                Div(
                    Button(
                        "Or select a folder",
                        type="button",
                        onclick="document.getElementById('folder-input').click()",
                        cls="text-sm text-secondary hover:text-primary transition-colors underline"
                    ),
                    cls="text-center"
                ),

                # Selected files display
                Div(id="selected-files", cls="text-sm text-secondary"),

                # Resize options
                Div(
                    Label("Resize", cls="text-sm text-secondary mb-2 block"),
                    Div(
                        Select(
                            *[Option(label, value=val, selected=(val == '')) for val, label in size_presets],
                            name="max_size",
                            id="size-select",
                            cls="px-4 py-2 rounded-lg text-primary w-full",
                            style="background-color: #2a2a2a; border: 1px solid #3a3a3a;"
                        ),
                        # Custom size input (hidden by default)
                        Div(
                            Input(
                                type="number",
                                name="custom_size",
                                id="custom-size-input",
                                placeholder="Enter max dimension (px)",
                                min="16",
                                max="10000",
                                cls="px-4 py-2 rounded-lg text-primary w-full mt-2",
                                style="background-color: #2a2a2a; border: 1px solid #3a3a3a;"
                            ),
                            id="custom-size-container",
                            cls="hidden"
                        ),
                        cls="flex flex-col"
                    ),
                    P("Images smaller than selected size won't be upscaled", cls="text-muted text-xs mt-2"),
                    cls="mt-4"
                ),

                # Upload progress bar (hidden initially)
                Div(
                    Div(
                        Div(cls="h-2 rounded-full transition-all duration-200", style="background-color: #e3e3e3; width: 0%;", id="upload-bar"),
                        cls="w-full rounded-full overflow-hidden",
                        style="background-color: #3a3a3a;"
                    ),
                    P("Uploading...", cls="text-secondary text-sm mt-2", id="upload-text"),
                    cls="hidden",
                    id="upload-progress-container"
                ),

                # Submit button (hidden - auto-submit on file selection)
                Button(
                    'Upload Images',
                    type='submit',
                    cls="hidden",
                    id="submit-btn"
                ),

                # Result placeholder
                Div(id="upload-result"),
            ),

            # JavaScript for file handling
            Script("""
                const dropZone = document.getElementById('drop-zone');
                const fileInput = document.getElementById('file-input');
                const folderInput = document.getElementById('folder-input');
                const selectedFiles = document.getElementById('selected-files');
                const form = document.getElementById('upload-form');
                const sizeSelect = document.getElementById('size-select');
                const customSizeContainer = document.getElementById('custom-size-container');
                const customSizeInput = document.getElementById('custom-size-input');

                // Handle size dropdown change
                sizeSelect.addEventListener('change', (e) => {
                    if (e.target.value === 'custom') {
                        customSizeContainer.classList.remove('hidden');
                        customSizeInput.focus();
                    } else {
                        customSizeContainer.classList.add('hidden');
                        customSizeInput.value = '';
                    }
                });

                // Auto-submit after file selection
                function autoSubmit() {
                    // Small delay to let browser process files
                    setTimeout(() => {
                        htmx.trigger(form, 'submit');
                    }, 100);
                }

                // File input change - auto upload
                fileInput.addEventListener('change', (e) => {
                    if (e.target.files.length > 0) {
                        selectedFiles.textContent = `Uploading ${e.target.files.length} file(s)...`;
                        autoSubmit();
                    }
                });

                // Folder input change - transfer files to main input and auto upload
                folderInput.addEventListener('change', (e) => {
                    if (e.target.files.length > 0) {
                        // Transfer folder files to main file input
                        const dt = new DataTransfer();
                        for (const file of e.target.files) {
                            dt.items.add(file);
                        }
                        fileInput.files = dt.files;
                        selectedFiles.textContent = `Uploading ${e.target.files.length} file(s) from folder...`;
                        autoSubmit();
                    }
                });

                // Drag and drop - auto upload
                dropZone.addEventListener('dragover', (e) => {
                    e.preventDefault();
                    dropZone.style.borderColor = '#e3e3e3';
                });

                dropZone.addEventListener('dragleave', (e) => {
                    e.preventDefault();
                    dropZone.style.borderColor = '#3a3a3a';
                });

                dropZone.addEventListener('drop', (e) => {
                    e.preventDefault();
                    dropZone.style.borderColor = '#3a3a3a';
                    const dt = new DataTransfer();
                    for (const file of e.dataTransfer.files) {
                        dt.items.add(file);
                    }
                    fileInput.files = dt.files;
                    selectedFiles.textContent = `Uploading ${dt.files.length} file(s)...`;
                    autoSubmit();
                });

                // Upload progress
                document.body.addEventListener('htmx:xhr:progress', function(e) {
                    if (e.detail.elt.id === 'upload-form') {
                        const container = document.getElementById('upload-progress-container');
                        const bar = document.getElementById('upload-bar');
                        const text = document.getElementById('upload-text');

                        container.classList.remove('hidden');
                        const percent = (e.detail.loaded / e.detail.total) * 100;
                        bar.style.width = percent + '%';

                        const loadedMB = (e.detail.loaded / (1024 * 1024)).toFixed(2);
                        const totalMB = (e.detail.total / (1024 * 1024)).toFixed(2);
                        text.textContent = `Uploading: ${loadedMB} MB / ${totalMB} MB`;
                    }
                });
            """),

            cls="mb-8 p-6 rounded-xl",
            style="background-color: #232323; border: 1px solid #3a3a3a;",
            id="upload-section"
        )

        # Progress section (hidden initially)
        progress_section = Div(
            H3("Converting", cls="text-xl font-semibold text-primary mb-4"),
            Div(
                Div(
                    Div(cls="h-3 rounded-full transition-all duration-200", style="background-color: #e3e3e3; width: 0%;", id="convert-bar"),
                    cls="w-full rounded-full overflow-hidden",
                    style="background-color: #3a3a3a;"
                ),
                cls="mb-3"
            ),
            P("Preparing...", cls="text-secondary", id="convert-message"),
            cls="mb-8 p-6 rounded-xl hidden",
            style="background-color: #232323; border: 1px solid #3a3a3a;",
            id="progress-section"
        )

        # Results section (hidden initially)
        results_section = Div(
            H3("Conversion Complete", cls="text-xl font-semibold text-primary mb-4"),
            Div(id="results-summary", cls="mb-4"),
            Div(id="results-table", cls="mb-6"),
            Div(id="download-button"),
            cls="mb-8 p-6 rounded-xl hidden",
            style="background-color: #232323; border: 1px solid #3a3a3a;",
            id="results-section"
        )

        # Gallery section (hidden initially, shown after upload)
        gallery_section = Div(
            id="gallery-section",
            cls="mb-8 hidden"
        )

        content = Div(
            H1("Image Crop & Convert", cls="text-3xl font-semibold mb-2 text-primary"),
            P("Crop images and optionally convert to WebP format", cls="text-secondary mb-8"),
            upload_section,
            gallery_section,
            progress_section,
            results_section,
            A(
                "Back to Dashboard",
                href="/",
                cls="inline-block text-secondary hover:text-primary transition-colors text-sm"
            ),
            cls="max-w-4xl mx-auto px-6 py-12"
        )

        return (
            Title("WebP Converter"),
            Div(content, cls="min-h-screen")
        )


    @rt('/upload_webp_images')
    async def upload_webp_images(files: List[UploadFile] = None, max_size: str = '', custom_size: str = '', sess=None):
        """Handle image upload and show gallery for cropping."""

        # Determine max dimension from dropdown or custom input
        max_dimension = None
        if max_size == 'custom' and custom_size:
            try:
                max_dimension = int(custom_size)
                if max_dimension < 16 or max_dimension > 10000:
                    max_dimension = None
            except ValueError:
                pass
        elif max_size and max_size != 'custom':
            try:
                max_dimension = int(max_size)
            except ValueError:
                pass

        # Handle files (can be single file, list, or tuple)
        all_files = []
        if files:
            if isinstance(files, (list, tuple)):
                all_files.extend(files)
            else:
                all_files.append(files)

        # Filter out empty file objects
        all_files = [f for f in all_files if f and hasattr(f, 'filename') and f.filename]

        if not all_files:
            return Div(
                P("No files selected", cls="text-red-400"),
                cls="mt-4"
            )

        # Create session directories
        session_id = str(uuid.uuid4())
        upload_dir = UPLOADS_DIR / session_id
        result_dir = RESULTS_DIR / session_id
        thumbnail_dir = THUMBNAILS_DIR / session_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        result_dir.mkdir(parents=True, exist_ok=True)
        thumbnail_dir.mkdir(parents=True, exist_ok=True)

        # Save uploaded files
        seen_filenames = set()
        for uploaded_file in all_files:
            original_filename = Path(uploaded_file.filename).name  # Security: only use filename
            filename = original_filename

            # Handle duplicate filenames (from folder uploads with same-named files in subfolders)
            counter = 1
            while filename in seen_filenames:
                stem = Path(original_filename).stem
                suffix = Path(original_filename).suffix
                filename = f"{stem}_{counter}{suffix}"
                counter += 1
            seen_filenames.add(filename)

            file_path = upload_dir / filename
            content = await uploaded_file.read()

            # Handle ZIP files
            if filename.lower().endswith('.zip'):
                zip_path = upload_dir / filename
                with open(zip_path, 'wb') as f:
                    f.write(content)
                # Extract ZIP
                extract_subdir = upload_dir / 'extracted'
                extract_subdir.mkdir(exist_ok=True)
                extract_zip(zip_path, extract_subdir)
            else:
                with open(file_path, 'wb') as f:
                    f.write(content)

        # Find all images and generate thumbnails
        image_paths = find_images(upload_dir)
        images = {}
        for img_path in image_paths:
            try:
                thumb_path = generate_thumbnail(img_path, thumbnail_dir)
                images[img_path.name] = {
                    'original_path': str(img_path),
                    'thumbnail_path': str(thumb_path),
                    'crop': None
                }
            except Exception as e:
                # Skip images that fail thumbnail generation
                pass

        if not images:
            return Div(
                P("No valid images found", cls="text-red-400"),
                cls="mt-4"
            )

        # Store session data
        sess['webp_session_id'] = session_id
        conversion_state[session_id] = {
            'status': 'gallery',
            'images': images,
            'upload_dir': str(upload_dir),
            'result_dir': str(result_dir),
            'thumbnail_dir': str(thumbnail_dir),
            'max_dimension': max_dimension,
            'result_file': None,
            'results': None,
        }

        # Build thumbnail gallery
        gallery_html = build_gallery(session_id, images, max_dimension)

        # Return gallery view
        return Div(
            gallery_html,
            Script(f"""
                // Hide upload section, show gallery
                document.getElementById('upload-section').classList.add('hidden');
                document.getElementById('gallery-section').classList.remove('hidden');
                document.getElementById('gallery-section').innerHTML = document.getElementById('temp-gallery').innerHTML;
                document.getElementById('temp-gallery').remove();
                // Tell htmx to process the new content for hx-* attributes
                htmx.process(document.getElementById('gallery-section'));
            """),
            id="temp-gallery",
            cls="hidden"
        )


    def build_gallery(session_id: str, images: dict, max_dimension: int = None):
        """Build the thumbnail gallery UI with crop modal."""

        # Size presets for dropdown (reused from main page)
        size_presets = [
            ('', 'Original size'),
            ('2048', 'Max 2048px'),
            ('1920', 'Max 1920px'),
            ('1280', 'Max 1280px'),
            ('1024', 'Max 1024px'),
            ('512', 'Max 512px'),
            ('256', 'Max 256px'),
            ('128', 'Max 128px'),
            ('64', 'Max 64px'),
        ]

        # Build thumbnail grid
        thumbnails = []
        for filename, img_data in images.items():
            has_crop = img_data.get('crop') is not None
            safe_id = filename.replace('.', '-').replace(' ', '-').replace("'", '-').replace('"', '-')
            # Escape filename for use in URL and JavaScript
            url_safe_filename = quote(filename, safe='')
            js_safe_filename = json.dumps(filename)  # Properly escapes quotes and special chars

            thumb = Div(
                # Thumbnail image (natural aspect ratio)
                Img(
                    src=f"/webp_thumbnail?sid={session_id}&fn={url_safe_filename}",
                    cls="w-full h-auto rounded-lg cursor-pointer hover:opacity-80 transition-opacity",
                    style="max-height: 200px; object-fit: contain;",
                    alt=filename,
                    onclick=f"openCropEditor({js_safe_filename})"
                ),
                # Crop indicator badge
                Div(
                    "Cropped",
                    cls=f"absolute top-2 right-2 text-xs px-2 py-1 rounded bg-green-600 text-white {'hidden' if not has_crop else ''}",
                    id=f"crop-badge-{safe_id}"
                ),
                # Filename
                P(
                    filename[:25] + ('...' if len(filename) > 25 else ''),
                    cls="text-xs text-secondary mt-2 truncate",
                    title=filename
                ),
                cls="relative p-2 rounded-xl",
                style="background-color: #2a2a2a; border: 1px solid #3a3a3a;",
                id=f"thumb-{safe_id}"
            )
            thumbnails.append(thumb)

        # Thumbnail grid
        thumbnail_grid = Div(
            *thumbnails,
            cls="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4 mb-6"
        )

        # Output mode selection
        output_section = Div(
            H3("Output Options", cls="text-lg font-semibold text-primary mb-4"),

            # Output mode radio buttons
            Div(
                Div(
                    Input(type="radio", name="output_mode", value="crop_only", id="mode-crop"),
                    Label("Crop Only", fr="mode-crop", cls="ml-2 text-primary cursor-pointer"),
                    P("Download in original format (JPEG, PNG, etc.)", cls="text-secondary text-xs ml-6"),
                    cls="mb-3"
                ),
                Div(
                    Input(type="radio", name="output_mode", value="webp", id="mode-webp", checked=True),
                    Label("Convert to WebP", fr="mode-webp", cls="ml-2 text-primary cursor-pointer"),
                    P("Convert all images to optimized WebP format", cls="text-secondary text-xs ml-6"),
                    cls="mb-3"
                ),
                cls="mb-4"
            ),

            # Resize option (only for WebP mode)
            Div(
                Label("Resize (WebP only)", cls="text-sm text-secondary mb-2 block"),
                Select(
                    *[Option(label, value=val, selected=(str(max_dimension) == val if max_dimension else val == '')) for val, label in size_presets],
                    name="max_size_final",
                    id="size-select-final",
                    cls="px-4 py-2 rounded-lg text-primary w-full",
                    style="background-color: #2a2a2a; border: 1px solid #3a3a3a;"
                ),
                id="resize-option",
                cls="mb-4"
            ),

            cls="p-4 rounded-xl mb-6",
            style="background-color: #232323; border: 1px solid #3a3a3a;"
        )

        # Process button
        process_button = Button(
            "Process Images",
            hx_post=f"/webp_process_all?sid={session_id}",
            hx_target="#gallery-section",
            hx_include="[name='output_mode'], [name='max_size_final']",
            cls="w-full px-6 py-4 rounded-xl font-medium transition-all duration-200 hover:bg-[#3a3a3a] hover:scale-[1.02] active:scale-[0.98]",
            style="background-color: #2a2a2a; border: 1px solid #3a3a3a; color: #e3e3e3;"
        )

        # Crop modal (hidden by default)
        crop_modal = Div(
            # Backdrop
            Div(
                onclick="closeCropEditor()",
                cls="fixed inset-0 bg-black/80 z-40"
            ),
            # Modal content
            Div(
                # Header
                Div(
                    H3("Crop Image", cls="text-xl font-semibold text-primary"),
                    Button("✕", onclick="closeCropEditor()", cls="text-secondary hover:text-primary text-xl"),
                    cls="flex justify-between items-center mb-4"
                ),

                # Aspect ratio buttons
                Div(
                    Button("Free", onclick="setAspectRatio(NaN)", cls="aspect-btn active", id="aspect-free"),
                    Button("1:1", onclick="setAspectRatio(1)", cls="aspect-btn", id="aspect-1-1"),
                    Button("4:3", onclick="setAspectRatio(4/3)", cls="aspect-btn", id="aspect-4-3"),
                    Button("16:9", onclick="setAspectRatio(16/9)", cls="aspect-btn", id="aspect-16-9"),
                    Button("9:16", onclick="setAspectRatio(9/16)", cls="aspect-btn", id="aspect-9-16"),
                    cls="flex gap-2 mb-4 flex-wrap"
                ),

                # Image container for Cropper.js
                Div(
                    Img(id="crop-image", cls="max-w-full", style="display: block;"),
                    cls="max-h-[60vh] overflow-hidden flex items-center justify-center",
                    style="background-color: #191919;",
                    id="crop-container"
                ),

                # Action buttons
                Div(
                    Button("Reset Crop", onclick="resetCrop()",
                           cls="px-4 py-2 rounded-lg text-secondary hover:text-primary transition-colors"),
                    Button("Done", onclick="closeCropEditor()",
                           cls="px-6 py-2 rounded-lg font-medium transition-all duration-200 hover:bg-[#3a3a3a]",
                           style="background-color: #2a2a2a; border: 1px solid #3a3a3a; color: #e3e3e3;"),
                    cls="flex justify-between mt-4"
                ),

                cls="fixed top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-[95vw] max-w-4xl p-6 rounded-2xl z-50",
                style="background-color: #232323; border: 1px solid #3a3a3a;"
            ),
            id="crop-modal",
            cls="hidden"
        )

        # JavaScript for crop editor
        crop_js = Script(f"""
            let cropper = null;
            let currentFilename = null;
            const sessionId = '{session_id}';

            function openCropEditor(filename) {{
                currentFilename = filename;
                document.getElementById('crop-modal').classList.remove('hidden');

                const img = document.getElementById('crop-image');
                img.src = `/webp_fullsize?sid=${{sessionId}}&fn=${{encodeURIComponent(filename)}}`;

                img.onload = function() {{
                    if (cropper) {{
                        cropper.destroy();
                    }}

                    cropper = new Cropper(img, {{
                        viewMode: 1,
                        dragMode: 'crop',
                        autoCropArea: 1,
                        responsive: true,
                        guides: true,
                        center: true,
                        highlight: true,
                        cropBoxMovable: true,
                        cropBoxResizable: true,
                        background: true,
                        autoCrop: true,
                    }});

                    // Reset aspect ratio buttons
                    document.querySelectorAll('.aspect-btn').forEach(btn => btn.classList.remove('active'));
                    document.getElementById('aspect-free').classList.add('active');
                }};
            }}

            function closeCropEditor() {{
                // Auto-save crop when closing
                if (cropper && currentFilename) {{
                    const cropData = cropper.getData(true);
                    const imageData = cropper.getImageData();
                    // Capture filename before async operation
                    const filenameToSave = currentFilename;

                    // Only save if the crop actually changes something
                    // (not just the full image with no changes)
                    const isFullImage = (
                        Math.abs(cropData.x) < 2 &&
                        Math.abs(cropData.y) < 2 &&
                        Math.abs(cropData.width - imageData.naturalWidth) < 2 &&
                        Math.abs(cropData.height - imageData.naturalHeight) < 2
                    );

                    // Only save if there's an actual crop (not full image)
                    if (cropData.width > 0 && cropData.height > 0 && !isFullImage) {{
                        fetch('/webp_save_crop', {{
                            method: 'POST',
                            headers: {{'Content-Type': 'application/json'}},
                            body: JSON.stringify({{
                                session_id: sessionId,
                                filename: filenameToSave,
                                crop_data: cropData
                            }})
                        }}).then(response => response.json())
                          .then(data => {{
                              if (data.success) {{
                                  // Show crop badge on thumbnail
                                  const safeId = filenameToSave.replace(/\\./g, '-').replace(/ /g, '-').replace(/'/g, '-').replace(/"/g, '-');
                                  const badge = document.getElementById('crop-badge-' + safeId);
                                  if (badge) badge.classList.remove('hidden');

                                  // Refresh thumbnail with cache-busting to show cropped preview
                                  const thumbContainer = document.getElementById('thumb-' + safeId);
                                  if (thumbContainer) {{
                                      const thumbImg = thumbContainer.querySelector('img');
                                      if (thumbImg) {{
                                          const baseUrl = `/webp_thumbnail?sid=${{sessionId}}&fn=${{encodeURIComponent(filenameToSave)}}`;
                                          thumbImg.src = baseUrl + '&t=' + data.timestamp;
                                      }}
                                  }}
                              }}
                          }});
                    }}
                }}

                document.getElementById('crop-modal').classList.add('hidden');
                if (cropper) {{
                    cropper.destroy();
                    cropper = null;
                }}
                currentFilename = null;
            }}

            function setAspectRatio(ratio) {{
                if (cropper) {{
                    cropper.setAspectRatio(ratio);
                }}
                document.querySelectorAll('.aspect-btn').forEach(btn => btn.classList.remove('active'));
                event.target.classList.add('active');
            }}

            function resetCrop() {{
                if (!currentFilename) return;

                // Clear crop on server
                fetch('/webp_clear_crop', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        session_id: sessionId,
                        filename: currentFilename
                    }})
                }}).then(response => response.json())
                  .then(data => {{
                      if (data.success) {{
                          const safeId = currentFilename.replace(/\\./g, '-').replace(/ /g, '-').replace(/'/g, '-').replace(/"/g, '-');
                          const badge = document.getElementById('crop-badge-' + safeId);
                          if (badge) badge.classList.add('hidden');

                          // Refresh thumbnail to show original (uncropped) preview
                          const thumbContainer = document.getElementById('thumb-' + safeId);
                          if (thumbContainer) {{
                              const thumbImg = thumbContainer.querySelector('img');
                              if (thumbImg) {{
                                  const baseUrl = `/webp_thumbnail?sid=${{sessionId}}&fn=${{encodeURIComponent(currentFilename)}}`;
                                  thumbImg.src = baseUrl + '&t=' + data.timestamp;
                              }}
                          }}
                      }}
                  }});

                if (cropper) {{
                    cropper.reset();
                    cropper.clear();
                }}
            }}

            // Toggle resize option visibility based on output mode
            document.querySelectorAll('input[name="output_mode"]').forEach(radio => {{
                radio.addEventListener('change', (e) => {{
                    const resizeOption = document.getElementById('resize-option');
                    if (e.target.value === 'webp') {{
                        resizeOption.style.opacity = '1';
                        resizeOption.querySelector('select').disabled = false;
                    }} else {{
                        resizeOption.style.opacity = '0.5';
                        resizeOption.querySelector('select').disabled = true;
                    }}
                }});
            }});
        """)

        return Div(
            H3(f"{len(images)} Images Ready", cls="text-xl font-semibold text-primary mb-4"),
            P("Click any image to crop it. Crops are auto-saved when you close the editor.", cls="text-secondary text-sm mb-6"),
            thumbnail_grid,
            output_section,
            process_button,
            crop_modal,
            crop_js,
            cls="p-6 rounded-xl",
            style="background-color: #232323; border: 1px solid #3a3a3a;"
        )


    @rt('/webp_thumbnail')
    async def webp_thumbnail(sid: str, fn: str):
        """Serve thumbnail images. Use query params: ?sid=session_id&fn=filename"""
        import unicodedata

        # Try to find thumbnail by looking for _thumb.jpg version of the filename stem
        thumbnail_dir = THUMBNAILS_DIR / sid
        if not thumbnail_dir.exists():
            return Response(f"Session dir not found: {sid}", status_code=404)

        # The thumbnail is saved as {stem}_thumb.jpg
        stem = Path(fn).stem
        thumb_name = f"{stem}_thumb.jpg"

        # Try exact match first
        thumb_path = thumbnail_dir / thumb_name
        if thumb_path.exists():
            return FileResponse(str(thumb_path), media_type='image/jpeg')

        # Try with Unicode normalization (NFC vs NFD)
        stem_nfc = unicodedata.normalize('NFC', stem)
        stem_nfd = unicodedata.normalize('NFD', stem)

        for existing_file in thumbnail_dir.iterdir():
            existing_stem = existing_file.stem.replace('_thumb', '')
            existing_nfc = unicodedata.normalize('NFC', existing_stem)
            existing_nfd = unicodedata.normalize('NFD', existing_stem)

            if stem_nfc == existing_nfc or stem_nfd == existing_nfd or stem == existing_stem:
                return FileResponse(str(existing_file), media_type='image/jpeg')

        # Not found
        existing = [f.name for f in thumbnail_dir.iterdir()]
        return Response(f"Thumbnail not found: {thumb_name}. Existing: {existing}", status_code=404)


    @rt('/webp_fullsize')
    async def webp_fullsize(sid: str, fn: str):
        """Serve full-size images for Cropper.js. Use query params: ?sid=session_id&fn=filename"""
        import unicodedata

        # Look for file directly in uploads directory
        upload_dir = UPLOADS_DIR / sid
        if not upload_dir.exists():
            return Response(f"Upload dir not found: {sid}", status_code=404)

        # Find the original file - try exact match first
        original_path = upload_dir / fn
        if original_path.exists():
            pass  # Found it
        else:
            # Try with Unicode normalization
            filename_nfc = unicodedata.normalize('NFC', fn)
            filename_nfd = unicodedata.normalize('NFD', fn)
            found = False

            for existing_file in upload_dir.rglob('*'):
                if not existing_file.is_file():
                    continue
                existing_name = existing_file.name
                existing_nfc = unicodedata.normalize('NFC', existing_name)
                existing_nfd = unicodedata.normalize('NFD', existing_name)

                if (filename_nfc == existing_nfc or filename_nfd == existing_nfd or
                    fn == existing_name):
                    original_path = existing_file
                    found = True
                    break

            if not found:
                existing = [ef.name for ef in upload_dir.rglob('*') if ef.is_file()][:10]
                return Response(f"File not found: {fn}. Existing: {existing}", status_code=404)

        # Determine media type
        ext = original_path.suffix.lower()
        media_types = {
            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.png': 'image/png', '.gif': 'image/gif',
            '.webp': 'image/webp', '.bmp': 'image/bmp',
        }
        media_type = media_types.get(ext, 'application/octet-stream')

        return FileResponse(str(original_path), media_type=media_type)


    @rt('/webp_save_crop')
    async def webp_save_crop(request):
        """Save crop coordinates for an image and regenerate thumbnail with crop preview."""
        import time
        from PIL import Image

        try:
            data = await request.json()
            session_id = data.get('session_id')
            filename = data.get('filename')
            crop_data = data.get('crop_data')

            if not session_id or session_id not in conversion_state:
                return {"success": False, "error": "Session not found"}

            state = conversion_state[session_id]
            if filename not in state.get('images', {}):
                return {"success": False, "error": "Image not found"}

            # Store crop data
            state['images'][filename]['crop'] = crop_data

            # Regenerate thumbnail with crop applied
            original_path = Path(state['images'][filename]['original_path'])
            thumbnail_dir = Path(state['thumbnail_dir'])

            try:
                img = Image.open(original_path)

                # Apply crop
                x = int(crop_data.get('x', 0))
                y = int(crop_data.get('y', 0))
                width = int(crop_data.get('width', img.width))
                height = int(crop_data.get('height', img.height))
                img = img.crop((x, y, x + width, y + height))

                # Create thumbnail
                img.thumbnail((300, 300), Image.Resampling.LANCZOS)

                # Convert to RGB for JPEG
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (25, 25, 25))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    if img.mode in ('RGBA', 'LA'):
                        background.paste(img, mask=img.split()[-1])
                        img = background
                    else:
                        img = img.convert('RGB')
                elif img.mode != 'RGB':
                    img = img.convert('RGB')

                # Save thumbnail
                stem = Path(filename).stem
                thumb_path = thumbnail_dir / f"{stem}_thumb.jpg"
                img.save(thumb_path, 'JPEG', quality=85)

            except Exception as e:
                # Thumbnail generation failed, but crop data is still saved
                pass

            # Return success with timestamp for cache busting
            return {"success": True, "timestamp": int(time.time() * 1000)}

        except Exception as e:
            return {"success": False, "error": str(e)}


    @rt('/webp_clear_crop')
    async def webp_clear_crop(request):
        """Clear crop coordinates for an image and regenerate original thumbnail."""
        import time

        try:
            data = await request.json()
            session_id = data.get('session_id')
            filename = data.get('filename')

            if not session_id or session_id not in conversion_state:
                return {"success": False, "error": "Session not found"}

            state = conversion_state[session_id]
            if filename not in state.get('images', {}):
                return {"success": False, "error": "Image not found"}

            # Clear crop data
            state['images'][filename]['crop'] = None

            # Regenerate original thumbnail (without crop)
            original_path = Path(state['images'][filename]['original_path'])
            thumbnail_dir = Path(state['thumbnail_dir'])
            try:
                generate_thumbnail(original_path, thumbnail_dir)
            except Exception:
                pass

            return {"success": True, "timestamp": int(time.time() * 1000)}

        except Exception as e:
            return {"success": False, "error": str(e)}


    @rt('/webp_process_all')
    async def webp_process_all(sid: str, output_mode: str = 'webp', max_size_final: str = '', sess=None):
        """Process all images with crops applied."""
        session_id = sid

        if not session_id or session_id not in conversion_state:
            return Div(P("Session not found", cls="text-red-400"))

        state = conversion_state[session_id]
        upload_dir = Path(state['upload_dir'])
        result_dir = Path(state['result_dir'])

        # Parse max dimension
        max_dimension = None
        if max_size_final and output_mode == 'webp':
            try:
                max_dimension = int(max_size_final)
            except ValueError:
                pass

        # Get crops dict
        crops = {}
        for filename, img_data in state.get('images', {}).items():
            if img_data.get('crop'):
                crops[filename] = img_data['crop']

        # Update state
        state['status'] = 'processing'
        state['output_mode'] = output_mode
        state['max_dimension'] = max_dimension
        state['progress_percent'] = 0
        state['progress_message'] = 'Starting...'

        # Start background processing
        asyncio.create_task(process_images_background(session_id, upload_dir, result_dir, output_mode, max_dimension, crops))

        # Return progress section
        return Div(
            H3("Processing", cls="text-xl font-semibold text-primary mb-4"),
            Div(
                Div(
                    Div(cls="h-3 rounded-full transition-all duration-200", style="background-color: #e3e3e3; width: 0%;", id="process-bar"),
                    cls="w-full rounded-full overflow-hidden",
                    style="background-color: #3a3a3a;"
                ),
                cls="mb-3"
            ),
            P("Starting...", cls="text-secondary", id="process-message"),
            Script(f"""
                const gallerySection = document.getElementById('gallery-section');
                gallerySection.setAttribute('hx-ext', 'sse');
                gallerySection.setAttribute('sse-connect', '/webp_progress_stream?sid={session_id}');
                gallerySection.setAttribute('sse-swap', 'message');
                gallerySection.setAttribute('hx-swap', 'innerHTML');
                htmx.process(gallerySection);
            """),
            cls="p-6 rounded-xl",
            style="background-color: #232323; border: 1px solid #3a3a3a;"
        )


    async def process_images_background(session_id: str, upload_dir: Path, result_dir: Path, output_mode: str, max_dimension: int = None, crops: dict = None):
        """Background task to process images with crops."""
        try:
            state = conversion_state[session_id]

            def progress_callback(current, total, filename):
                percent = int((current / total) * 100)
                state['progress_percent'] = percent
                state['progress_message'] = f"Processing {current}/{total}"

            loop = asyncio.get_event_loop()

            if output_mode == 'webp':
                results = await loop.run_in_executor(
                    None,
                    lambda: process_images(upload_dir, result_dir, 80, progress_callback, max_dimension, crops)
                )

                if results['success']:
                    webp_files = list(result_dir.glob('*.webp'))
                    if len(webp_files) > 1:
                        zip_path = result_dir / 'converted_images.zip'
                        create_result_zip(result_dir, zip_path, '*.webp')
                        state['result_file'] = str(zip_path)
                        state['is_zip'] = True
                    elif len(webp_files) == 1:
                        state['result_file'] = str(webp_files[0])
                        state['is_zip'] = False

                    state['status'] = 'complete'
                    state['results'] = results
                else:
                    state['status'] = 'error'
                    state['error'] = results.get('error', 'Unknown error')
            else:
                # Crop only mode
                results = await loop.run_in_executor(
                    None,
                    lambda: process_images_crop_only(upload_dir, result_dir, progress_callback, crops)
                )

                if results['success']:
                    # Find all output files
                    output_files = [f for f in result_dir.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]
                    if len(output_files) > 1:
                        zip_path = result_dir / 'cropped_images.zip'
                        create_result_zip(result_dir, zip_path, '*')
                        state['result_file'] = str(zip_path)
                        state['is_zip'] = True
                    elif len(output_files) == 1:
                        state['result_file'] = str(output_files[0])
                        state['is_zip'] = False

                    state['status'] = 'complete'
                    state['results'] = results
                else:
                    state['status'] = 'error'
                    state['error'] = results.get('error', 'Unknown error')

        except Exception as e:
            conversion_state[session_id]['status'] = 'error'
            conversion_state[session_id]['error'] = str(e)


    async def convert_images_background(session_id: str, upload_dir: Path, result_dir: Path, max_dimension: int = None):
        """Background task to convert images."""
        try:
            conversion_state[session_id]['status'] = 'processing'

            def progress_callback(current, total, filename):
                percent = int((current / total) * 100)
                conversion_state[session_id]['progress_percent'] = percent
                conversion_state[session_id]['progress_message'] = f"Converting {current}/{total}"
                conversion_state[session_id]['current_file'] = filename

            # Run conversion in thread pool to not block
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: process_images(upload_dir, result_dir, 80, progress_callback, max_dimension)
            )

            if results['success']:
                # Create ZIP if multiple files
                webp_files = list(result_dir.glob('*.webp'))
                if len(webp_files) > 1:
                    zip_path = result_dir / 'converted_images.zip'
                    create_result_zip(result_dir, zip_path)
                    conversion_state[session_id]['result_file'] = str(zip_path)
                    conversion_state[session_id]['is_zip'] = True
                elif len(webp_files) == 1:
                    conversion_state[session_id]['result_file'] = str(webp_files[0])
                    conversion_state[session_id]['is_zip'] = False

                conversion_state[session_id]['status'] = 'complete'
                conversion_state[session_id]['results'] = results
            else:
                conversion_state[session_id]['status'] = 'error'
                conversion_state[session_id]['error'] = results.get('error', 'Unknown error')

        except Exception as e:
            conversion_state[session_id]['status'] = 'error'
            conversion_state[session_id]['error'] = str(e)


    @rt('/webp_progress_stream')
    async def webp_progress_stream(sid: str = None, sess=None):
        """SSE endpoint for conversion progress."""
        shutdown_event = signal_shutdown()
        # Get session_id from URL parameter (more reliable than session for SSE)
        session_id = sid or (sess.get('webp_session_id') if sess else None)

        async def progress_generator():
            if not session_id:
                await asyncio.sleep(0.1)
                return

            last_percent = -1
            last_status = None

            while not shutdown_event.is_set():
                if session_id not in conversion_state:
                    yield sse_message(P("Session not found", cls="text-red-400"))
                    break

                state = conversion_state[session_id]
                status = state.get('status', 'unknown')
                percent = state.get('progress_percent', 0)
                message = state.get('progress_message', 'Processing...')

                # Only send update if something changed
                if percent != last_percent or status != last_status:
                    # Progress bar HTML
                    progress_html = Div(
                        Div(
                            Div(
                                cls="h-3 rounded-full transition-all duration-300",
                                style=f"width: {percent}%; background-color: #e3e3e3;"
                            ),
                            cls="w-full rounded-full overflow-hidden",
                            style="background-color: #3a3a3a;"
                        ),
                        P(message, cls="text-secondary mt-3"),
                        cls="mb-3"
                    )

                    yield sse_message(progress_html, event="message")

                    last_percent = percent
                    last_status = status

                    # If complete, show results
                    if status == 'complete':
                        results = state.get('results', {})
                        output_mode = state.get('output_mode', 'webp')
                        is_crop_only = output_mode == 'crop_only'

                        if state.get('is_zip'):
                            download_label = 'ZIP'
                        elif is_crop_only:
                            download_label = 'Image'
                        else:
                            download_label = 'WebP'

                        # Build file rows
                        file_rows = []
                        for f in results.get('files', [])[:20]:
                            if f.get('success'):
                                # Format dimensions
                                final_dims = f.get('final_dimensions', (0, 0))
                                dims_text = f"{final_dims[0]}×{final_dims[1]}"
                                if f.get('resized') or f.get('cropped'):
                                    dims_text += " ✓"

                                # Get size fields based on mode
                                if is_crop_only:
                                    output_size = f.get('output_size_formatted', '')
                                else:
                                    output_size = f.get('webp_size_formatted', '')

                                file_rows.append(
                                    Tr(
                                        Td(f.get('original_name', ''), cls="py-2 text-primary"),
                                        Td(dims_text, cls="py-2 text-secondary"),
                                        Td(f.get('original_size_formatted', ''), cls="py-2 text-secondary"),
                                        Td(output_size, cls="py-2 text-secondary"),
                                        Td("Cropped" if f.get('cropped') else "-", cls="py-2 text-green-400" if f.get('cropped') else "py-2 text-secondary"),
                                        cls="border-b",
                                        style="border-color: #3a3a3a;"
                                    )
                                )

                        more_text = None
                        if len(results.get('files', [])) > 20:
                            more_text = P(f"... and {len(results.get('files', [])) - 20} more files", cls="text-secondary text-sm mt-2")

                        # Stats differ by mode
                        if is_crop_only:
                            cropped_count = sum(1 for f in results.get('files', []) if f.get('cropped'))
                            stats_grid = Div(
                                Div(
                                    Div(str(results.get('successful_files', 0)), cls="text-2xl font-semibold text-primary"),
                                    Div("Files processed", cls="text-secondary text-sm"),
                                    cls="p-3 rounded-lg",
                                    style="background-color: #2a2a2a;"
                                ),
                                Div(
                                    Div(str(cropped_count), cls="text-2xl font-semibold text-primary"),
                                    Div("Images cropped", cls="text-secondary text-sm"),
                                    cls="p-3 rounded-lg",
                                    style="background-color: #2a2a2a;"
                                ),
                                Div(
                                    Div(results.get('total_output_formatted', '0 B'), cls="text-2xl font-semibold text-primary"),
                                    Div("Total size", cls="text-secondary text-sm"),
                                    cls="p-3 rounded-lg",
                                    style="background-color: #2a2a2a;"
                                ),
                                cls="grid grid-cols-3 gap-4 text-center mb-6"
                            )
                            title = "Processing Complete"
                        else:
                            stats_grid = Div(
                                Div(
                                    Div(str(results.get('successful_files', 0)), cls="text-2xl font-semibold text-primary"),
                                    Div("Files converted", cls="text-secondary text-sm"),
                                    cls="p-3 rounded-lg",
                                    style="background-color: #2a2a2a;"
                                ),
                                Div(
                                    Div(f"{results.get('total_savings_percent', 0)}%", cls="text-2xl font-semibold text-primary"),
                                    Div("Size reduced", cls="text-secondary text-sm"),
                                    cls="p-3 rounded-lg",
                                    style="background-color: #2a2a2a;"
                                ),
                                Div(
                                    Div(results.get('total_webp_formatted', '0 B'), cls="text-2xl font-semibold text-primary"),
                                    Div("Total size", cls="text-secondary text-sm"),
                                    cls="p-3 rounded-lg",
                                    style="background-color: #2a2a2a;"
                                ),
                                cls="grid grid-cols-3 gap-4 text-center mb-6"
                            )
                            title = "Conversion Complete"

                        # Complete results
                        complete_html = Div(
                            H3(title, cls="text-xl font-semibold text-primary mb-4"),
                            stats_grid,
                            # File table
                            Table(
                                Thead(
                                    Tr(
                                        Th("File", cls="py-2"),
                                        Th("Dims", cls="py-2"),
                                        Th("Original", cls="py-2"),
                                        Th("Output", cls="py-2"),
                                        Th("Status", cls="py-2"),
                                        cls="border-b text-left text-secondary",
                                        style="border-color: #3a3a3a;"
                                    )
                                ),
                                Tbody(*file_rows),
                                cls="w-full text-sm mb-4"
                            ),
                            more_text if more_text else "",
                            # Download button
                            Div(
                                A(
                                    f"Download {download_label}",
                                    href=f"/download_webp_result?sid={session_id}",
                                    cls="inline-block px-6 py-3 rounded-xl font-medium transition-all duration-200 hover:bg-[#3a3a3a]",
                                    style="background-color: #2a2a2a; border: 1px solid #3a3a3a; color: #e3e3e3;"
                                ),
                                cls="mt-6"
                            )
                        )

                        yield sse_message(complete_html, event="message")
                        break

                    elif status == 'error':
                        error = state.get('error', 'Unknown error')
                        yield sse_message(P(f"Error: {error}", cls="text-red-400"), event="message")
                        break

                await asyncio.sleep(0.3)

        return EventStream(progress_generator())


    @rt('/download_webp_result')
    async def download_webp_result(auth, sid: str = None, sess=None):
        """Download the processed file(s)."""
        # Get session_id from URL parameter or session
        session_id = sid or (sess.get('webp_session_id') if sess else None)

        if not session_id or session_id not in conversion_state:
            return Div(P("No conversion result found", cls="text-red-400"))

        state = conversion_state[session_id]
        result_file = state.get('result_file')

        if not result_file or not Path(result_file).exists():
            return Div(P("Result file not found", cls="text-red-400"))

        file_path = Path(result_file)
        is_zip = state.get('is_zip', False)
        output_mode = state.get('output_mode', 'webp')

        # Determine filename and media type
        if is_zip:
            if output_mode == 'crop_only':
                filename = 'cropped_images.zip'
            else:
                filename = 'converted_images.zip'
            media_type = 'application/zip'
        else:
            filename = file_path.name
            # Determine media type based on extension
            ext = file_path.suffix.lower()
            media_types = {
                '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.png': 'image/png', '.gif': 'image/gif',
                '.webp': 'image/webp', '.bmp': 'image/bmp',
            }
            media_type = media_types.get(ext, 'application/octet-stream')

        # Cleanup function
        async def cleanup():
            await asyncio.sleep(1)
            upload_dir = state.get('upload_dir')
            result_dir = state.get('result_dir')
            thumbnail_dir = state.get('thumbnail_dir')
            if upload_dir and Path(upload_dir).exists():
                shutil.rmtree(upload_dir, ignore_errors=True)
            if result_dir and Path(result_dir).exists():
                shutil.rmtree(result_dir, ignore_errors=True)
            if thumbnail_dir and Path(thumbnail_dir).exists():
                shutil.rmtree(thumbnail_dir, ignore_errors=True)
            if session_id in conversion_state:
                del conversion_state[session_id]
            if sess and 'webp_session_id' in sess:
                del sess['webp_session_id']

        # Start cleanup in background
        asyncio.create_task(cleanup())

        return FileResponse(
            path=str(file_path),
            media_type=media_type,
            filename=filename,
        )


    return {
        'webp_converter': webp_converter,
        'upload_webp_images': upload_webp_images,
        'webp_thumbnail': webp_thumbnail,
        'webp_fullsize': webp_fullsize,
        'webp_save_crop': webp_save_crop,
        'webp_clear_crop': webp_clear_crop,
        'webp_process_all': webp_process_all,
        'webp_progress_stream': webp_progress_stream,
        'download_webp_result': download_webp_result,
    }
