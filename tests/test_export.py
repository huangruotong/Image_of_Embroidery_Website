import base64
import json
import os
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
import pyembroidery
import pytest

from app import FIXED_HOOP_HEIGHT_MM, FIXED_HOOP_WIDTH_MM, build_embroidery_pattern
from embroidery import (
    get_image,
    image_to_embroidery_canny,
    pattern_has_stitches,
    pattern_path_metrics,
    pattern_to_data_url,
    photo_to_line_embroidery,
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
        response = client.post('/api/export', data={'format': '.dst', 'mode': 'line'})
        assert response.status_code == 401
        data = json.loads(response.data)
        assert data['error'] == 'Authentication required'

    def test_preview_requires_authentication(self, client):
        response = post_preview(
            client,
            image_bytes=image_bytes_from_file(),
            filename='test.jpg',
            mode='line'
        )
        assert response.status_code == 401
        data = json.loads(response.data)
        assert data['error'] == 'Authentication required'


class TestExportValidation:
    def test_export_missing_image(self, authenticated_client):
        response = authenticated_client.post(
            '/api/export',
            data={'format': '.dst', 'mode': 'line'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_export_missing_format(self, authenticated_client):
        response = post_export(
            authenticated_client,
            image_bytes=image_bytes_from_file(),
            filename='test.jpg',
            mode='line'
        )
        assert response.status_code == 400


class TestExportSuccess:
    def test_export_line_mode_success(self, authenticated_client):
        response = post_export(
            authenticated_client,
            image_bytes=image_bytes_from_file(),
            filename='test.jpg',
            format='.dst',
            mode='line',
            line_precision=50,
            target_width_mm=100,
            min_stitch_len_mm=0.8,
            max_stitch_len_mm=6.0,
            line_contrast_boost=1.8,
        )
        assert response.status_code == 200
        assert len(response.data) > 0

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

        line_pattern = photo_to_line_embroidery(image, scale=1.0)
        raster_pattern = photo_to_raster_embroidery(image, scale=1.0)
        canny_pattern = image_to_embroidery_canny(image, scale=1.0)

        assert isinstance(line_pattern, pyembroidery.EmbPattern)
        assert isinstance(raster_pattern, pyembroidery.EmbPattern)
        assert isinstance(canny_pattern, pyembroidery.EmbPattern)


class TestExportBoundary:
    def test_export_line_max_precision(self, authenticated_client):
        response = post_export(
            authenticated_client,
            image_bytes=image_bytes_from_file(),
            filename='test.jpg',
            format='.dst',
            mode='line',
            line_precision=100,
            target_width_mm=100
        )
        assert response.status_code == 200
        assert len(response.data) > 0

    def test_export_line_min_precision(self, authenticated_client):
        response = post_export(
            authenticated_client,
            image_bytes=image_bytes_from_file(),
            filename='test.jpg',
            format='.dst',
            mode='line',
            line_precision=0,
            target_width_mm=100
        )
        assert response.status_code == 200
        assert len(response.data) > 0

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
    def test_preview_line_mode_success(self, authenticated_client):
        response = post_preview(
            authenticated_client,
            image_bytes=image_bytes_from_file('sign_in.jpg'),
            filename='test.jpg',
            mode='line',
            line_precision=50,
            line_contrast_boost=1.8,
            target_width_mm=100,
            min_stitch_len_mm=0.8,
            max_stitch_len_mm=6.0,
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['preview'].startswith('data:image/png;base64,')
        assert data['empty'] is False
        assert 'applied_settings' in data
        assert 'analysis' not in data

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

    def test_line_contrast_boost_changes_export_output(self, authenticated_client):
        image_data = image_bytes_from_file('sign_in.jpg')
        low = post_export(
            authenticated_client,
            image_bytes=image_data,
            filename='sign_in.jpg',
            format='.dst',
            mode='line',
            line_precision=50,
            line_contrast_boost=0.8,
            target_width_mm=100,
        )
        high = post_export(
            authenticated_client,
            image_bytes=image_data,
            filename='sign_in.jpg',
            format='.dst',
            mode='line',
            line_precision=50,
            line_contrast_boost=3.0,
            target_width_mm=100,
        )
        assert low.status_code == 200
        assert high.status_code == 200
        assert low.data != high.data


class TestPathOptimization:
    @pytest.mark.parametrize(
        ('mode', 'form_data'),
        [
            (
                'line',
                {
                    'mode': 'line',
                    'line_precision': 50,
                    'line_contrast_boost': 1.8,
                    'target_width_mm': 100,
                    'min_stitch_len_mm': 0.8,
                    'max_stitch_len_mm': 6.0,
                },
            ),
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
        assert metrics['max_stitch_length_mm'] <= 6.05, (mode, metrics)

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
    @pytest.mark.parametrize(
        ('alpha', 'beta'),
        [
            (1.0, 0),
            (1.0, -25),
            (1.0, 25),
            (0.75, 0),
            (1.25, 0),
        ],
        ids=['original', 'darker', 'brighter', 'low-contrast', 'high-contrast'],
    )
    def test_fixed_line_settings_keep_portrait_variants_non_empty(self, alpha, beta):
        result = build_pattern_details(
            image_bytes=adjusted_image_bytes('sign_in.jpg', alpha=alpha, beta=beta),
            mode='line',
            line_precision=50,
            line_contrast_boost=1.8,
            target_width_mm=100,
            min_stitch_len_mm=0.8,
            max_stitch_len_mm=6.0,
        )
        assert pattern_has_stitches(result['pattern'])
        assert result['settings']['mode'] == 'line'

    def test_missing_values_use_fixed_defaults(self):
        result = build_pattern_details(filename='sign_in.jpg')

        assert result['settings']['mode'] == 'line'
        assert result['settings']['target_width_mm'] == 100.0
        assert result['settings']['min_stitch_len_mm'] == 0.8
        assert result['settings']['max_stitch_len_mm'] == 6.0
        assert result['settings']['line_precision'] == 50
        assert result['settings']['line_contrast_boost'] == 1.8

    def test_defaults_do_not_change_for_low_contrast_variant(self):
        original = build_pattern_details(filename='sign_in.jpg')
        low_contrast = build_pattern_details(
            image_bytes=adjusted_image_bytes('sign_in.jpg', alpha=0.75, beta=0),
        )

        assert original['settings'] == low_contrast['settings']

    def test_export_blocks_when_design_exceeds_hoop_limit(self, authenticated_client):
        response = post_export(
            authenticated_client,
            image_bytes=image_bytes_from_file('sign_in.jpg'),
            filename='portrait.jpg',
            format='.dst',
            mode='line',
            target_width_mm=FIXED_HOOP_WIDTH_MM + 1,
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['error'] == (
            f'This size exceeds the hoop limit ({int(FIXED_HOOP_WIDTH_MM)} x {int(FIXED_HOOP_HEIGHT_MM)} mm).'
        )

    def test_preview_ignores_client_supplied_hoop_values(self, authenticated_client):
        response = post_preview(
            authenticated_client,
            image_bytes=image_bytes_from_file('sign_in.jpg'),
            filename='portrait.jpg',
            mode='line',
            target_width_mm=100,
            hoop_width_mm=80,
            hoop_height_mm=80,
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['applied_settings']['hoop_width_mm'] == FIXED_HOOP_WIDTH_MM
        assert data['applied_settings']['hoop_height_mm'] == FIXED_HOOP_HEIGHT_MM

    def test_preview_ignores_removed_auto_tune_flag_and_returns_requested_settings(self, authenticated_client):
        response = post_preview(
            authenticated_client,
            image_bytes=image_bytes_from_file('sign_in.jpg'),
            filename='portrait.jpg',
            mode='line',
            line_precision=44,
            line_contrast_boost=2.2,
            target_width_mm=96,
            min_stitch_len_mm=0.9,
            max_stitch_len_mm=5.7,
            auto_tune='1',
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'auto_tuned' not in data['applied_settings']
        assert 'recommended_mode' not in data['applied_settings']
        assert data['applied_settings']['mode'] == 'line'
        assert data['applied_settings']['line_precision'] == 44
        assert data['applied_settings']['line_contrast_boost'] == 2.2
        assert data['applied_settings']['target_width_mm'] == 96.0
        assert data['applied_settings']['min_stitch_len_mm'] == 0.9
        assert data['applied_settings']['max_stitch_len_mm'] == 5.7


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
