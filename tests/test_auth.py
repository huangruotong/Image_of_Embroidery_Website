import pytest  # pytest 测试框架（本文件主要使用其测试发现能力）
import json    # 处理请求/响应中的 JSON 序列化与反序列化


class TestAuthSignup:
    """用户注册接口测试集（/api/auth/signup）。

    覆盖场景：
    - 必填字段缺失
    - 密码长度不合法
    - 注册成功
    - 邮箱重复注册
    """
    
    def test_signup_missing_fields(self, client):
        """当 name/email/password 缺失时，应返回 400。"""
        # 发送空 JSON，请求体缺少所有必填字段
        response = client.post(
            '/api/auth/signup',
            data=json.dumps({}),
            content_type='application/json'
        )
        # 断言状态码为 400 Bad Request
        assert response.status_code == 400
        # 解析响应 JSON
        data = json.loads(response.data)
        # 断言响应中包含错误信息字段
        assert 'error' in data
    
    def test_signup_password_too_short(self, client):
        """当密码长度小于 8 位时，应返回 400。"""
        # 构造合法 name/email，但密码故意设置为过短
        response = client.post(
            '/api/auth/signup',
            data=json.dumps({
                'name': 'Test User',
                'email': 'test@example.com',
                'password': 'short'
            }),
            content_type='application/json'
        )
        # 断言后端执行了密码长度校验
        assert response.status_code == 400
        data = json.loads(response.data)
        # 错误响应应带有 error 字段
        assert 'error' in data
    
    def test_signup_success(self, client):
        """注册成功时应返回 201，并返回 user 信息。"""
        # 发送合法注册信息
        response = client.post(
            '/api/auth/signup',
            data=json.dumps({
                'name': 'Test User',
                'email': 'newuser@example.com',
                'password': 'TestPass123'
            }),
            content_type='application/json'
        )
        # 断言创建成功
        assert response.status_code == 201
        data = json.loads(response.data)
        # 响应中应包含 user 对象
        assert 'user' in data
        # 返回的邮箱应与请求一致（并已标准化）
        assert data['user']['email'] == 'newuser@example.com'
    
    def test_signup_duplicate_email(self, client):
        """同一邮箱重复注册时应返回 409（冲突）。"""
        # 第一次注册：写入数据库成功
        client.post(
            '/api/auth/signup',
            data=json.dumps({
                'name': 'User One',
                'email': 'duplicate@example.com',
                'password': 'TestPass123'
            }),
            content_type='application/json'
        )
        
        # 第二次使用相同邮箱注册：应触发唯一约束冲突
        response = client.post(
            '/api/auth/signup',
            data=json.dumps({
                'name': 'User Two',
                'email': 'duplicate@example.com',
                'password': 'AnotherPass456'
            }),
            content_type='application/json'
        )
        # 断言冲突状态码
        assert response.status_code == 409
        data = json.loads(response.data)
        # 响应中应返回错误信息
        assert 'error' in data


class TestAuthLogin:
    """用户登录接口测试集（/api/auth/login）。

    覆盖场景：
    - 错误密码登录
    - 正确凭证登录
    """
    
    def test_login_wrong_password(self, client):
        """密码错误时登录应返回 401。"""
        # 前置：先创建一个有效账号
        client.post(
            '/api/auth/signup',
            data=json.dumps({
                'name': 'Test User',
                'email': 'testuser@example.com',
                'password': 'CorrectPass123'
            }),
            content_type='application/json'
        )
        
        # 使用错误密码尝试登录
        response = client.post(
            '/api/auth/login',
            data=json.dumps({
                'email': 'testuser@example.com',
                'password': 'WrongPassword'
            }),
            content_type='application/json'
        )
        # 断言认证失败
        assert response.status_code == 401
    
    def test_login_success(self, client):
        """正确邮箱+密码登录时应返回 200，并返回 user 信息。"""
        # 前置：创建账号
        client.post(
            '/api/auth/signup',
            data=json.dumps({
                'name': 'Test User',
                'email': 'logintest@example.com',
                'password': 'LoginPass123'
            }),
            content_type='application/json'
        )
        
        # 使用正确凭证登录
        response = client.post(
            '/api/auth/login',
            data=json.dumps({
                'email': 'logintest@example.com',
                'password': 'LoginPass123'
            }),
            content_type='application/json'
        )
        # 断言登录成功
        assert response.status_code == 200
        data = json.loads(response.data)
        # 返回体应包含 user 对象
        assert 'user' in data
        # 返回的用户邮箱应与登录账号一致
        assert data['user']['email'] == 'logintest@example.com'


class TestAuthSession:
    """会话状态接口测试集（/api/auth/me, /api/auth/logout）。

    覆盖场景：
    - 未登录状态查询
    - 注册后已登录状态查询
    - 登出后会话清空
    """
    
    def test_auth_me_not_authenticated(self, client):
        """未登录时调用 /api/auth/me，应返回 authenticated=false。"""
        # 不做任何登录操作，直接查询当前会话
        response = client.get('/api/auth/me')
        # 查询自身登录状态接口始终返回 200
        assert response.status_code == 200
        data = json.loads(response.data)
        # 断言未认证
        assert data['authenticated'] == False
        # 未登录时 user 应为 null（Python 里对应 None）
        assert data['user'] is None
    
    def test_auth_me_authenticated(self, client):
        """注册后（自动登录）调用 /api/auth/me，应返回 authenticated=true。"""
        # 注册成功后后端会自动写入 session，相当于已登录
        client.post(
            '/api/auth/signup',
            data=json.dumps({
                'name': 'Test User',
                'email': 'sessiontest@example.com',
                'password': 'SessionPass123'
            }),
            content_type='application/json'
        )
        
        # 查询当前登录状态
        response = client.get('/api/auth/me')
        assert response.status_code == 200
        data = json.loads(response.data)
        # 断言已认证且返回了用户信息
        assert data['authenticated'] == True
        assert data['user'] is not None
        assert data['user']['email'] == 'sessiontest@example.com'
    
    def test_logout_clears_session(self, client):
        """登出后应清空会话，再次查询 /api/auth/me 返回未登录。"""
        # 先注册（自动登录）
        client.post(
            '/api/auth/signup',
            data=json.dumps({
                'name': 'Test User',
                'email': 'logouttest@example.com',
                'password': 'LogoutPass123'
            }),
            content_type='application/json'
        )
        
        # 确认当前处于已登录状态
        response = client.get('/api/auth/me')
        data = json.loads(response.data)
        assert data['authenticated'] == True
        
        # 调用登出接口清空 session
        response = client.post('/api/auth/logout')
        assert response.status_code == 200
        
        # 再次查询登录状态，应恢复为未登录
        response = client.get('/api/auth/me')
        data = json.loads(response.data)
        assert data['authenticated'] == False
