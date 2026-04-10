document.addEventListener('DOMContentLoaded', function () {
    (function () {
        let uploadedImage = null;
        let uploadedFile = null;
        let currentMode = 'line';
        let sourceImageWidth = 0;
        let sourceImageHeight = 0;
        let lastPreviewDataUrl = null;
        let isPreviewLoading = false;

        function requireAuthenticatedWorkspaceAction() {
            if (window.appAuthState && window.appAuthState.authenticated) {
                return false;
            }

            if (typeof window.showLoginRequiredModal === 'function') {
                window.showLoginRequiredModal();
            }
            return true;
        }

        function showMessageModal(message) {
            const modal = document.getElementById('error-modal');
            const msgEl = document.getElementById('error-modal-message');
            const okBtn = document.getElementById('error-modal-ok');
            const closeBtn = document.getElementById('error-modal-close');

            if (!modal || !okBtn || !msgEl) return;

            msgEl.textContent = message;
            modal.classList.remove('hidden');

            const hide = () => modal.classList.add('hidden');
            okBtn.onclick = hide;
            if (closeBtn) closeBtn.onclick = hide;
        }

        const fileInput = document.getElementById('file-input');
        const uploadZone = document.getElementById('upload-zone');
        const workspaceRoot = document.getElementById('workspace-root');
        const originalCanvas = document.getElementById('original-canvas');
        const processedCanvas = document.getElementById('processed-canvas');
        const previewEmpty = document.getElementById('preview-empty');
        const previewCanvases = document.getElementById('preview-canvases');
        const processingIndicator = document.getElementById('processing-indicator');

        const modeCard = document.getElementById('mode-card');
        const settingsCard = document.getElementById('settings-card');
        const exportCard = document.getElementById('export-card');
        const tabButtons = document.querySelectorAll('.tab-button');

        const targetWidthInput = document.getElementById('target-width');
        const targetWidthError = document.getElementById('target-width-error');
        const targetWidthErrorText = document.getElementById('target-width-error-text');
        const minStitchLenInput = document.getElementById('min-stitch-len');
        const maxStitchLenInput = document.getElementById('max-stitch-len');
        const rasterMinStepInput = document.getElementById('raster-min-stitch');
        const rasterMaxStepInput = document.getElementById('raster-max-stitch');
        const fixedHoopWidthMm = Number(workspaceRoot?.dataset.hoopWidthMm || '130');
        const fixedHoopHeightMm = Number(workspaceRoot?.dataset.hoopHeightMm || '180');

        const linePrecisionSlider = document.getElementById('line-precision');
        const linePrecisionValue = document.getElementById('line-value');
        const lineContrastBoostSlider = document.getElementById('line-contrast-boost');
        const lineContrastBoostValue = document.getElementById('line-contrast-boost-value');
        const cannyLowSlider = document.getElementById('canny-low');
        const cannyLowValue = document.getElementById('canny-low-value');
        const cannyHighSlider = document.getElementById('canny-high');
        const cannyHighValue = document.getElementById('canny-high-value');
        const cannyContrastBoostSlider = document.getElementById('canny-contrast-boost');
        const cannyContrastBoostValue = document.getElementById('canny-contrast-boost-value');
        const rasterRowSpacingSlider = document.getElementById('raster-row-spacing');
        const rasterRowSpacingValue = document.getElementById('raster-row-spacing-value');
        const rasterWhiteThresholdSlider = document.getElementById('raster-white-threshold');
        const rasterWhiteThresholdValue = document.getElementById('raster-white-threshold-value');
        const rasterContrastBoostSlider = document.getElementById('raster-contrast-boost');
        const rasterContrastBoostValue = document.getElementById('raster-contrast-boost-value');

        function updateSliderBackground(slider) {
            const percentage = ((slider.value - slider.min) / (slider.max - slider.min)) * 100;
            slider.style.setProperty('--value', percentage + '%');
        }

        function updateContrastDisplay(slider, valueDisplay) {
            updateSliderBackground(slider);
            valueDisplay.textContent = (parseInt(slider.value, 10) / 10).toFixed(1);
        }

        function formatCompactNumber(value) {
            const numericValue = Number(value || 0);
            return Number.isInteger(numericValue) ? String(numericValue) : numericValue.toFixed(1);
        }

        function getHoopLimitMessage() {
            return `This size exceeds the hoop limit (${formatCompactNumber(fixedHoopWidthMm)} x ${formatCompactNumber(fixedHoopHeightMm)} mm).`;
        }

        function getExportHoopLimitMessage() {
            return `This design exceeds the hoop size (${formatCompactNumber(fixedHoopWidthMm)} x ${formatCompactNumber(fixedHoopHeightMm)} mm). Please try again.`;
        }

        function showTargetWidthError(message) {
            if (!targetWidthError || !targetWidthErrorText) return;
            targetWidthErrorText.textContent = message;
            targetWidthError.classList.remove('hidden');
        }

        function hideTargetWidthError() {
            if (!targetWidthError) return;
            targetWidthError.classList.add('hidden');
        }

        function getTargetWidthErrorMessage(targetWidthValue) {
            const widthMm = Number(targetWidthValue);
            if (!Number.isFinite(widthMm) || widthMm <= 0) {
                return '';
            }

            const heightMm = sourceImageWidth > 0
                ? widthMm * (sourceImageHeight / sourceImageWidth)
                : null;
            const exceedsWidth = widthMm > fixedHoopWidthMm + 1e-6;
            const exceedsHeight = heightMm !== null && heightMm > fixedHoopHeightMm + 1e-6;

            if (!exceedsWidth && !exceedsHeight) {
                return '';
            }

            return getHoopLimitMessage();
        }

        function validateTargetWidthInput() {
            if (!targetWidthInput) return '';

            const message = getTargetWidthErrorMessage(targetWidthInput.value);
            if (message) {
                showTargetWidthError(message);
            } else {
                hideTargetWidthError();
            }
            return message;
        }

        function syncUploadZoneState(isDragActive = false) {
            if (!uploadZone) return;
            uploadZone.classList.toggle('upload-zone-active', isDragActive || Boolean(uploadedImage));
        }

        function applyModeUI(mode) {
            currentMode = mode;

            tabButtons.forEach(btn => {
                if (btn.getAttribute('data-mode') === mode) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            });

            document.getElementById('line-params').classList.add('hidden');
            document.getElementById('canny-params').classList.add('hidden');
            document.getElementById('raster-params').classList.add('hidden');
            document.getElementById(`${mode}-params`).classList.remove('hidden');
        }

        function setMode(mode, shouldPreview) {
            applyModeUI(mode);
            if (shouldPreview && uploadedImage) {
                requestPatternPreview();
            }
        }

        function applySettings(settings) {
            if (!settings) return;

            applyModeUI(settings.mode || currentMode);

            if (targetWidthInput && settings.target_width_mm !== undefined) {
                targetWidthInput.value = settings.target_width_mm;
            }
            if (minStitchLenInput && settings.min_stitch_len_mm !== undefined) {
                minStitchLenInput.value = settings.min_stitch_len_mm;
            }
            if (maxStitchLenInput && settings.max_stitch_len_mm !== undefined) {
                maxStitchLenInput.value = settings.max_stitch_len_mm;
            }
            if (rasterMinStepInput && settings.raster_min_stitch !== undefined) {
                rasterMinStepInput.value = settings.raster_min_stitch;
            }
            if (rasterMaxStepInput && settings.raster_max_stitch !== undefined) {
                rasterMaxStepInput.value = settings.raster_max_stitch;
            }

            if (settings.line_precision !== undefined) {
                linePrecisionSlider.value = settings.line_precision;
                linePrecisionValue.textContent = settings.line_precision;
                updateSliderBackground(linePrecisionSlider);
            }
            if (settings.line_contrast_boost !== undefined) {
                lineContrastBoostSlider.value = String(Math.round(settings.line_contrast_boost * 10));
                updateContrastDisplay(lineContrastBoostSlider, lineContrastBoostValue);
            }
            if (settings.canny_low !== undefined) {
                cannyLowSlider.value = settings.canny_low;
                cannyLowValue.textContent = settings.canny_low;
                updateSliderBackground(cannyLowSlider);
            }
            if (settings.canny_high !== undefined) {
                cannyHighSlider.value = settings.canny_high;
                cannyHighValue.textContent = settings.canny_high;
                updateSliderBackground(cannyHighSlider);
            }
            if (settings.canny_contrast_boost !== undefined) {
                cannyContrastBoostSlider.value = String(Math.round(settings.canny_contrast_boost * 10));
                updateContrastDisplay(cannyContrastBoostSlider, cannyContrastBoostValue);
            }
            if (settings.raster_row_spacing !== undefined) {
                rasterRowSpacingSlider.value = settings.raster_row_spacing;
                rasterRowSpacingValue.textContent = settings.raster_row_spacing;
                updateSliderBackground(rasterRowSpacingSlider);
            }
            if (settings.raster_white_threshold !== undefined) {
                rasterWhiteThresholdSlider.value = settings.raster_white_threshold;
                rasterWhiteThresholdValue.textContent = settings.raster_white_threshold;
                updateSliderBackground(rasterWhiteThresholdSlider);
            }
            if (settings.raster_contrast_boost !== undefined) {
                rasterContrastBoostSlider.value = String(Math.round(settings.raster_contrast_boost * 10));
                updateContrastDisplay(rasterContrastBoostSlider, rasterContrastBoostValue);
            }

            validateTargetWidthInput();
        }

        function requestPatternPreview() {
            if (requireAuthenticatedWorkspaceAction()) return;
            if (!uploadedImage) return;

            processingIndicator.classList.remove('hidden');

            const img = new Image();
            img.onload = function () {
                sourceImageWidth = img.width;
                sourceImageHeight = img.height;
                originalCanvas.width = img.width;
                originalCanvas.height = img.height;
                originalCanvas.style.maxWidth = '100%';
                originalCanvas.style.height = 'auto';

                processedCanvas.width = img.width;
                processedCanvas.height = img.height;
                processedCanvas.style.maxWidth = '100%';
                processedCanvas.style.height = 'auto';

                const originalCtx = originalCanvas.getContext('2d');
                const processedCtx = processedCanvas.getContext('2d');
                originalCtx.drawImage(img, 0, 0);
                processedCtx.clearRect(0, 0, processedCanvas.width, processedCanvas.height);

                processingIndicator.classList.add('hidden');
                validateTargetWidthInput();
                fetchPatternPreviewDebounced();
            };
            img.src = uploadedImage;
        }

        function appendEmbroiderySettings(formData) {
            formData.append('target_width_mm', targetWidthInput ? targetWidthInput.value : '100');
            formData.append('min_stitch_len_mm', minStitchLenInput ? minStitchLenInput.value : '0.8');
            formData.append('max_stitch_len_mm', maxStitchLenInput ? maxStitchLenInput.value : '6.0');

            formData.append('line_precision', linePrecisionSlider.value);
            formData.append('line_contrast_boost', (parseInt(lineContrastBoostSlider.value, 10) / 10).toFixed(1));
            formData.append('canny_low', cannyLowSlider.value);
            formData.append('canny_high', cannyHighSlider.value);
            formData.append('canny_contrast_boost', (parseInt(cannyContrastBoostSlider.value, 10) / 10).toFixed(1));
            formData.append('raster_row_spacing', rasterRowSpacingSlider.value);
            formData.append('raster_white_threshold', rasterWhiteThresholdSlider.value);
            formData.append('raster_contrast_boost', (parseInt(rasterContrastBoostSlider.value, 10) / 10).toFixed(1));
            formData.append('raster_min_stitch', rasterMinStepInput ? rasterMinStepInput.value : '2');
            formData.append('raster_max_stitch', rasterMaxStepInput ? rasterMaxStepInput.value : '12');
        }

        function renderPreview(dataUrl) {
            const previewImg = new Image();
            previewImg.onload = function () {
                processedCanvas.width = previewImg.width;
                processedCanvas.height = previewImg.height;
                processedCanvas.style.maxWidth = '100%';
                processedCanvas.style.height = 'auto';
                processedCanvas.getContext('2d').drawImage(previewImg, 0, 0);
            };
            previewImg.src = dataUrl;
        }

        function downloadDataUrl(filename, dataUrl) {
            const link = document.createElement('a');
            link.href = dataUrl;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }

        function getPreviewDownloadName() {
            if (!uploadedFile || !uploadedFile.name) {
                return 'embroidery_preview.png';
            }

            const filename = uploadedFile.name.replace(/\.[^.]+$/, '');
            return `${filename || 'embroidery'}_preview.png`;
        }

        function debounce(fn, delay) {
            let timer;
            return function (...args) {
                clearTimeout(timer);
                timer = setTimeout(() => fn.apply(this, args), delay);
            };
        }

        function fetchPatternPreview() {
            if (requireAuthenticatedWorkspaceAction()) return;
            if (!uploadedFile) return;

            isPreviewLoading = true;
            lastPreviewDataUrl = null;
            processingIndicator.classList.remove('hidden');

            const formData = new FormData();
            formData.append('image', uploadedFile, uploadedFile.name);
            formData.append('mode', currentMode);
            appendEmbroiderySettings(formData);

            fetch('/api/preview', {
                method: 'POST',
                body: formData
            })
                .then(async response => {
                    if (response.status === 401) {
                        if (typeof window.showLoginRequiredModal === 'function') {
                            window.showLoginRequiredModal();
                        }
                        return null;
                    }
                    const data = await response.json();
                    if (!response.ok) {
                        throw new Error(data.error || 'Preview failed');
                    }
                    return data;
                })
                .then(data => {
                    if (!data) return;
                    if (data.applied_settings) {
                        applySettings(data.applied_settings);
                    }
                    if (data.preview) {
                        lastPreviewDataUrl = data.preview;
                        renderPreview(data.preview);
                    }
                })
                .catch(error => {
                    showMessageModal('Preview failed: ' + error.message);
                })
                .finally(() => {
                    isPreviewLoading = false;
                    processingIndicator.classList.add('hidden');
                });
        }

        const fetchPatternPreviewDebounced = debounce(fetchPatternPreview, 400);

        function showPreview() {
            previewEmpty.classList.add('hidden');
            previewCanvases.classList.remove('hidden');
            modeCard.classList.remove('hidden');
            settingsCard.classList.remove('hidden');
            exportCard.classList.remove('hidden');
            syncUploadZoneState();
        }

        function setupSlider(slider, valueDisplay) {
            slider.addEventListener('input', function () {
                updateSliderBackground(this);
                valueDisplay.textContent = this.value;
                if (uploadedImage) {
                    requestPatternPreview();
                }
            });
        }

        function setupNumericInput(input) {
            if (!input) return;
            input.addEventListener('input', function () {
                if (input === targetWidthInput) {
                    validateTargetWidthInput();
                }
                if (uploadedImage) {
                    fetchPatternPreviewDebounced();
                }
            });
        }

        function handleFile(file) {
            if (requireAuthenticatedWorkspaceAction()) return;
            if (file.size > 5 * 1024 * 1024) {
                showMessageModal('File size cannot exceed 5MB. Please try again.');
                return;
            }

            if (!['image/jpeg', 'image/png', 'image/bmp'].includes(file.type)) {
                showMessageModal('Only JPG, PNG, BMP formats are supported.');
                return;
            }

            uploadedFile = file;
            lastPreviewDataUrl = null;

            const reader = new FileReader();
            reader.onload = function (e) {
                uploadedImage = e.target.result;
                showPreview();
                requestPatternPreview();
            };
            reader.onerror = function () {
                showMessageModal('Failed to read file. Please try again.');
            };
            reader.readAsDataURL(file);
        }

        function handleFileUpload(event) {
            if (requireAuthenticatedWorkspaceAction()) {
                event.target.value = '';
                return;
            }
            const file = event.target.files[0];
            if (file) {
                handleFile(file);
            }
        }

        uploadZone.addEventListener('click', function () {
            if (requireAuthenticatedWorkspaceAction()) return;
            fileInput.click();
        });

        fileInput.addEventListener('change', handleFileUpload);

        uploadZone.addEventListener('dragover', function (e) {
            e.preventDefault();
            e.stopPropagation();
            syncUploadZoneState(true);
        });

        uploadZone.addEventListener('dragleave', function (e) {
            e.preventDefault();
            e.stopPropagation();
            syncUploadZoneState();
        });

        uploadZone.addEventListener('drop', function (e) {
            e.preventDefault();
            e.stopPropagation();
            syncUploadZoneState();

            if (requireAuthenticatedWorkspaceAction()) return;

            const file = e.dataTransfer.files[0];
            if (file && file.type.startsWith('image/')) {
                handleFile(file);
            }
        });

        tabButtons.forEach(button => {
            button.addEventListener('click', function () {
                setMode(this.getAttribute('data-mode'), true);
            });
        });

        setupSlider(linePrecisionSlider, linePrecisionValue);
        setupSlider(cannyLowSlider, cannyLowValue);
        setupSlider(cannyHighSlider, cannyHighValue);
        setupSlider(rasterRowSpacingSlider, rasterRowSpacingValue);
        setupSlider(rasterWhiteThresholdSlider, rasterWhiteThresholdValue);

        cannyContrastBoostSlider.addEventListener('input', function () {
            updateContrastDisplay(this, cannyContrastBoostValue);
            if (uploadedImage) {
                requestPatternPreview();
            }
        });

        rasterContrastBoostSlider.addEventListener('input', function () {
            updateContrastDisplay(this, rasterContrastBoostValue);
            if (uploadedImage) {
                requestPatternPreview();
            }
        });

        lineContrastBoostSlider.addEventListener('input', function () {
            updateContrastDisplay(this, lineContrastBoostValue);
            if (uploadedImage) {
                requestPatternPreview();
            }
        });

        [
            targetWidthInput,
            minStitchLenInput,
            maxStitchLenInput,
            rasterMinStepInput,
            rasterMaxStepInput
        ].forEach(setupNumericInput);

        updateSliderBackground(linePrecisionSlider);
        updateSliderBackground(cannyLowSlider);
        updateSliderBackground(cannyHighSlider);
        updateSliderBackground(rasterRowSpacingSlider);
        updateSliderBackground(rasterWhiteThresholdSlider);
        updateContrastDisplay(lineContrastBoostSlider, lineContrastBoostValue);
        updateContrastDisplay(cannyContrastBoostSlider, cannyContrastBoostValue);
        updateContrastDisplay(rasterContrastBoostSlider, rasterContrastBoostValue);
        syncUploadZoneState();

        window.exportFile = function (format) {
            if (requireAuthenticatedWorkspaceAction()) return;
            if (!uploadedFile) {
                showMessageModal('Please upload an image first.');
                return;
            }

            const targetWidthErrorMessage = validateTargetWidthInput();
            if (targetWidthErrorMessage) {
                showMessageModal(getExportHoopLimitMessage());
                return;
            }

            processingIndicator.classList.remove('hidden');

            const formData = new FormData();
            formData.append('image', uploadedFile, uploadedFile.name);
            formData.append('format', format);
            formData.append('mode', currentMode);
            appendEmbroiderySettings(formData);

            fetch('/api/export', {
                method: 'POST',
                body: formData
            })
                .then(async response => {
                    if (response.status === 401) {
                        if (typeof window.showLoginRequiredModal === 'function') {
                            window.showLoginRequiredModal();
                        }
                        return null;
                    }
                    if (!response.ok) {
                        let message = 'Export failed';
                        try {
                            const data = await response.json();
                            message = data.error || message;
                        } catch (_) {
                            // JSON 解析失败时使用兜底提示。
                        }
                        if (message === getHoopLimitMessage()) {
                            message = getExportHoopLimitMessage();
                        }
                        throw new Error(message);
                    }
                    return response.blob();
                })
                .then(blob => {
                    if (!blob) return;
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `embroidery_design${format}`;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                })
                .catch(error => {
                    showMessageModal(error.message || 'Export failed.');
                })
                .finally(() => {
                    processingIndicator.classList.add('hidden');
                });
        };

        window.exportPreviewPng = function () {
            if (requireAuthenticatedWorkspaceAction()) return;
            if (!uploadedFile) {
                showMessageModal('Please upload an image first.');
                return;
            }
            if (isPreviewLoading) {
                showMessageModal('Please wait for the preview to finish processing.');
                return;
            }
            if (!lastPreviewDataUrl) {
                showMessageModal('Please generate a preview before exporting PNG.');
                return;
            }

            downloadDataUrl(getPreviewDownloadName(), lastPreviewDataUrl);
        };
    })();
});
