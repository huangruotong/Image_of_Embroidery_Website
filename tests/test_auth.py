import pytest
import json


class TestAuthSignup:
    """Test suite for user registration."""
    
    def test_signup_missing_fields(self, client):
        """Test signup with missing required fields returns 400."""
        response = client.post(
            '/api/auth/signup',
            data=json.dumps({}),
            content_type='application/json'
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_signup_password_too_short(self, client):
        """Test signup with password < 8 characters returns 400."""
        response = client.post(
            '/api/auth/signup',
            data=json.dumps({
                'name': 'Test User',
                'email': 'test@example.com',
                'password': 'short'
            }),
            content_type='application/json'
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_signup_success(self, client):
        """Test successful signup returns 201 and sets session."""
        response = client.post(
            '/api/auth/signup',
            data=json.dumps({
                'name': 'Test User',
                'email': 'newuser@example.com',
                'password': 'TestPass123'
            }),
            content_type='application/json'
        )
        assert response.status_code == 201
        data = json.loads(response.data)
        assert 'user' in data
        assert data['user']['email'] == 'newuser@example.com'
    
    def test_signup_duplicate_email(self, client):
        """Test signup with duplicate email returns 409."""
        # First signup
        client.post(
            '/api/auth/signup',
            data=json.dumps({
                'name': 'User One',
                'email': 'duplicate@example.com',
                'password': 'TestPass123'
            }),
            content_type='application/json'
        )
        
        # Duplicate attempt
        response = client.post(
            '/api/auth/signup',
            data=json.dumps({
                'name': 'User Two',
                'email': 'duplicate@example.com',
                'password': 'AnotherPass456'
            }),
            content_type='application/json'
        )
        assert response.status_code == 409
        data = json.loads(response.data)
        assert 'error' in data


class TestAuthLogin:
    """Test suite for user login."""
    
    def test_login_wrong_password(self, client):
        """Test login with wrong password returns 401."""
        # First create an account
        client.post(
            '/api/auth/signup',
            data=json.dumps({
                'name': 'Test User',
                'email': 'testuser@example.com',
                'password': 'CorrectPass123'
            }),
            content_type='application/json'
        )
        
        # Try to login with wrong password
        response = client.post(
            '/api/auth/login',
            data=json.dumps({
                'email': 'testuser@example.com',
                'password': 'WrongPassword'
            }),
            content_type='application/json'
        )
        assert response.status_code == 401
    
    def test_login_success(self, client):
        """Test successful login returns 200 and sets session."""
        # Create account
        client.post(
            '/api/auth/signup',
            data=json.dumps({
                'name': 'Test User',
                'email': 'logintest@example.com',
                'password': 'LoginPass123'
            }),
            content_type='application/json'
        )
        
        # Login
        response = client.post(
            '/api/auth/login',
            data=json.dumps({
                'email': 'logintest@example.com',
                'password': 'LoginPass123'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'user' in data
        assert data['user']['email'] == 'logintest@example.com'


class TestAuthSession:
    """Test suite for session management."""
    
    def test_auth_me_not_authenticated(self, client):
        """Test auth/me returns authenticated=false when not logged in."""
        response = client.get('/api/auth/me')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['authenticated'] == False
        assert data['user'] is None
    
    def test_auth_me_authenticated(self, client):
        """Test auth/me returns authenticated=true after signup."""
        client.post(
            '/api/auth/signup',
            data=json.dumps({
                'name': 'Test User',
                'email': 'sessiontest@example.com',
                'password': 'SessionPass123'
            }),
            content_type='application/json'
        )
        
        response = client.get('/api/auth/me')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['authenticated'] == True
        assert data['user'] is not None
        assert data['user']['email'] == 'sessiontest@example.com'
    
    def test_logout_clears_session(self, client):
        """Test logout clears session and auth/me returns false."""
        # Signup
        client.post(
            '/api/auth/signup',
            data=json.dumps({
                'name': 'Test User',
                'email': 'logouttest@example.com',
                'password': 'LogoutPass123'
            }),
            content_type='application/json'
        )
        
        # Verify authenticated
        response = client.get('/api/auth/me')
        data = json.loads(response.data)
        assert data['authenticated'] == True
        
        # Logout
        response = client.post('/api/auth/logout')
        assert response.status_code == 200
        
        # Verify session cleared
        response = client.get('/api/auth/me')
        data = json.loads(response.data)
        assert data['authenticated'] == False
