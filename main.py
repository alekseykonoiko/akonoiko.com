from fasthtml.common import *
from hmac import compare_digest
import os

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
        '/send_login'
    ]
)

# Global CSS for Notion/Apple-like dark theme without blue hue
# Using warm neutral colors instead of cool grays
global_css = Style("""
    * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }

    html, body {
        width: 100%;
        height: 100%;
        background-color: #191919;
        color: #e3e3e3;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }

    /* Remove blue hue - use warm neutrals */
    .bg-dark { background-color: #191919; }
    .bg-dark-elevated { background-color: #232323; }
    .bg-dark-hover { background-color: #2a2a2a; }
    .border-dark { border-color: #3a3a3a; }
    .text-primary { color: #e3e3e3; }
    .text-secondary { color: #9b9b9b; }
    .text-muted { color: #6b6b6b; }

    /* Remove default link underlines */
    a { text-decoration: none; }

    /* Smooth transitions */
    * { transition: background-color 150ms ease, border-color 150ms ease, color 150ms ease; }
""")

# Tailwind CSS v4.1.2 Play CDN - allows inline utility classes without build step
# Latest stable version as of 2025
tailwind_script = Script(
    src="https://cdn.tailwindcss.com",
    type="text/javascript"
)

# Tailwind config to use neutral colors without blue hue
tailwind_config = Script("""
    tailwind.config = {
        theme: {
            extend: {
                colors: {
                    'dark': {
                        DEFAULT: '#191919',
                        'elevated': '#232323',
                        'hover': '#2a2a2a',
                        'border': '#3a3a3a',
                    },
                    'text': {
                        'primary': '#e3e3e3',
                        'secondary': '#9b9b9b',
                        'muted': '#6b6b6b',
                    }
                }
            }
        }
    }
""")

# Create FastHTML app with Beforeware, secret key, and Tailwind CSS
# pico=False disables Pico CSS so we can use Tailwind instead
# live=True enables FastHTML's live reload (auto-refresh browser on code changes)
secret_key = os.getenv('SECRET_KEY', 'change-me-in-production-use-env-variable')
app, rt = fast_app(
    before=beforeware,
    secret_key=secret_key,
    pico=False,  # Disable Pico CSS
    live=True,   # Enable live reload (development only)
    hdrs=(global_css, tailwind_script, tailwind_config)  # Add global CSS and Tailwind
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
            # Email field
            Div()(
                Label("Email", fr="username", cls="block text-sm font-medium mb-2 text-primary"),
                Input(
                    id='username',
                    name='username',
                    type='email',
                    placeholder='Enter your email',
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
def send_login(username: str, pwd: str, sess):
    if not username or not pwd:
        return RedirectResponse('/login', status_code=303)
    
    # Check credentials (in production, use proper password hashing)
    if username in users and compare_digest(users[username].encode("utf-8"), pwd.encode("utf-8")):
        sess['auth'] = username
        return RedirectResponse('/', status_code=303)
    
    return RedirectResponse('/login', status_code=303)

# Logout handler
@rt
def logout(sess):
    if 'auth' in sess:
        del sess['auth']
    return RedirectResponse('/login', status_code=303)

# Home page with project links
@rt
def index(auth):
    title = f"Welcome, {auth}!"
    projects = [
        ('Project 1', project1),
        ('Project 2', project2),
    ]

    project_links = [
        Div(
            A(
                name,
                href=route_fn,
                hx_get=route_fn,
                hx_target='#content',
                hx_swap='innerHTML',
                cls="text-base font-medium text-primary hover:text-white"
            ),
            cls="p-4 border border-dark-border rounded hover:bg-dark-hover transition-all duration-150 cursor-pointer"
        )
        for name, route_fn in projects
    ]

    content = Div(
        H1(title, cls="text-3xl font-semibold mb-2 text-primary"),
        P('Select a project to view:', cls="text-secondary mb-8 text-sm"),
        Div(*project_links, cls="flex flex-col gap-2 mb-8"),
        Div(id='content', cls="min-h-[200px] p-6 border border-dark-border rounded bg-dark-elevated"),
        P(
            A('Logout', href=logout, cls="text-secondary hover:text-primary"),
            cls="mt-8 text-right"
        ),
        cls="max-w-3xl mx-auto px-6 py-12"
    )

    return Titled("Home", content)

# Project 1 route
@rt
def project1(auth):
    return Titled(
        "Project 1",
        Div(
            H1("Project 1", cls="text-3xl font-semibold mb-3 text-primary"),
            P(f"Welcome to Project 1, {auth}!", cls="text-base text-primary mb-2"),
            P("This is a protected project route.", cls="text-sm text-secondary mb-8"),
            A(
                "Back to Home",
                href=index,
                cls="inline-block bg-white text-black px-4 py-2 rounded hover:bg-gray-100 transition-colors text-sm font-medium"
            ),
            cls="max-w-3xl mx-auto px-6 py-12"
        )
    )

# Project 2 route
@rt
def project2(auth):
    return Titled(
        "Project 2",
        Div(
            H1("Project 2", cls="text-3xl font-semibold mb-3 text-primary"),
            P(f"Welcome to Project 2, {auth}!", cls="text-base text-primary mb-2"),
            P("This is another protected project route.", cls="text-sm text-secondary mb-8"),
            A(
                "Back to Home",
                href=index,
                cls="inline-block bg-white text-black px-4 py-2 rounded hover:bg-gray-100 transition-colors text-sm font-medium"
            ),
            cls="max-w-3xl mx-auto px-6 py-12"
        )
    )

# Run the app with FastHTML's recommended approach
# live=True in fast_app() enables auto browser refresh + serve() reload=True (default) handles server restart
# Note: In Docker, file watchers may be unreliable. Use ./reload.sh if changes aren't detected
serve()
