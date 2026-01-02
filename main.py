from fasthtml.common import *
from hmac import compare_digest
import os
from pathlib import Path
import sys

# Add projects directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Import project routes
from projects.instagram_aggregator import setup_routes as setup_instagram
from projects.webp_converter import setup_routes as setup_webp

# Simple in-memory user store (replace with database in production)
users = {
    'admin': 'admin123'  # username: password (in production, use hashed passwords)
}

# Authentication Beforeware
def before(req, sess):
    # `auth` key in the request scope is automatically provided to any handler which requests it
    auth = req.scope['auth'] = sess.get('auth', None)
    if not auth:
        return RedirectResponse('/login', status_code=303)

# Skip authentication for public routes
beforeware = Beforeware(
    before,
    skip=[
        r'/favicon\.ico',
        r'/static/.*',
        r'.*\.css',
        r'.*\.js',
        '/login',
        '/send_login',
        '/progress_stream',  # SSE endpoint needs session but not auth redirect
        '/webp_progress_stream',  # WebP converter SSE endpoint
        '/webp_thumbnail',  # Thumbnail images (session UUID provides security)
        '/webp_fullsize',  # Full-size images for crop editor
    ]
)

# Link to external CSS file for cleaner code organization
global_css = Link(rel='stylesheet', href='/static/css/style.css', type='text/css')

# Tailwind CSS v4.1.2 Play CDN - allows inline utility classes without build step
# Latest stable version as of 2025
# Good for development and simple production. For large-scale production, consider Tailwind CLI build.
tailwind_script = Script(
    src="https://cdn.tailwindcss.com",
    type="text/javascript"
)

# HTMX SSE extension for progress updates
sse_script = Script(src="https://unpkg.com/htmx-ext-sse@2.2.3/sse.js")

# Cropper.js for image cropping (v1.6.2 - stable, well-documented)
cropper_css = Link(rel="stylesheet", href="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.6.2/cropper.min.css")
cropper_js = Script(src="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.6.2/cropper.min.js")

# Minimal Tailwind config - just for background color utilities
# (Text colors are in style.css instead for cleaner code)
tailwind_config = Script("""
    tailwind.config = {
        theme: {
            extend: {
                colors: {
                    'dark': {
                        DEFAULT: '#191919',
                        'elevated': '#232323',
                        'hover': '#2a2a2a',
                    }
                }
            }
        }
    }
""")

# Create FastHTML app with Beforeware, secret key, and Tailwind CSS
# pico=False disables Pico CSS so we can use Tailwind instead
# live reload: Only enable for development (causes WebSocket errors over HTTPS)
# For development: access via http://localhost:5001 to use live reload
secret_key = os.getenv('SECRET_KEY', 'change-me-in-production-use-env-variable')
enable_live_reload = os.getenv('ENABLE_LIVE_RELOAD', 'false').lower() == 'true'
app, rt = fast_app(
    before=beforeware,
    secret_key=secret_key,
    pico=False,  # Disable Pico CSS
    live=enable_live_reload,  # Enable live reload only if ENABLE_LIVE_RELOAD=true in .env
    hdrs=(global_css, tailwind_script, tailwind_config, sse_script, cropper_css, cropper_js)  # Add global CSS, Tailwind, SSE, and Cropper.js
)

# Mount static files directory for serving icons, CSS, JS, etc.
from starlette.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="static"), name="static")

# Login page
@rt
def login():
    frm = Div(cls="p-8 rounded-2xl space-y-6", style="background-color: #232323; border: 1px solid #3a3a3a;")(
        # Header
        Div(cls="text-center space-y-2 mb-8")(
            H1("Welcome back", cls="text-4xl font-semibold text-primary"),
            P("Sign in to your account", cls="text-secondary text-base")
        ),

        # Form
        Form(action=send_login, method='post', cls="space-y-4")(
            # Username field
            Div()(
                Label("Username", fr="username", cls="block text-sm font-medium mb-2 text-primary"),
                Input(
                    id='username',
                    name='username',
                    type='text',
                    placeholder='Enter your username',
                    required=True,
                    cls="w-full px-4 py-3 rounded-lg transition-all duration-200 outline-none focus:bg-[#3a3a3a] hover:bg-[#3a3a3a] focus:ring-2 focus:ring-white/20",
                    style="background-color: #2a2a2a; border: 1px solid #3a3a3a; color: #e3e3e3;"
                )
            ),

            # Password field with eye icon
            Div()(
                Label("Password", fr="password", cls="block text-sm font-medium mb-2 text-primary"),
                Div(cls="relative")(
                    Input(
                        id='password',
                        name='password',
                        type='password',
                        placeholder='Enter your password',
                        required=True,
                        cls="w-full px-4 py-3 pr-12 rounded-lg transition-all duration-200 outline-none focus:bg-[#3a3a3a] hover:bg-[#3a3a3a] focus:ring-2 focus:ring-white/20",
                        style="background-color: #2a2a2a; border: 1px solid #3a3a3a; color: #e3e3e3;"
                    ),
                    Button(
                        Img(
                            src="/static/icons/eye.svg",
                            alt="Toggle password visibility",
                            id="eye-icon",
                            cls="w-5 h-5",
                            style="filter: brightness(0) invert(1) opacity(0.6);"
                        ),
                        type="button",
                        onclick="""
                            const input = this.previousElementSibling;
                            const icon = this.querySelector('img');
                            if (input.type === 'password') {
                                input.type = 'text';
                                icon.src = '/static/icons/eye-off.svg';
                            } else {
                                input.type = 'password';
                                icon.src = '/static/icons/eye.svg';
                            }
                        """,
                        cls="absolute right-3 top-1/2 transform -translate-y-1/2 p-1 rounded transition-all duration-200 hover:bg-white/10",
                        tabindex="-1"
                    )
                )
            ),

            # Forgot password link
            Div(cls="text-right")(
                A("Forgot password?", href="#", cls="text-sm text-secondary hover:text-primary transition-colors")
            ),

            # Submit button
            Button(
                'Sign In',
                type='submit',
                cls="w-full px-6 py-4 rounded-xl font-medium transition-all duration-200 hover:bg-[#3a3a3a] hover:scale-[1.02] active:scale-[0.98] active:bg-[#2a2a2a] focus:bg-[#3a3a3a] focus:ring-2 focus:ring-white/20",
                style="background-color: #2a2a2a; border: 1px solid #3a3a3a; color: #e3e3e3;"
            )
        )
    )

    # Return just Title + centered form
    return (
        Title("Login"),
        Div(Div(frm, cls="w-full max-w-md"), cls="min-h-screen flex items-center justify-center px-4")
    )

