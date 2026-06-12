import base64
import json
import os
from io import BytesIO
from pathlib import Path
import cv2
import numpy as np
import pyembroidery
import pytest

from app import build_embroidery_pattern
from embroidery import (
    get_image,
    image_to_embroidery_canny,
    pattern_has_stitches,
    pattern_path_metrics,
    pattern_to_data_url,
    photo_to_raster_embroidery,
)


def get_test_image_path(filename='home_photo.jpg'):
    current_dir = Path(__file__).parent.parent
    return os.path.join(str(current_dir), 'static', 'images', filename)


def image_bytes_from_file(filename='home_photo.jpg'):
    with open(get_test_image_path(filename), 'rb') as image_file:
        return image_file.read()


def solid_image_bytes(value=255, width=200, height=200):
    image = np.full((height, width, 3), value, dtype=np.uint8)
    ok, buffer = cv2.imencode('.png', image)
    assert ok
    return buffer.tobytes()


def oversized_file_bytes(size_mb=11):
    return b'0' * (size_mb * 1024 * 1024)


def adjusted_image_bytes(filename='sign_in.jpg', alpha=1.0, beta=0):
    image = get_image(image_bytes_from_file(filename))
    assert image is not None
    adjusted = cv2.convertScaleAbs(image, alpha=alpha, beta=beta)
    ok, buffer = cv2.imencode('.png', adjusted)
    assert ok
    return buffer.tobytes()


def post_export(client, *, image_bytes=None, filename='test.png', **form_data):
    payload = dict(form_data)
    if image_bytes is not None:
        payload['image'] = (BytesIO(image_bytes), filename)
    return client.post('/api/export', data=payload)


def post_preview(client, *, image_bytes=None, filename='test.png', **form_data):
    payload = dict(form_data)
    if image_bytes is not None:
        payload['image'] = (BytesIO(image_bytes), filename)
    return client.post('/api/preview', data=payload)


def build_pattern(filename='home_photo.jpg', **form_data):
    image = get_image(image_bytes_from_file(filename))
    assert image is not None
    return build_embroidery_pattern(image, form_data)


def build_pattern_details(filename='home_photo.jpg', image_bytes=None, **form_data):
    raw = image_bytes if image_bytes is not None else image_bytes_from_file(filename)
    image = get_image(raw)
    assert image is not None
    return build_embroidery_pattern(image, form_data, return_details=True)


class TestExportAuth:
    def test_export_requires_authentication(self, client):
        response = client.post('/api/export', data={'format': '.dst', 'mode': 'canny'})
        assert response.status_code == 401
        data = json.loads(response.data)
        assert data['error'] == 'Authentication required'

    def test_preview_requires_authentication(self, client):
        response = post_preview(
            client,
            image_bytes=image_bytes_from_file(),
            filename='test.jpg',
            mode='canny'
        )
        assert response.status_code == 401
        data = json.loads(response.data)
        assert data['error'] == 'Authentication required'


