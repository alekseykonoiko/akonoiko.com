# Project Context for Claude Code

## Project Overview
Personal website at akonoiko.com built with FastHTML, featuring:
- Authentication system with login/logout
- Project management interface
- Notion/Apple-like dark theme without blue hue
- Tailwind CSS for styling
- Direct Python deployment with Caddy reverse proxy

## Tech Stack
- **Framework**: FastHTML (Python-based hypermedia framework)
- **Styling**: Tailwind CSS v4.1.2 Play CDN + Custom CSS
- **Server**: Uvicorn (ASGI) with live reload
- **Reverse Proxy**: Caddy (automatic HTTPS)
- **Deployment**: Direct Python execution in venv
- **Authentication**: Session-based with Beforeware

## Project Structure
```
/root/akonoiko.com/
├── main.py                 # Main FastHTML application
├── requirements.txt        # Python dependencies
├── venv/                  # Python virtual environment
├── Caddyfile             # Reverse proxy config
├── .env                  # Environment variables (SECRET_KEY)
├── static/               # Static assets
│   └── icons/           # SVG icons (eye.svg, eye-off.svg)
└── projects/             # Project-specific code
    └── instagram_aggregator/
```

## Key Design Decisions

### Dark Theme
- **Base color**: `#191919` (warm neutral, no blue hue)
- **Elevated surfaces**: `#232323`
- **Input/Button background**: `#2a2a2a`
- **Hover states**: `#3a3a3a`
- **Borders**: `#3a3a3a`
- **Text primary**: `#e3e3e3`
- **Text secondary**: `#9b9b9b`
- **Text muted**: `#6b6b6b`

Inspired by Notion and Apple's dark modes - warm neutrals instead of cool grays with blue undertones.

### Styling Approach
1. **Pico CSS disabled** with `pico=False` to avoid conflicts
2. **Global CSS** in a `<style>` tag for html/body base styles
3. **Tailwind CSS** via Play CDN for utility classes
4. **Custom Tailwind config** to define dark theme colors
5. **Inline utility classes** for component styling

### Authentication
- Session-based using FastHTML's built-in session middleware
- Beforeware checks authentication before route handlers
- Skip patterns for public routes (login, static assets)
- Simple user store (should be replaced with database in production)

## Important Files

### main.py
Main application file containing:
- Global CSS with warm neutral dark theme
- Tailwind configuration
- Authentication Beforeware
- Route handlers for login, home, projects
- Session management
- Static file mounting for icons and assets

### .env
Contains `SECRET_KEY` for session encryption (generated during setup)

### Caddyfile
Caddy reverse proxy configuration:
- Proxies `akonoiko.com` to `localhost:5001`
- Automatic SSL certificate management via Let's Encrypt
- Automatic HTTP to HTTPS redirects

## Development Workflow

### Running the Application
```bash
# Activate virtual environment and run
source venv/bin/activate
python main.py

# Or run directly
venv/bin/python main.py
```

### Hot Reload
FastHTML's built-in hot reload is enabled with:
- `live=True` in `fast_app()` - enables browser auto-refresh
- `serve()` with default `reload=True` - handles server restart on file changes

When you save changes to `main.py`, WatchFiles automatically detects changes and reloads the server. The browser will refresh automatically.

### Background Process
To run the app in background:
```bash
# Start in background
nohup venv/bin/python main.py > app.log 2>&1 &

# Check if running
ps aux | grep main.py

# Kill if needed
pkill -f main.py
```

### CSS Updates
All styling is in `main.py`:
1. Global CSS in the `global_css` Style tag
2. Tailwind config in the `tailwind_config` Script tag
3. Component classes use both custom CSS classes and Tailwind utilities

### Static Files
Static files are served from `/static` directory:
- Icons: `/static/icons/eye.svg`, `/static/icons/eye-off.svg`
- Mounted via Starlette's `StaticFiles` middleware

## Common Tasks

### Add New Route
```python
@rt
def new_route(auth):
    return Titled(
        "Page Title",
        Div(
            H1("Heading", cls="text-3xl font-semibold mb-3 text-primary"),
            P("Content", cls="text-base text-primary mb-2"),
            cls="max-w-3xl mx-auto px-6 py-12"
        )
    )
```

### Update Color Scheme
Edit the custom CSS variables in `global_css` and `tailwind_config` in main.py

### Add New User
Update the `users` dict in main.py (temporary - replace with database)

### Add Static Assets
Place files in `/static` directory:
```bash
mkdir -p static/images
cp myimage.png static/images/
# Access at /static/images/myimage.png
```

### Install New Dependencies
```bash
source venv/bin/activate
pip install package-name
pip freeze > requirements.txt
```

## Documentation References

### FastHTML Documentation
- **Local context file**: `llms-ctx.txt` - comprehensive FastHTML reference including:
  - FastHTML concise guide with API overview
  - HTMX reference with all attributes, events, and headers
  - Starlette quick guide for ASGI features
  - Complete API list for fasthtml and monsterui modules
- **Official website**: https://www.fastht.ml/
- **API docs**: https://www.fastht.ml/docs/api/
- **Tutorials**: https://www.fastht.ml/tutorials/
- **Examples**: https://github.com/AnswerDotAI/fasthtml-example
- **Discord community**: https://discord.gg/qcXvcxMhdP

### Other Documentation
- Tailwind CSS: https://tailwindcss.com/docs
- Caddy: https://caddyserver.com/docs/
- HTMX: https://htmx.org/docs/

## Production Setup
- Python app runs on port 5001
- Caddy handles HTTPS and proxies to localhost:5001
- Use a process manager like systemd or supervisor for production
- Set `SECRET_KEY` environment variable from `.env` file
- Consider disabling `live=True` in production

## Notes
- The `projects/` folder is for project-specific modules (currently ignored in main app)
- All routes require authentication except login page
- Dark theme covers entire viewport with no blue hue
- Uses system font stack for native look and feel
- Hot reload works reliably when running Python directly (no Docker)
