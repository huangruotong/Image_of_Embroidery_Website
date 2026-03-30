import pytest
import json
import os
from pathlib import Path


def get_test_image_path():
    """Get path to test image file."""
    current_dir = Path(__file__).parent.parent
    return os.path.join(str(current_dir), 'static', 'images', 'home_photo.jpg')


class TestExportValidation:
    """Test suite for export endpoint validation."""
    
    def test_export_missing_image(self, client):
        """Test export without image returns 400."""
        response = client.post(
            '/api/export',
            data={'format': '.dst', 'mode': 'line'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_export_missing_format(self, client):
        """Test export without format returns 400."""
        img_path = get_test_image_path()
        with open(img_path, 'rb') as f:
            response = client.post(
                '/api/export',
                data={
                    'image': (f, 'test.jpg'),
                    'mode': 'line'
                }
            )
        assert response.status_code == 400


class TestExportSuccess:
    """Test suite for successful export operations."""
    
    def test_export_line_mode_success(self, client):
        """Test line mode export returns 200 and non-empty file."""
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
        assert response.status_code == 200
        assert len(response.data) > 0
    
    def test_export_canny_mode_success(self, client):
        """Test canny mode export returns 200 and non-empty file."""
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
        assert response.status_code == 200
        assert len(response.data) > 0
    
    def test_export_raster_mode_success(self, client):
        """Test raster mode export returns 200 and non-empty file."""
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
        assert response.status_code == 200
        assert len(response.data) > 0


class TestExportBoundary:
    """Test suite for boundary/extreme parameter values."""
    
    def test_export_line_max_precision(self, client):
        """Test line mode with maximum precision (100)."""
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
        assert response.status_code == 200
        assert len(response.data) > 0
    
    def test_export_line_min_precision(self, client):
        """Test line mode with minimum precision (0)."""
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
        assert response.status_code == 200
        assert len(response.data) > 0
    
    def test_export_canny_extreme_thresholds(self, client):
        """Test canny mode with extreme threshold values."""
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
        assert response.status_code == 200
        assert len(response.data) > 0
    
    def test_export_raster_max_row_spacing(self, client):
        """Test raster mode with maximum row spacing (16)."""
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
        assert response.status_code == 200
        assert len(response.data) > 0
    
    def test_export_raster_min_row_spacing(self, client):
        """Test raster mode with minimum row spacing (1)."""
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
        assert response.status_code == 200
        assert len(response.data) > 0
