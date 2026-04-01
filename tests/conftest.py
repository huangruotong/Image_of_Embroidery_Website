import pytest    # pytest 测试框架，用于 fixture 和测试组织
import tempfile  # 创建临时文件/临时数据库路径，确保测试隔离
import os        # 文件删除与路径存在性检查
import sys       # 修改 Python 模块搜索路径（sys.path）
from pathlib import Path  # 跨平台路径拼接

# 将项目根目录加入模块搜索路径，确保 tests/ 下可以 import app
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app, DB_PATH, init_db


@pytest.fixture
def temp_db():
    """为每个测试用例创建独立的临时 SQLite 数据库。

    作用：
    - 避免测试污染真实 users.db
    - 保证每个测试之间数据库状态互不影响
    - 测试结束后自动清理临时文件
    """
    # mkstemp 返回 (文件描述符, 路径)，suffix='.db' 保持 SQLite 文件后缀
    fd, temp_db_path = tempfile.mkstemp(suffix='.db')
    # 关闭底层文件描述符，后续由 sqlite3 按路径自行管理
    os.close(fd)
    
    # 暂存原始 DB_PATH，便于测试结束后恢复
    original_db_path = app.config.get('DB_PATH')
    # 将 Flask 配置中的 DB_PATH 指向临时数据库
    app.config['DB_PATH'] = temp_db_path
    
    # 关键：app.py 内部实际使用模块级变量 DB_PATH，因此需要 monkey-patch
    import app as app_module
    app_module.DB_PATH = temp_db_path
    
    # 将临时数据库路径暴露给依赖该 fixture 的测试
    yield temp_db_path
    
    # 测试结束后的清理逻辑：删除临时数据库并恢复原配置
    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)
    app.config['DB_PATH'] = original_db_path


@pytest.fixture
def client(temp_db):
    """创建 Flask 测试客户端，并绑定到隔离的临时数据库。"""
    # 启用 Flask TESTING 模式：异常直接冒泡，便于 pytest 捕获
    app.config['TESTING'] = True
    
    # 使用临时 DB_PATH 重新初始化表结构（创建 users 表）
    init_db()
    
    # 通过上下文管理器创建测试客户端，自动管理请求上下文生命周期
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def sample_image():
    """提供示例测试图片的相对路径（用于需要图片输入的测试）。"""
    return 'static/images/home_photo.jpg'


def get_test_image_path():
    """获取示例测试图片的绝对路径。

    说明：
    - 从项目根目录拼接 static/images/home_photo.jpg
    - 绝对路径可避免测试运行目录变化导致的路径解析错误
    """
    current_dir = Path(__file__).parent.parent
    return str(current_dir / 'static' / 'images' / 'home_photo.jpg')
