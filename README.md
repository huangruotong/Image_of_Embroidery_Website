# Image of Embroidery Website

Upload an image, preview processing effects in the workspace, and export machine-ready embroidery files.

## Features

- Three processing modes: line, canny, raster
- Real-time preview in browser
- Export formats: .pes, .dst, .jef, .exp
- Backend authentication (sign up, login, logout, session check)
- SQLite user storage with password hashing...

## Requirements

- Python 3.10+

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

Open http://127.0.0.1:5000 in your browser.

## Authentication API

- `POST /api/auth/signup`: Create account with `name`, `email`, `password`
- `POST /api/auth/login`: Login with `email`, `password`
- `POST /api/auth/logout`: Logout current session
- `GET /api/auth/me`: Get current session status

## Notes

- A local `users.db` file is created automatically on first run.
- For production, set `SECRET_KEY` as an environment variable before startup.

## Project Structure

- app.py: Flask routes and export API
- users.db: SQLite database for user accounts (auto generated)
- embroidery.py: image to embroidery conversion logic
- templates/: page templates
- static/js/: auth and workspace scripts
- static/images/: UI images
