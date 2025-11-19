"""
Instagram Aggregator Routes

All routes and handlers for the Instagram follower aggregator functionality.
"""
from fasthtml.common import *
import zipfile
import shutil
import uuid
import asyncio
from pathlib import Path
from starlette.responses import FileResponse, RedirectResponse, StreamingResponse
from starlette.background import BackgroundTasks
from starlette.datastructures import UploadFile
from . import follower_aggregator

# Configuration
TEMP_DIR = Path(__file__).parent.parent.parent / "temp"
TEMP_UPLOADS = TEMP_DIR / "uploads"
TEMP_RESULTS = TEMP_DIR / "results"

# Ensure temp directories exist
TEMP_UPLOADS.mkdir(parents=True, exist_ok=True)
TEMP_RESULTS.mkdir(parents=True, exist_ok=True)

# Maximum file size: 100MB
MAX_FILE_SIZE = 100 * 1024 * 1024

# Shared state for processing progress (keyed by session ID)
# This allows background tasks to update progress
processing_state = {}

def cleanup_temp_files(upload_path: Path = None, result_path: Path = None):
    """Clean up temporary files."""
    try:
        if upload_path and upload_path.exists():
            if upload_path.is_dir():
                shutil.rmtree(upload_path)
            else:
                upload_path.unlink()
        if result_path and result_path.exists():
            result_path.unlink()
    except Exception as e:
        print(f"Error cleaning up temp files: {e}")

