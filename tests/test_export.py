import pytest  # pytest 测试框架（本文件主要使用其测试发现能力）
import json    # 解析接口返回的 JSON 数据
import os      # 处理跨平台路径拼接
from pathlib import Path  # 提供稳定的路径定位能力


def get_test_image_path():
    """返回测试图片的绝对路径。

    使用项目根目录拼接 static/images/home_photo.jpg，
    避免因 pytest 运行目录不同导致相对路径失效。
    """
    current_dir = Path(__file__).parent.parent
    return os.path.join(str(current_dir), 'static', 'images', 'home_photo.jpg')


class TestExportValidation:
    """导出接口参数校验测试集（/api/export）。

    覆盖场景：
    - 缺少 image
    - 缺少 format
    """
    
    def test_export_missing_image(self, client):
        """未上传 image 时应返回 400。"""
        # 仅传 format/mode，不传 image 文件
        response = client.post(
            '/api/export',
            data={'format': '.dst', 'mode': 'line'}
        )
        # 参数不完整，应返回 Bad Request
        assert response.status_code == 400
        # 响应体应包含错误字段
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_export_missing_format(self, client):
        """上传了 image 但缺少 format 时应返回 400。"""
        # 准备测试图片
        img_path = get_test_image_path()
        with open(img_path, 'rb') as f:
            response = client.post(
                '/api/export',
                data={
                    'image': (f, 'test.jpg'),
                    'mode': 'line'
                }
            )
        # 缺少 format（且格式校验失败）应返回 400
        assert response.status_code == 400


class TestExportSuccess:
    """导出接口成功路径测试集。

    覆盖三种模式：line / canny / raster。
    每个测试都验证：
    - 状态码为 200
    - 返回文件非空（response.data 长度 > 0）
    """
    
    def test_export_line_mode_success(self, client):
        """line 模式导出成功：应返回 200 且文件内容非空。"""
        img_path = get_test_image_path()
        with open(img_path, 'rb') as f:
            response = client.post(
                '/api/export',
                data={
                    'image': (f, 'test.jpg'),
                    'format': '.dst',
                    'mode': 'line',
                    'line_precision': 50,
                    'target_width_mm': 100,
                    'min_stitch_len_mm': 0.8,
                    'max_stitch_len_mm': 6.0
                }
            )
        # 导出成功
        assert response.status_code == 200
        # 返回的是二进制刺绣文件，长度应大于 0
        assert len(response.data) > 0
    
    def test_export_canny_mode_success(self, client):
        """canny 模式导出成功：应返回 200 且文件内容非空。"""
        img_path = get_test_image_path()
        with open(img_path, 'rb') as f:
            response = client.post(
                '/api/export',
                data={
                    'image': (f, 'test.jpg'),
                    'format': '.pes',
                    'mode': 'canny',
                    'canny_low': 50,
                    'canny_high': 150,
                    'target_width_mm': 100,
                    'min_stitch_len_mm': 0.8,
                    'max_stitch_len_mm': 6.0
                }
            )
        # 导出成功
        assert response.status_code == 200
        # 返回文件不应为空
        assert len(response.data) > 0
    
    def test_export_raster_mode_success(self, client):
        """raster 模式导出成功：应返回 200 且文件内容非空。"""
        img_path = get_test_image_path()
        with open(img_path, 'rb') as f:
            response = client.post(
                '/api/export',
                data={
                    'image': (f, 'test.jpg'),
                    'format': '.jef',
                    'mode': 'raster',
                    'raster_row_spacing': 4,
                    'raster_min_stitch': 2,
                    'raster_max_stitch': 12,
                    'raster_white_threshold': 220,
                    'raster_contrast_boost': 1.8,
                    'target_width_mm': 100,
                    'min_stitch_len_mm': 0.8,
                    'max_stitch_len_mm': 6.0
                }
            )
        # 导出成功
        assert response.status_code == 200
        # 返回文件不应为空
        assert len(response.data) > 0


class TestExportBoundary:
    """导出接口边界值/极值参数测试集。

    目标：验证接口对参数极值处理稳定，不应崩溃，并且仍可导出文件。
    """
    
    def test_export_line_max_precision(self, client):
        """line 模式精度上限 100：应可正常导出。"""
        img_path = get_test_image_path()
        with open(img_path, 'rb') as f:
            response = client.post(
                '/api/export',
                data={
                    'image': (f, 'test.jpg'),
                    'format': '.dst',
                    'mode': 'line',
                    'line_precision': 100,  # Maximum
                    'target_width_mm': 100
                }
            )
        # 极值参数下仍应成功返回文件
        assert response.status_code == 200
        assert len(response.data) > 0
    
    def test_export_line_min_precision(self, client):
        """line 模式精度下限 0：应可正常导出。"""
        img_path = get_test_image_path()
        with open(img_path, 'rb') as f:
            response = client.post(
                '/api/export',
                data={
                    'image': (f, 'test.jpg'),
                    'format': '.dst',
                    'mode': 'line',
                    'line_precision': 0,  # Minimum
                    'target_width_mm': 100
                }
            )
        # 极值参数下仍应成功返回文件
        assert response.status_code == 200
        assert len(response.data) > 0
    
    def test_export_canny_extreme_thresholds(self, client):
        """canny 阈值极值（low=0, high=255）：应可正常导出。"""
        img_path = get_test_image_path()
        with open(img_path, 'rb') as f:
            response = client.post(
                '/api/export',
                data={
                    'image': (f, 'test.jpg'),
                    'format': '.pes',
                    'mode': 'canny',
                    'canny_low': 0,      # Minimum
                    'canny_high': 255,   # Maximum
                    'target_width_mm': 100
                }
            )
        # 阈值极端组合下仍应返回有效文件
        assert response.status_code == 200
        assert len(response.data) > 0
    
    def test_export_raster_max_row_spacing(self, client):
        """raster 行间距上限 16：应可正常导出。"""
        img_path = get_test_image_path()
        with open(img_path, 'rb') as f:
            response = client.post(
                '/api/export',
                data={
                    'image': (f, 'test.jpg'),
                    'format': '.jef',
                    'mode': 'raster',
                    'raster_row_spacing': 16,  # Maximum
                    'raster_min_stitch': 2,
                    'raster_max_stitch': 12,
                    'target_width_mm': 100
                }
            )
        # 边界参数下仍应成功导出
        assert response.status_code == 200
        assert len(response.data) > 0
    
    def test_export_raster_min_row_spacing(self, client):
        """raster 行间距下限 1：应可正常导出。"""
        img_path = get_test_image_path()
        with open(img_path, 'rb') as f:
            response = client.post(
                '/api/export',
                data={
                    'image': (f, 'test.jpg'),
                    'format': '.jef',
                    'mode': 'raster',
                    'raster_row_spacing': 1,  # Minimum
                    'raster_min_stitch': 2,
                    'raster_max_stitch': 12,
                    'target_width_mm': 100
                }
            )
        # 边界参数下仍应成功导出
        assert response.status_code == 200
        assert len(response.data) > 0