class TestExportValidation:
    def test_export_missing_image(self, authenticated_client):
        response = authenticated_client.post(
            '/api/export',
            data={'format': '.dst', 'mode': 'canny'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_export_missing_format(self, authenticated_client):
        response = post_export(
            authenticated_client,
            image_bytes=image_bytes_from_file(),
            filename='test.jpg',
            mode='canny'
        )
        assert response.status_code == 400


class TestUploadLimits:
    def test_preview_rejects_files_over_10mb(self, authenticated_client):
        response = post_preview(
            authenticated_client,
            image_bytes=oversized_file_bytes(),
            filename='large.jpg',
            mode='canny',
        )

        assert response.status_code == 413
        assert response.get_json()['error'] == 'File size cannot exceed 10MB'


class TestExportSuccess:
    def test_export_canny_mode_success(self, authenticated_client):
        response = post_export(
            authenticated_client,
            image_bytes=image_bytes_from_file(),
            filename='test.jpg',
            format='.pes',
            mode='canny',
            canny_low=50,
            canny_high=150,
            canny_contrast_boost=1.8,
            target_width_mm=100,
            min_stitch_len_mm=0.8,
            max_stitch_len_mm=6.0,
        )
        assert response.status_code == 200
        assert len(response.data) > 0

    def test_export_raster_mode_success(self, authenticated_client):
        response = post_export(
            authenticated_client,
            image_bytes=image_bytes_from_file(),
            filename='test.jpg',
            format='.jef',
            mode='raster',
            raster_row_spacing=4,
            raster_min_stitch=2,
            raster_max_stitch=12,
            raster_white_threshold=220,
            raster_contrast_boost=1.8,
            target_width_mm=100,
            min_stitch_len_mm=0.8,
            max_stitch_len_mm=6.0,
        )
        assert response.status_code == 200
        assert len(response.data) > 0


class TestEmbroideryFunctionContracts:
    def test_public_generators_return_patterns(self):
        image = get_image(image_bytes_from_file('sign_in.jpg'))
        assert image is not None

        raster_pattern = photo_to_raster_embroidery(image, scale=1.0)
        canny_pattern = image_to_embroidery_canny(image, scale=1.0)

        assert isinstance(raster_pattern, pyembroidery.EmbPattern)
        assert isinstance(canny_pattern, pyembroidery.EmbPattern)


class TestExportBoundary:
    def test_export_canny_extreme_thresholds(self, authenticated_client):
        response = post_export(
            authenticated_client,
            image_bytes=image_bytes_from_file(),
            filename='test.jpg',
            format='.pes',
            mode='canny',
            canny_low=0,
            canny_high=255,
            target_width_mm=100
        )
        assert response.status_code == 200
        assert len(response.data) > 0

    def test_export_raster_max_row_spacing(self, authenticated_client):
        response = post_export(
            authenticated_client,
            image_bytes=image_bytes_from_file(),
            filename='test.jpg',
            format='.jef',
            mode='raster',
            raster_row_spacing=16,
            raster_min_stitch=2,
            raster_max_stitch=12,
            target_width_mm=100
        )
        assert response.status_code == 200
        assert len(response.data) > 0

    def test_export_raster_min_row_spacing(self, authenticated_client):
        response = post_export(
            authenticated_client,
            image_bytes=image_bytes_from_file(),
            filename='test.jpg',
            format='.jef',
            mode='raster',
            raster_row_spacing=1,
            raster_min_stitch=2,
            raster_max_stitch=12,
            target_width_mm=100
        )
        assert response.status_code == 200
        assert len(response.data) > 0


class TestPreview:
    def test_preview_raster_white_image_returns_blank_preview(self, authenticated_client):
        response = post_preview(
            authenticated_client,
            image_bytes=solid_image_bytes(255),
            filename='white.png',
            mode='raster',
            raster_row_spacing=4,
            raster_white_threshold=220,
            raster_contrast_boost=1.8,
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['preview'].startswith('data:image/png;base64,')
        assert data['empty'] is True


class TestExportQualityGuards:
    def test_export_white_raster_returns_clear_error(self, authenticated_client):
        response = post_export(
            authenticated_client,
            image_bytes=solid_image_bytes(255),
            filename='white.png',
            format='.dst',
            mode='raster',
            raster_row_spacing=4,
            raster_white_threshold=220,
            raster_contrast_boost=1.8,
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'No stitches generated' in data['error']


class TestPathOptimization:
    @pytest.mark.parametrize(
        ('mode', 'form_data'),
        [
            (
                'canny',
                {
                    'mode': 'canny',
                    'canny_low': 50,
                    'canny_high': 150,
                    'canny_contrast_boost': 1.8,
                    'target_width_mm': 100,
                    'min_stitch_len_mm': 0.8,
                    'max_stitch_len_mm': 6.0,
                },
            ),
            (
                'raster',
                {
                    'mode': 'raster',
                    'raster_row_spacing': 4,
                    'raster_min_stitch': 2,
                    'raster_max_stitch': 12,
                    'raster_white_threshold': 220,
                    'raster_contrast_boost': 1.8,
                    'target_width_mm': 100,
                    'min_stitch_len_mm': 0.8,
                    'max_stitch_len_mm': 6.0,
                },
            ),
        ],
    )
    def test_generated_patterns_limit_jump_lengths(self, mode, form_data):
        pattern = build_pattern(**form_data)

        assert pattern_has_stitches(pattern), mode

        metrics = pattern_path_metrics(pattern)
        assert metrics['max_jump_length_mm'] <= 8.05, (mode, metrics)
        assert metrics['max_untrimmed_jump_length_mm'] <= 8.05, (mode, metrics)
        assert metrics['max_untrimmed_jump_run_length_mm'] <= 8.05, (mode, metrics)
        assert metrics['max_stitch_length_mm'] <= 6.05, (mode, metrics)

    def test_raster_portrait_limits_untrimmed_jump_runs(self):
        pattern = build_pattern(
            filename='sign_in.jpg',
            mode='raster',
            raster_row_spacing=5,
            raster_min_stitch=2,
            raster_max_stitch=12,
            raster_white_threshold=210,
            raster_contrast_boost=1.8,
            target_width_mm=100,
            min_stitch_len_mm=0.8,
            max_stitch_len_mm=6.0,
        )

        metrics = pattern_path_metrics(pattern)
        assert pattern_has_stitches(pattern)
        assert metrics['max_untrimmed_jump_run_length_mm'] <= 8.05, metrics

    def test_canny_contrast_boost_changes_export_output(self, authenticated_client):
        image_data = image_bytes_from_file('sign_in.jpg')
        low = post_export(
            authenticated_client,
            image_bytes=image_data,
            filename='sign_in.jpg',
            format='.pes',
            mode='canny',
            canny_low=50,
            canny_high=150,
            canny_contrast_boost=0.8,
            target_width_mm=100,
        )
        high = post_export(
            authenticated_client,
            image_bytes=image_data,
            filename='sign_in.jpg',
            format='.pes',
            mode='canny',
            canny_low=50,
            canny_high=150,
            canny_contrast_boost=3.0,
            target_width_mm=100,
        )
        assert low.status_code == 200
        assert high.status_code == 200
        assert low.data != high.data


class TestFixedDefaults:
    def test_missing_values_use_fixed_defaults(self):
        result = build_pattern_details(filename='sign_in.jpg')

        assert result['settings']['mode'] == 'canny'
        assert result['settings']['target_width_mm'] == 100.0
        assert result['settings']['min_stitch_len_mm'] == 0.8
        assert result['settings']['max_stitch_len_mm'] == 6.0

    def test_canny_defaults_keep_common_stitch_lengths(self):
        result = build_pattern_details(filename='sign_in.jpg', mode='canny')

        assert result['settings']['mode'] == 'canny'
        assert result['settings']['min_stitch_len_mm'] == 0.8
        assert result['settings']['max_stitch_len_mm'] == 6.0

    def test_defaults_do_not_change_for_low_contrast_variant(self):
        original = build_pattern_details(filename='sign_in.jpg')
        low_contrast = build_pattern_details(
            image_bytes=adjusted_image_bytes('sign_in.jpg', alpha=0.75, beta=0),
        )

        stable_keys = {
            'mode',
            'target_width_mm',
            'min_stitch_len_mm',
            'max_stitch_len_mm',
            'canny_low',
            'canny_high',
            'canny_contrast_boost',
            'canny_auto_thresholds',
            'canny_min_stitch_mm',
        }
        assert {
            key: original['settings'][key]
            for key in stable_keys
        } == {
            key: low_contrast['settings'][key]
            for key in stable_keys
        }

    def test_preview_ignores_client_supplied_machine_safety_settings(self, authenticated_client):
        response = post_preview(
            authenticated_client,
            image_bytes=image_bytes_from_file('sign_in.jpg'),
            filename='portrait.jpg',
            mode='canny',
            canny_contrast_boost=2.2,
            target_width_mm=96,
            min_stitch_len_mm=0.9,
            max_stitch_len_mm=5.7,
            canny_min_stitch_mm=1.9,
            auto_tune='1',
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'auto_tuned' not in data['applied_settings']
        assert 'recommended_mode' not in data['applied_settings']
        assert data['applied_settings']['mode'] == 'canny'
        assert data['applied_settings']['target_width_mm'] == 100.0
        assert data['applied_settings']['canny_contrast_boost'] == 2.2
        assert data['applied_settings']['min_stitch_len_mm'] == 0.8
        assert data['applied_settings']['max_stitch_len_mm'] == 6.0
        assert data['applied_settings']['canny_min_stitch_mm'] == 0.7


class TestPreviewRendering:
    def test_preview_does_not_draw_jump_as_stitch_line(self):
        pattern = pyembroidery.EmbPattern()
        pattern.add_stitch_absolute(pyembroidery.STITCH, 0, 0)
        pattern.add_stitch_absolute(pyembroidery.JUMP, 100, 100)
        pattern.add_stitch_absolute(pyembroidery.STITCH, 200, 100)
        pattern.add_command(pyembroidery.END)

        data_url = pattern_to_data_url(pattern, canvas_size=(100, 100))
        _, encoded = data_url.split(',', 1)
        preview_bytes = base64.b64decode(encoded)
        preview = cv2.imdecode(np.frombuffer(preview_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)

        assert preview is not None
        assert np.all(preview == 255)