def setup_routes(rt):
    """
    Setup Instagram aggregator routes.
    
    Args:
        rt: Route decorator from FastHTML app
        
    Returns:
        dict: Route references for use in main.py
    """
    
    # Instagram Aggregator main page
    @rt('/instagram_aggregator')
    def instagram_aggregator(auth):
        content = Div(
            H1("Instagram Follower Aggregator", cls="text-3xl font-semibold mb-3 text-primary"),
            P("Upload your Instagram data archive (ZIP file) to generate an aggregated Excel report.", cls="text-base text-secondary mb-8"),
            
            # Upload form
            Div(
                id="upload-section",
                cls="mb-8 p-6 rounded-lg",
                style="background-color: #232323; border: 1px solid #3a3a3a;"
            )(
                Form(
                    hx_post=upload_instagram_data,
                    hx_target="#upload-result",
                    hx_encoding="multipart/form-data",
                    cls="space-y-4",
                    id="upload-form"
                )(
                    Div()(
                        Label("Instagram Data Archive (ZIP)", fr="zipfile", cls="block text-sm font-medium mb-2 text-primary"),
                    Input(
                        id="zipfile",
                        name="uploaded_file",
                        type="file",
                        accept=".zip",
                        required=True,
                            cls="w-full px-4 py-3 rounded-lg transition-all duration-200 outline-none focus:bg-[#3a3a3a] hover:bg-[#3a3a3a] focus:ring-2 focus:ring-white/20",
                            style="background-color: #2a2a2a; border: 1px solid #3a3a3a; color: #e3e3e3;"
                        ),
                        P("Maximum file size: 100MB", cls="text-xs text-secondary mt-1")
                    ),
                    # Upload progress bar (hidden initially)
                    Div(
                        id="upload-progress-container",
                        cls="hidden mb-4"
                    )(
                        Div(
                            cls="mb-2",
                            style="background-color: #2a2a2a; border-radius: 0.5rem; overflow: hidden; height: 1rem;"
                        )(
                            Div(
                                id="upload-progress-bar",
                                cls="h-full transition-all duration-300",
                                style="width: 0%; background-color: #4a9eff;"
                            )
                        ),
                        P(id="upload-progress-text", cls="text-xs text-secondary", text="Uploading...")
                    ),
                    Button(
                        "Upload and Process",
                        type="submit",
                        id="upload-btn",
                        cls="w-full px-6 py-4 rounded-xl font-medium transition-all duration-200 hover:bg-[#3a3a3a] hover:scale-[1.02] active:scale-[0.98] active:bg-[#2a2a2a] focus:bg-[#3a3a3a] focus:ring-2 focus:ring-white/20",
                        style="background-color: #2a2a2a; border: 1px solid #3a3a3a; color: #e3e3e3;"
                    )
                ),
                Div(id="upload-result", cls="mt-4"),
                # JavaScript for upload progress tracking
                Script("""
                    document.getElementById('upload-form').addEventListener('htmx:xhr:progress', function(evt) {
                        const progressContainer = document.getElementById('upload-progress-container');
                        const progressBar = document.getElementById('upload-progress-bar');
                        const progressText = document.getElementById('upload-progress-text');

                        if (evt.detail.lengthComputable) {
                            progressContainer.classList.remove('hidden');
                            const percentComplete = Math.round((evt.detail.loaded / evt.detail.total) * 100);
                            progressBar.style.width = percentComplete + '%';

                            const loadedMB = (evt.detail.loaded / (1024 * 1024)).toFixed(2);
                            const totalMB = (evt.detail.total / (1024 * 1024)).toFixed(2);
                            progressText.textContent = `Uploading... ${percentComplete}% (${loadedMB}MB / ${totalMB}MB)`;
                        }
                    });

                    document.getElementById('upload-form').addEventListener('htmx:beforeRequest', function() {
                        document.getElementById('upload-btn').disabled = true;
                        document.getElementById('upload-btn').textContent = 'Uploading...';
                    });

                    document.getElementById('upload-form').addEventListener('htmx:afterRequest', function() {
                        document.getElementById('upload-progress-container').classList.add('hidden');
                        document.getElementById('upload-btn').disabled = false;
                        document.getElementById('upload-btn').textContent = 'Upload and Process';
                    });
                """)
            ),
            
            # Progress section (hidden initially, SSE will be connected via JS after upload)
            Div(
                id="progress-section",
                cls="mb-8 p-6 rounded-lg hidden",
                style="background-color: #232323; border: 1px solid #3a3a3a;"
            )(
                H2("Processing...", cls="text-xl font-semibold mb-4 text-primary"),
                Div(
                    id="progress-container"
                )(
                    Div(
                        id="progress-bar-container",
                        cls="mb-4"
                    )(
                        Div(
                            id="progress-bar",
                            cls="h-4 rounded-full transition-all duration-300",
                            style="width: 0%; background-color: #4a9eff;"
                        )
                    ),
                    P(id="progress-text", cls="text-sm text-secondary", text="Initializing...")
                )
            ),
            
            # Download section (hidden initially)
            Div(
                id="download-section",
                cls="mb-8 p-6 rounded-lg hidden",
                style="background-color: #232323; border: 1px solid #3a3a3a;"
            )(
                H2("Processing Complete!", cls="text-xl font-semibold mb-4 text-primary"),
                P("Your Excel file is ready for download.", cls="text-base text-secondary mb-4"),
                A(
                    "Download Excel File",
                    href="/download_result",
                    id="download-btn",
                    download="followers_aggregated.xlsx",
                    hx_boost="false",  # Disable HTMX for this link to ensure direct download
                    cls="inline-block px-6 py-4 rounded-xl font-medium transition-all duration-200 hover:bg-[#3a3a3a] hover:scale-[1.02] active:scale-[0.98] active:bg-[#2a2a2a] focus:bg-[#3a3a3a] focus:ring-2 focus:ring-white/20",
                    style="background-color: #2a2a2a; border: 1px solid #3a3a3a; color: #e3e3e3;"
                )
            ),
            
            A(
                "Back to Home",
                href="/",
                cls="inline-block bg-white text-black px-4 py-2 rounded hover:bg-gray-100 transition-colors text-sm font-medium"
            ),
            cls="max-w-3xl mx-auto px-6 py-12"
        )
        
        return Titled("Instagram Aggregator", content)

    # Upload handler
    @rt('/upload_instagram_data')
    async def upload_instagram_data(uploaded_file: UploadFile, sess):
        """Handle ZIP file upload and extraction."""
        try:
            # Validate file type
            if not uploaded_file.filename.endswith('.zip'):
                return Div(
                    P("Error: Please upload a ZIP file.", cls="text-red-400 text-sm"),
                    cls="p-4 rounded bg-red-900/20 border border-red-500/50"
                )
            
            # Check file size
            file_content = await uploaded_file.read()
            if len(file_content) > MAX_FILE_SIZE:
                return Div(
                    P(f"Error: File size exceeds maximum of {MAX_FILE_SIZE / (1024*1024):.0f}MB.", cls="text-red-400 text-sm"),
                    cls="p-4 rounded bg-red-900/20 border border-red-500/50"
                )
            
            # Generate unique session ID for this upload
            session_id = str(uuid.uuid4())
            upload_dir = TEMP_UPLOADS / session_id
            upload_dir.mkdir(parents=True, exist_ok=True)
            
            # Save ZIP file
            zip_path = upload_dir / uploaded_file.filename
            zip_path.write_bytes(file_content)
            
            # Extract ZIP file
            extract_dir = upload_dir / "extracted"
            extract_dir.mkdir(parents=True, exist_ok=True)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # Store in session and shared state
            sess['instagram_session_id'] = session_id
            sess['instagram_upload_path'] = str(upload_dir)  # Store parent directory for cleanup
            
            # Initialize shared state
            processing_state[session_id] = {
                'status': 'uploaded',
                'progress_percent': 0,
                'progress_message': 'Uploaded successfully',
                'result_file': None,
                'upload_path': str(upload_dir)
            }
            
            # Start processing in background
            asyncio.create_task(process_instagram_data_background(session_id, extract_dir))
            
            return Div(
                P("File uploaded successfully! Processing started...", cls="text-green-400 text-sm mb-2"),
                Script("""
                    document.getElementById('upload-section').classList.add('hidden');
                    const progressSection = document.getElementById('progress-section');
                    progressSection.classList.remove('hidden');
                    // Connect SSE after showing the section
                    const progressContainer = document.getElementById('progress-container');
                    progressContainer.setAttribute('hx-ext', 'sse');
                    progressContainer.setAttribute('sse-connect', '/progress_stream');
                    progressContainer.setAttribute('sse-swap', 'message');
                    progressContainer.setAttribute('hx-swap', 'innerHTML');
                    // Trigger HTMX to process the new attributes
                    htmx.process(progressContainer);
                """),
                cls="p-4 rounded bg-green-900/20 border border-green-500/50"
            )
            
        except zipfile.BadZipFile:
            return Div(
                P("Error: Invalid ZIP file.", cls="text-red-400 text-sm"),
                cls="p-4 rounded bg-red-900/20 border border-red-500/50"
            )
        except Exception as e:
            return Div(
                P(f"Error: {str(e)}", cls="text-red-400 text-sm"),
                cls="p-4 rounded bg-red-900/20 border border-red-500/50"
            )

    # Background processing function
    async def process_instagram_data_background(session_id: str, upload_path: Path):
        """Process Instagram data in background."""
        try:
            if session_id not in processing_state:
                return
            
            processing_state[session_id]['status'] = 'processing'
            
            if not upload_path.exists():
                processing_state[session_id]['status'] = 'error'
                processing_state[session_id]['progress_message'] = 'Error: Upload directory not found'
                return
            
            # Find instagram-photia folder or use upload_path directly
            data_dir = upload_path
            if (upload_path / "instagram-photia").exists():
                data_dir = upload_path / "instagram-photia"
            elif not (upload_path / "connections").exists():
                processing_state[session_id]['status'] = 'error'
                processing_state[session_id]['progress_message'] = 'Error: Invalid Instagram data structure'
                return
            
            # Create output directory
            output_dir = TEMP_RESULTS / session_id
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Progress callback
            def progress_callback(message: str, percent: int):
                if session_id in processing_state:
                    processing_state[session_id]['progress_percent'] = percent
                    processing_state[session_id]['progress_message'] = message
            
            # Process data (run in thread pool to avoid blocking)
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: follower_aggregator.process_instagram_data(
                    data_directory=data_dir,
                    output_directory=output_dir,
                    output_filename="followers_aggregated",
                    export_jsonl=False,
                    export_excel=True,
                    progress_callback=progress_callback
                )
            )
            
            # Store result file path
            excel_file = output_dir / "followers_aggregated.xlsx"
            if excel_file.exists():
                processing_state[session_id]['result_file'] = str(excel_file)
                processing_state[session_id]['status'] = 'complete'
                processing_state[session_id]['progress_percent'] = 100
                processing_state[session_id]['progress_message'] = 'Готово!'
            else:
                processing_state[session_id]['status'] = 'error'
                processing_state[session_id]['progress_message'] = 'Error: Excel file not generated'
                
        except Exception as e:
            if session_id in processing_state:
                processing_state[session_id]['status'] = 'error'
                processing_state[session_id]['progress_message'] = f'Error: {str(e)}'

    # Progress stream (SSE)
    @rt('/progress_stream')
    async def progress_stream(sess):
        """Server-Sent Events stream for progress updates."""
        shutdown_event = signal_shutdown()  # signal_shutdown is from fasthtml.common
        
        session_id = sess.get('instagram_session_id')
        
        async def progress_generator():
            # If no session_id, wait a bit and close gracefully
            if not session_id:
                await asyncio.sleep(0.1)
                return
            
            last_percent = -1
            last_status = None
            
            while not shutdown_event.is_set():
                # Get state from shared processing_state
                state = processing_state.get(session_id, {})
                status = state.get('status', 'idle')
                percent = state.get('progress_percent', 0)
                message = state.get('progress_message', '')
                
                # Only send update if something changed
                if percent != last_percent or status != last_status:
                    progress_html = Div(
                        Div(
                            Div(
                                id="progress-bar-inner",
                                cls="h-4 rounded-full transition-all duration-300",
                                style=f"width: {percent}%; background-color: #4a9eff;"
                            ),
                            id="progress-bar-container",
                            cls="mb-4",
                            style="background-color: #2a2a2a; border-radius: 0.5rem; overflow: hidden;"
                        ),
                        P(message, id="progress-text", cls="text-sm text-secondary")
                    )
                    
                    yield sse_message(progress_html, event="message")
                    
                    last_percent = percent
                    last_status = status
                    
                    # If complete or error, send final update and break
                    if status == 'complete':
                        # Store result file in session for download
                        sess['instagram_result_file'] = state.get('result_file')
                        yield sse_message(
                            Script("""
                                document.getElementById('progress-section').classList.add('hidden');
                                document.getElementById('download-section').classList.remove('hidden');
                            """),
                            event="message"
                        )
                        break
                    elif status == 'error':
                        yield sse_message(
                            Div(
                                P(f"Error: {message}", cls="text-red-400 text-sm"),
                                cls="p-4 rounded bg-red-900/20 border border-red-500/50"
                            ),
                            event="message"
                        )
                        break
                
                await asyncio.sleep(0.5)  # Poll every 500ms
        
        return EventStream(progress_generator())

    # Download handler
    @rt('/download_result')
    async def download_result(auth, sess):
        """Download the processed Excel file."""
        try:
            session_id = sess.get('instagram_session_id')
            upload_path = sess.get('instagram_upload_path')
            
            # Get result file from processing_state (more reliable than session)
            result_file = None
            if session_id:
                state = processing_state.get(session_id, {})
                result_file = state.get('result_file')
            
            # Fallback to session if not in processing_state
            if not result_file:
                result_file = sess.get('instagram_result_file')
            
            if not result_file:
                print(f"DEBUG: No result_file found. Session ID: {session_id}, Session keys: {list(sess.keys())}, State keys: {list(processing_state.keys())}")
                return RedirectResponse('/instagram_aggregator', status_code=303)
            
            file_path = Path(result_file)
            if not file_path.exists():
                print(f"DEBUG: File does not exist: {file_path}")
                return RedirectResponse('/instagram_aggregator', status_code=303)
            
            print(f"DEBUG: Serving file: {file_path} (size: {file_path.stat().st_size} bytes)")
            
            # Create background tasks for cleanup
            background = BackgroundTasks()
            background.add_task(cleanup_temp_files, 
                              upload_path=Path(upload_path) if upload_path else None,
                              result_path=file_path)
            
            # Clear session and shared state AFTER creating response
            if session_id:
                processing_state.pop(session_id, None)
            sess.pop('instagram_result_file', None)
            sess.pop('instagram_upload_path', None)
            sess.pop('instagram_session_id', None)
            
            # Use FileResponse - it handles binary files correctly and avoids FastHTML wrapping
            # FileResponse automatically streams the file and sets proper headers
            response = FileResponse(
                path=str(file_path),
                media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                filename='followers_aggregated.xlsx',
                background=background
            )
            print(f"DEBUG: Returning FileResponse for {file_path}")
            return response
        except Exception as e:
            print(f"ERROR in download_result: {e}")
            import traceback
            traceback.print_exc()
            return RedirectResponse('/instagram_aggregator', status_code=303)
    
    # Return route references for main.py
    return {
        'instagram_aggregator': instagram_aggregator,
        'upload_instagram_data': upload_instagram_data,
        'progress_stream': progress_stream,
        'download_result': download_result,
    }

