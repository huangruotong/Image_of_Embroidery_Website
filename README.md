# Embroidery Design

A Flask app for turning images into embroidery patterns.

You can upload an image, choose a mode to generate embroidery files.

## Features

- Upload `JPG`, `PNG`, or `BMP` images up to 5 MB
- Preview the result in the browser before exporting
- Three processing modes: 'line', 'canny', 'raster'
- Adjust width, stitch length, contrast, and details settings
- Export machine embroidery formats: `.pes`, `.dst`, `.jef`, `.exp`
- Download the current preview as `.png`
- Store users in SQLite with hashed passwords

## Usage
1.Upload a JPG, PNG, or BMP image
2.Choose a mode: line, canny, or raster
3.Adjust detail settings for the image
4.View the preview results in the browser
5.Save the current preview as .png
6.Export the design as an embroidery file

## Requirements

- Python 3.10+

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

Open http://127.0.0.1:5000 in your browser.

## Tests

The project includes automated tests for the main backend flows and user security.

Run the full test suite:

```powershell
pytest
```

Run a specific test module:

```powershell
pytest tests/test_auth.py -v
pytest tests/test_export.py -v
```

Run tests with coverage:

```powershell
pytest --cov=. --cov-report=html
```

The current tests cover:

- authentication flows
- database path resolution
- preview and export behavior
- parameter boundary handling
- hoop-limit checks
- preview rendering behavior

## API Endpoints

Authentication:

- `POST /api/auth/signup`: create an account with `name`, `email`, and `password`
- `POST /api/auth/login`: log in with `email` and `password`
- `POST /api/auth/logout`: log out the current session
- `GET /api/auth/me`: get the current session status

Workspace:

- `POST /api/preview`: generate a preview for the uploaded image and current settings
- `POST /api/export`: export the uploaded image as an embroidery file

## Project Structure

- `app.py`: Flask app entry, routes, auth, preview, and export logic
- `embroidery.py`: image processing and embroidery pattern generation
- `templates/`: page templates for home, auth, guide, and workspace views
- `static/js/`: auth and workspace scripts
- `static/css/`: styles 
- `static/images/`: UI images and sample assets
- `tests/`: automated tests
