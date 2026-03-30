import pytest
import tempfile
import os
import sys
from pathlib import Path

# Add parent directory to path to import app
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app, DB_PATH, init_db


@pytest.fixture
def temp_db():
    """Create a temporary database for each test."""
    fd, temp_db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    # Temporarily replace DB_PATH
    original_db_path = app.config.get('DB_PATH')
    app.config['DB_PATH'] = temp_db_path
    
    # Monkey-patch the module-level DB_PATH
    import app as app_module
    app_module.DB_PATH = temp_db_path
    
    yield temp_db_path
    
    # Cleanup
    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)
    app.config['DB_PATH'] = original_db_path


@pytest.fixture
def client(temp_db):
    """Create a test client with isolated database."""
    app.config['TESTING'] = True
    
    # Re-initialize database with temp path
    init_db()
    
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def sample_image():
    """Provide path to sample test image."""
    return 'static/images/home_photo.jpg'


def get_test_image_path():
    """Get absolute path to test image."""
    current_dir = Path(__file__).parent.parent
    return str(current_dir / 'static' / 'images' / 'home_photo.jpg')
