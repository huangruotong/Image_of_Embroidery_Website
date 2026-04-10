import shutil
import tempfile
from pathlib import Path

import app as app_module


class TestDbPathResolution:
    def test_resolve_db_path_uses_env_override(self, monkeypatch):
        temp_dir = Path(tempfile.mkdtemp())
        configured_db_path = temp_dir / 'custom-users.db'

        try:
            monkeypatch.setenv('DB_PATH', str(configured_db_path))

            resolved = app_module.resolve_db_path()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        assert resolved == configured_db_path

    def test_resolve_db_path_falls_back_when_preferred_path_is_not_writable(self, monkeypatch):
        temp_dir = Path(tempfile.mkdtemp())

        try:
            preferred_db_path = temp_dir / 'appdata' / 'users.db'
            fallback_db_path = temp_dir / 'workspace' / 'users.db'

            monkeypatch.delenv('DB_PATH', raising=False)
            monkeypatch.setattr(app_module, 'can_write_db_path', lambda _: False)

            resolved = app_module.resolve_db_path(
                preferred_db_path=preferred_db_path,
                fallback_db_path=fallback_db_path,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        assert resolved == fallback_db_path


class TestAuthSignup:
    def test_signup_missing_fields(self, client):
        response = client.post('/api/auth/signup', json={})

        assert response.status_code == 400
        assert 'error' in response.get_json()

    def test_signup_password_too_short(self, client):
        response = client.post(
            '/api/auth/signup',
            json={
                'name': 'Test User',
                'email': 'test@example.com',
                'password': 'short',
            },
        )

        assert response.status_code == 400
        assert 'error' in response.get_json()

    def test_signup_success(self, client):
        response = client.post(
            '/api/auth/signup',
            json={
                'name': 'Test User',
                'email': 'newuser@example.com',
                'password': 'TestPass123',
            },
        )

        data = response.get_json()
        assert response.status_code == 201
        assert 'user' in data
        assert data['user']['email'] == 'newuser@example.com'

    def test_signup_duplicate_email(self, client):
        client.post(
            '/api/auth/signup',
            json={
                'name': 'User One',
                'email': 'duplicate@example.com',
                'password': 'TestPass123',
            },
        )

        response = client.post(
            '/api/auth/signup',
            json={
                'name': 'User Two',
                'email': 'duplicate@example.com',
                'password': 'AnotherPass456',
            },
        )

        assert response.status_code == 409
        assert 'error' in response.get_json()


class TestAuthLogin:
    def test_login_wrong_password(self, client):
        client.post(
            '/api/auth/signup',
            json={
                'name': 'Test User',
                'email': 'testuser@example.com',
                'password': 'CorrectPass123',
            },
        )

        response = client.post(
            '/api/auth/login',
            json={
                'email': 'testuser@example.com',
                'password': 'WrongPassword',
            },
        )

        assert response.status_code == 401

    def test_login_success(self, client):
        client.post(
            '/api/auth/signup',
            json={
                'name': 'Test User',
                'email': 'logintest@example.com',
                'password': 'LoginPass123',
            },
        )

        response = client.post(
            '/api/auth/login',
            json={
                'email': 'logintest@example.com',
                'password': 'LoginPass123',
            },
        )

        data = response.get_json()
        assert response.status_code == 200
        assert 'user' in data
        assert data['user']['email'] == 'logintest@example.com'


class TestAuthSession:
    def test_auth_me_not_authenticated(self, client):
        response = client.get('/api/auth/me')

        data = response.get_json()
        assert response.status_code == 200
        assert data['authenticated'] is False
        assert data['user'] is None

    def test_auth_me_authenticated(self, client):
        client.post(
            '/api/auth/signup',
            json={
                'name': 'Test User',
                'email': 'sessiontest@example.com',
                'password': 'SessionPass123',
            },
        )

        response = client.get('/api/auth/me')

        data = response.get_json()
        assert response.status_code == 200
        assert data['authenticated'] is True
        assert data['user'] is not None
        assert data['user']['email'] == 'sessiontest@example.com'

    def test_logout_clears_session(self, client):
        client.post(
            '/api/auth/signup',
            json={
                'name': 'Test User',
                'email': 'logouttest@example.com',
                'password': 'LogoutPass123',
            },
        )

        response = client.get('/api/auth/me')
        assert response.get_json()['authenticated'] is True

        response = client.post('/api/auth/logout')
        assert response.status_code == 200

        response = client.get('/api/auth/me')
        assert response.get_json()['authenticated'] is False
