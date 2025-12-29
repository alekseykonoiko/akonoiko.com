"""
WebP Converter Routes

FastHTML routes for the WebP image converter project.
"""

import asyncio
import shutil
import uuid
from pathlib import Path
from typing import Dict

from fasthtml.common import *
from starlette.responses import FileResponse

from .converter import (
    process_images,
    extract_zip,
    find_images,
    create_result_zip,
    SUPPORTED_EXTENSIONS,
)


# Shared state for tracking conversion progress
conversion_state: Dict[str, Dict] = {}

# Temp directories
TEMP_DIR = Path(__file__).parent.parent.parent / 'temp'
UPLOADS_DIR = TEMP_DIR / 'webp_uploads'
RESULTS_DIR = TEMP_DIR / 'webp_results'


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
                    # Hidden file inputs
                    Input(
                        type="file",
                        name="files",
                        multiple=True,
                        accept=",".join(SUPPORTED_EXTENSIONS) + ",.zip",
                        cls="absolute inset-0 opacity-0 cursor-pointer",
                        id="file-input"
                    ),
                    # Folder input (webkitdirectory for Chrome/Edge/Firefox)
                    Input(
                        type="file",
                        name="folder",
                        webkitdirectory=True,
                        cls="hidden",
                        id="folder-input"
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

                # Submit button
                Button(
                    'Convert to WebP',
                    type='submit',
                    cls="w-full px-6 py-4 rounded-xl font-medium transition-all duration-200 hover:bg-[#3a3a3a] hover:scale-[1.02] active:scale-[0.98]",
                    style="background-color: #2a2a2a; border: 1px solid #3a3a3a; color: #e3e3e3;",
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

                // Track selected files
                let allFiles = [];

                // Update file display
                function updateFileDisplay() {
                    if (allFiles.length === 0) {
                        selectedFiles.textContent = '';
                    } else if (allFiles.length === 1) {
                        selectedFiles.textContent = `Selected: ${allFiles[0].name}`;
                    } else {
                        selectedFiles.textContent = `Selected: ${allFiles.length} files`;
                    }
                }

                // File input change
                fileInput.addEventListener('change', (e) => {
                    allFiles = Array.from(e.target.files);
                    updateFileDisplay();
                });

                // Folder input change
                folderInput.addEventListener('change', (e) => {
                    allFiles = Array.from(e.target.files);
                    updateFileDisplay();
                });

                // Drag and drop
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
                    allFiles = Array.from(dt.files);
                    updateFileDisplay();
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

        content = Div(
            H1("WebP Converter", cls="text-3xl font-semibold mb-2 text-primary"),
            P("Convert images to optimized WebP format (80% quality)", cls="text-secondary mb-8"),
            upload_section,
            progress_section,
            results_section,
            A(
                "Back to Dashboard",
                href="/",
                cls="inline-block text-secondary hover:text-primary transition-colors text-sm"
            ),
            cls="max-w-3xl mx-auto px-6 py-12"
        )

        return (
            Title("WebP Converter"),
            Div(content, cls="min-h-screen")
        )


    @rt('/upload_webp_images')
    async def upload_webp_images(files: list = None, folder: list = None, max_size: str = '', custom_size: str = '', sess=None):
        """Handle image upload and start conversion."""

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

        # Combine files from both inputs
        all_files = []
        if files:
            all_files.extend(files if isinstance(files, list) else [files])
        if folder:
            all_files.extend(folder if isinstance(folder, list) else [folder])

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
        upload_dir.mkdir(parents=True, exist_ok=True)
        result_dir.mkdir(parents=True, exist_ok=True)

        # Save uploaded files
        for uploaded_file in all_files:
            filename = Path(uploaded_file.filename).name  # Security: only use filename
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

        # Store session data
        sess['webp_session_id'] = session_id
        conversion_state[session_id] = {
            'status': 'uploaded',
            'progress_percent': 0,
            'progress_message': 'Starting conversion...',
            'current_file': '',
            'upload_dir': str(upload_dir),
            'result_dir': str(result_dir),
            'result_file': None,
            'results': None,
            'max_dimension': max_dimension,
        }

        # Start background conversion
        asyncio.create_task(convert_images_background(session_id, upload_dir, result_dir, max_dimension))

        # Return JS to show progress section and connect SSE
        return Div(
            P("Upload complete! Starting conversion...", cls="text-green-400 mb-4"),
            Script(f"""
                // Hide upload section, show progress
                document.getElementById('upload-section').classList.add('hidden');
                document.getElementById('progress-section').classList.remove('hidden');

                // Connect to SSE for progress updates (pass session_id in URL)
                const progressSection = document.getElementById('progress-section');
                progressSection.setAttribute('hx-ext', 'sse');
                progressSection.setAttribute('sse-connect', '/webp_progress_stream?sid={session_id}');
                progressSection.setAttribute('sse-swap', 'message');
                progressSection.setAttribute('hx-swap', 'innerHTML');
                htmx.process(progressSection);
            """),
            cls="mt-4"
        )


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
                        download_label = 'ZIP' if state.get('is_zip') else 'WebP'

                        # Build file rows
                        file_rows = []
                        for f in results.get('files', [])[:20]:
                            if f.get('success'):
                                # Format dimensions
                                final_dims = f.get('final_dimensions', (0, 0))
                                dims_text = f"{final_dims[0]}×{final_dims[1]}"
                                if f.get('resized'):
                                    dims_text += " ↓"  # Arrow indicates resized
                                file_rows.append(
                                    Tr(
                                        Td(f.get('original_name', ''), cls="py-2 text-primary"),
                                        Td(dims_text, cls="py-2 text-secondary"),
                                        Td(f.get('original_size_formatted', ''), cls="py-2 text-secondary"),
                                        Td(f.get('webp_size_formatted', ''), cls="py-2 text-secondary"),
                                        Td(f"-{f.get('savings_percent', 0)}%", cls="py-2 text-green-400"),
                                        cls="border-b",
                                        style="border-color: #3a3a3a;"
                                    )
                                )

                        more_text = None
                        if len(results.get('files', [])) > 20:
                            more_text = P(f"... and {len(results.get('files', [])) - 20} more files", cls="text-secondary text-sm mt-2")

                        # Complete results
                        complete_html = Div(
                            H3("Conversion Complete", cls="text-xl font-semibold text-primary mb-4"),
                            # Stats grid
                            Div(
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
                            ),
                            # File table
                            Table(
                                Thead(
                                    Tr(
                                        Th("File", cls="py-2"),
                                        Th("Size", cls="py-2"),
                                        Th("Original", cls="py-2"),
                                        Th("WebP", cls="py-2"),
                                        Th("Saved", cls="py-2"),
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
        """Download the converted WebP file(s)."""
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

        # Determine filename and media type
        if is_zip:
            filename = 'converted_images.zip'
            media_type = 'application/zip'
        else:
            filename = file_path.name
            media_type = 'image/webp'

        # Cleanup function
        async def cleanup():
            await asyncio.sleep(1)
            upload_dir = state.get('upload_dir')
            result_dir = state.get('result_dir')
            if upload_dir and Path(upload_dir).exists():
                shutil.rmtree(upload_dir, ignore_errors=True)
            if result_dir and Path(result_dir).exists():
                shutil.rmtree(result_dir, ignore_errors=True)
            if session_id in conversion_state:
                del conversion_state[session_id]
            if 'webp_session_id' in sess:
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
        'webp_progress_stream': webp_progress_stream,
        'download_webp_result': download_webp_result,
    }
