import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app, init_db


@pytest.fixture
def temp_db():
    fd, temp_db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    original_db_path = app.config.get('DB_PATH')
    original_initialized_for = app.config.get('DB_INITIALIZED_FOR')

    app.config['DB_PATH'] = temp_db_path
    app.config['DB_INITIALIZED_FOR'] = None

    yield temp_db_path

    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)

    app.config['DB_PATH'] = original_db_path
    app.config['DB_INITIALIZED_FOR'] = original_initialized_for


@pytest.fixture
def client(temp_db):
    app.config['TESTING'] = True
    init_db()

    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def authenticated_client(client):
    response = client.post(
        '/api/auth/signup',
        data=json.dumps({
            'name': 'Export Tester',
            'email': 'exporter@example.com',
            'password': 'ExportPass123'
        }),
        content_type='application/json'
    )
    assert response.status_code == 201
    return client