# Login handler
@rt
def send_login(username: str, password: str, sess):
    if not username or not password:
        return RedirectResponse('/login', status_code=303)

    # Check credentials (in production, use proper password hashing)
    if username in users and compare_digest(users[username].encode("utf-8"), password.encode("utf-8")):
        sess['auth'] = username
        return RedirectResponse('/', status_code=303)

    return RedirectResponse('/login', status_code=303)

# Logout handler
@rt
def logout(sess):
    if 'auth' in sess:
        del sess['auth']
    return RedirectResponse('/login', status_code=303)

# Setup project routes
instagram_routes = setup_instagram(rt)
webp_routes = setup_webp(rt)

# Home page with project links
@rt
def index(auth):
    # Project definitions with descriptions and icons
    projects = [
        {
            'name': 'Instagram Aggregator',
            'description': 'Aggregate and analyze Instagram follower data for marketing insights',
            'route': instagram_routes['instagram_aggregator'],
            'icon': '📊',
            'status': 'active'
        },
        {
            'name': 'WebP Converter',
            'description': 'Convert images to optimized WebP format for web and mobile',
            'route': webp_routes['webp_converter'],
            'icon': '🖼️',
            'status': 'active'
        },
    ]

    # Header with user info and logout
    header = Div(
        Div(
            Span("⬡", cls="text-2xl mr-2"),
            Span("Dashboard", cls="text-lg font-medium text-primary"),
            cls="flex items-center"
        ),
        Div(
            Div(
                Span("👤", cls="mr-2 text-sm"),
                Span(auth, cls="text-primary text-sm"),
                cls="flex items-center px-4 py-2 rounded-lg",
                style="background-color: #232323; border: 1px solid #3a3a3a;"
            ),
            A(
                'Sign out',
                href=logout,
                cls="px-4 py-2 rounded-lg text-sm text-secondary hover:text-primary transition-all duration-200 hover:bg-[#2a2a2a]",
                style="border: 1px solid #3a3a3a;"
            ),
            cls="flex items-center gap-3"
        ),
        cls="flex justify-between items-center mb-10 pb-6",
        style="border-bottom: 1px solid #3a3a3a;"
    )

    # Project cards in grid
    project_cards = [
        Div(
            A(
                Div(
                    Span(p['icon'], cls="text-3xl mb-3 block"),
                    H3(p['name'], cls="text-lg font-medium text-primary mb-2"),
                    P(p['description'], cls="text-sm text-secondary leading-relaxed"),
                    cls="p-6"
                ),
                href=p['route'],
                hx_get=p['route'],
                hx_target='#content',
                hx_swap='innerHTML',
                cls="block h-full"
            ),
            cls="rounded-xl transition-all duration-200 hover:scale-[1.02] cursor-pointer",
            style="background-color: #232323; border: 1px solid #3a3a3a;"
        )
        for p in projects
    ]

    # Welcome message for empty content area
    empty_state = Div(
        Div(
            Span("👆", cls="text-4xl mb-4 block"),
            P("Select a project above to get started", cls="text-secondary"),
            cls="text-center py-8"
        ),
        id='content',
        cls="rounded-xl mt-8",
        style="background-color: #232323; border: 1px solid #3a3a3a;"
    )

    content = Div(
        header,
        H2("Projects", cls="text-2xl font-semibold mb-6 text-primary"),
        Div(*project_cards, cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"),
        empty_state,
        cls="max-w-5xl mx-auto px-6 py-8"
    )

    # Return Title (browser tab) + centered content wrapper
    return (
        Title("Dashboard"),
        Div(content, cls="min-h-screen")
    )

# Run the app with FastHTML's recommended approach
# live=True in fast_app() enables auto browser refresh + serve() reload=True (default) handles server restart
# Note: In Docker, file watchers may be unreliable. Use ./reload.sh if changes aren't detected
# Watch projects directory for live reload
serve(reload_includes=['projects/**/*.py'])
