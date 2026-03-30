document.addEventListener('DOMContentLoaded', function() {

    // Workspace functionality
    (function () {
        let uploadedImage = null;
        let currentMode = 'line';

        //弹窗
        function showMessageModal(title, message) {
            const modal = document.getElementById('test-error-modal');         // ✅ 改这里
            const msgEl = document.getElementById('test-error-message');       // ✅ 改这里
            const okBtn = document.getElementById('test-error-ok');            // ✅ 改这里
            const closeBtn = document.getElementById('test-error-close');

            // If modal markup is missing, do nothing (avoid crashing).
            if (!modal || !okBtn || !msgEl) return;

            msgEl.textContent = message;

            // Show modal
            modal.classList.remove('hidden');

            // Hide helper
            const hide = () => modal.classList.add('hidden');

            // Close actions
            okBtn.onclick = hide;
            if (closeBtn) closeBtn.onclick = hide;

        }

        // DOM elements
        const fileInput = document.getElementById('file-input');
        const uploadZone = document.getElementById('upload-zone');
        const originalCanvas = document.getElementById('original-canvas');
        const processedCanvas = document.getElementById('processed-canvas');
        const previewEmpty = document.getElementById('preview-empty');
        const previewCanvases = document.getElementById('preview-canvases');
        const processingIndicator = document.getElementById('processing-indicator');

        // Card elements
        const modeCard = document.getElementById('mode-card');
        const settingsCard = document.getElementById('settings-card');
        const exportCard = document.getElementById('export-card');

        // Tab buttons
        const tabButtons = document.querySelectorAll('.tab-button');

        // Parameter elements
        const linePrecisionSlider = document.getElementById('line-precision');
        const linePrecisionValue = document.getElementById('line-value');
        const cannyLowSlider = document.getElementById('canny-low');
        const cannyLowValue = document.getElementById('canny-low-value');
        const cannyHighSlider = document.getElementById('canny-high');
        const cannyHighValue = document.getElementById('canny-high-value');
        const rasterRowSpacingSlider = document.getElementById('raster-row-spacing');
        const rasterRowSpacingValue = document.getElementById('raster-row-spacing-value');
        const rasterWhiteThresholdSlider = document.getElementById('raster-white-threshold');
        const rasterWhiteThresholdValue = document.getElementById('raster-white-threshold-value');
        const rasterContrastBoostSlider = document.getElementById('raster-contrast-boost');
        const rasterContrastBoostValue = document.getElementById('raster-contrast-boost-value');

        // Upload zone click
        uploadZone.addEventListener('click', function () {
            fileInput.click();
        });

        // File input change
        fileInput.addEventListener('change', handleFileUpload);

        // Drag and drop
        uploadZone.addEventListener('dragover', function (e) {
            e.preventDefault();
            e.stopPropagation();
            uploadZone.style.borderColor = '#1A237E';
        });

        uploadZone.addEventListener('dragleave', function (e) {
            e.preventDefault();
            e.stopPropagation();
            uploadZone.style.borderColor = '#E5E7EB';
        });

        uploadZone.addEventListener('drop', function (e) {
            e.preventDefault();
            e.stopPropagation();
            uploadZone.style.borderColor = '#E5E7EB';

            const file = e.dataTransfer.files[0];
            if (file && file.type.startsWith('image/')) {
                handleFile(file);
            }
        });

        // Tab switching
        tabButtons.forEach(button => {
            button.addEventListener('click', function () {
                const mode = this.getAttribute('data-mode');
                switchMode(mode);
            });
        });

        // Slider updates
        function setupSlider(slider, valueDisplay) {
            slider.addEventListener('input', function () {
                const percentage = ((this.value - this.min) / (this.max - this.min)) * 100;
                this.style.setProperty('--value', percentage + '%');
                valueDisplay.textContent = this.value;
                if (uploadedImage) {
                    processImage();
                }
            });
        }

        setupSlider(linePrecisionSlider, linePrecisionValue);
        setupSlider(cannyLowSlider, cannyLowValue);
        setupSlider(cannyHighSlider, cannyHighValue);
        setupSlider(rasterRowSpacingSlider, rasterRowSpacingValue);
        setupSlider(rasterWhiteThresholdSlider, rasterWhiteThresholdValue);

        rasterContrastBoostSlider.addEventListener('input', function () {
            const percentage = ((this.value - this.min) / (this.max - this.min)) * 100;
            this.style.setProperty('--value', percentage + '%');
            rasterContrastBoostValue.textContent = (parseInt(this.value, 10) / 10).toFixed(1);
            if (uploadedImage) {
                processImage();
            }
        });

        // Handle file upload
        function handleFileUpload(event) {
            const file = event.target.files[0];
            if (file) {
                handleFile(file);
            }
        }

        function handleFile(file) {
            // Check file size (5MB limit)
            if (file.size > 5 * 1024 * 1024) {
                showMessageModal('Error', 'File size cannot exceed 5MB. Please try again.');
                return;
            }

            // Check file type
            if (!['image/jpeg', 'image/png', 'image/bmp'].includes(file.type)) {
                showMessageModal('Error', 'Only JPG, PNG, BMP formats are supported！');
                return;
            }

            const reader = new FileReader();
            reader.onload = function (e) {
                //读取成功
                uploadedImage = e.target.result;
                showPreview();
                processImage();
            };
            reader.onerror = function(){
                //失败情况
                showMessageModal('Error', 'Failed to read file. Please try again.');
            };
            reader.readAsDataURL(file);
        }

        function showPreview() {
            previewEmpty.classList.add('hidden');
            previewCanvases.classList.remove('hidden');
            modeCard.classList.remove('hidden');
            settingsCard.classList.remove('hidden');
            exportCard.classList.remove('hidden');
            uploadZone.style.borderColor = '#1A237E';
        }

        function switchMode(mode) {
            currentMode = mode;

            // Update active tab
            tabButtons.forEach(btn => {
                if (btn.getAttribute('data-mode') === mode) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            });

            // Show/hide parameter panels
            document.getElementById('line-params').classList.add('hidden');
            document.getElementById('canny-params').classList.add('hidden');
            document.getElementById('raster-params').classList.add('hidden');
            document.getElementById(`${mode}-params`).classList.remove('hidden');

            if (uploadedImage) {
                processImage();
            }
        }

        function processImage() {
            if (!uploadedImage) return;

            processingIndicator.classList.remove('hidden');

            const img = new Image();
            img.onload = function () {
                // Set canvas sizes
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

                // Draw original image
                originalCtx.drawImage(img, 0, 0);

                // Get image data
                const imageData = originalCtx.getImageData(0, 0, img.width, img.height);
                const processedData = processedCtx.createImageData(img.width, img.height);

                // Apply processing based on mode
                if (currentMode === 'line') {
                    applyLineProcessing(imageData, processedData, parseInt(linePrecisionSlider.value, 10));
                } else if (currentMode === 'canny') {
                    applyCannyProcessing(imageData, processedData, parseInt(cannyLowSlider.value, 10), parseInt(cannyHighSlider.value, 10));
                } else if (currentMode === 'raster') {
                    applyRasterProcessing(imageData, processedData, parseInt(rasterWhiteThresholdSlider.value, 10));
                }

                processedCtx.putImageData(processedData, 0, 0);
                processingIndicator.classList.add('hidden');
            };
            img.src = uploadedImage;
        }

        // Image processing algorithms
        function applyLineProcessing(input, output, precision) {
            const threshold = 255 - (precision * 2.55);

            for (let i = 0; i < input.data.length; i += 4) {
                const gray = (input.data[i] + input.data[i + 1] + input.data[i + 2]) / 3;
                const value = gray < threshold ? 0 : 255;

                output.data[i] = value;
                output.data[i + 1] = value;
                output.data[i + 2] = value;
                output.data[i + 3] = 255;
            }
        }

        function applyCannyProcessing(input, output, low, high) {
            const width = input.width;
            const height = input.height;

            // Convert to grayscale
            const gray = new Uint8Array(width * height);
            for (let i = 0; i < input.data.length; i += 4) {
                gray[i / 4] = (input.data[i] + input.data[i + 1] + input.data[i + 2]) / 3;
            }

            // Simple edge detection using Sobel operator
            for (let y = 1; y < height - 1; y++) {
                for (let x = 1; x < width - 1; x++) {
                    const idx = y * width + x;

                    // Sobel kernels
                    const gx =
                        -gray[idx - width - 1] + gray[idx - width + 1] +
                        -2 * gray[idx - 1] + 2 * gray[idx + 1] +
                        -gray[idx + width - 1] + gray[idx + width + 1];

                    const gy =
                        -gray[idx - width - 1] - 2 * gray[idx - width] - gray[idx - width + 1] +
                        gray[idx + width - 1] + 2 * gray[idx + width] + gray[idx + width + 1];

                    const magnitude = Math.sqrt(gx * gx + gy * gy);

                    const pixelIdx = idx * 4;
                    if (magnitude > high) {
                        output.data[pixelIdx] = 255;
                        output.data[pixelIdx + 1] = 255;
                        output.data[pixelIdx + 2] = 255;
                    } else if (magnitude > low) {
                        output.data[pixelIdx] = 128;
                        output.data[pixelIdx + 1] = 128;
                        output.data[pixelIdx + 2] = 128;
                    } else {
                        output.data[pixelIdx] = 0;
                        output.data[pixelIdx + 1] = 0;
                        output.data[pixelIdx + 2] = 0;
                    }
                    output.data[pixelIdx + 3] = 255;
                }
            }
        }

        function applyRasterProcessing(input, output, whiteThreshold) {
            const threshold = whiteThreshold;

            for (let i = 0; i < input.data.length; i += 4) {
                const gray = (input.data[i] + input.data[i + 1] + input.data[i + 2]) / 3;
                const value = gray >= threshold ? 255 : 0;

                output.data[i] = value;
                output.data[i + 1] = value;
                output.data[i + 2] = value;
                output.data[i + 3] = 255;
            }
        }

        // Export function
        window.exportFile = function (format) {

            //显示处理中
            processingIndicator.classList.remove('hidden');

            processedCanvas.toBlob(function (blob) {
                if (!blob) {
                    showMessageModal('Error', 'Failed to export image. Please try again.');
                    processingIndicator.classList.add('hidden');
                    return;
                }

                // 创建 FormData 用来发送数据
                const formData = new FormData();
                formData.append('image', blob);
                formData.append('format', format);
                formData.append('mode', currentMode);

                // Common embroidery settings
                const targetWidth = document.getElementById('target-width');
                const minStitchLen = document.getElementById('min-stitch-len');
                const maxStitchLen = document.getElementById('max-stitch-len');
                formData.append('target_width_mm', targetWidth ? targetWidth.value : '100');
                formData.append('min_stitch_len_mm', minStitchLen ? minStitchLen.value : '0.8');
                formData.append('max_stitch_len_mm', maxStitchLen ? maxStitchLen.value : '6.0');

                // Mode specific settings
                formData.append('line_precision', linePrecisionSlider.value);
                formData.append('canny_low', cannyLowSlider.value);
                formData.append('canny_high', cannyHighSlider.value);
                formData.append('raster_row_spacing', rasterRowSpacingSlider.value);
                formData.append('raster_white_threshold', rasterWhiteThresholdSlider.value);
                formData.append('raster_contrast_boost', (parseInt(rasterContrastBoostSlider.value, 10) / 10).toFixed(1));

                const rasterMinStep = document.getElementById('raster-min-stitch');
                const rasterMaxStep = document.getElementById('raster-max-stitch');
                formData.append('raster_min_stitch', rasterMinStep ? rasterMinStep.value : '2');
                formData.append('raster_max_stitch', rasterMaxStep ? rasterMaxStep.value : '12');

                //  发送到后端 /api/export 路由
                fetch('/api/export', {
                    method: 'POST',
                    body: formData
                })
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Export failed');
                    }
                    //  后端返回的是真正的刺绣格式 Blob
                    return response.blob();
                })
                .then(blob => {
                    // 下载后端生成的真正的刺绣格式文件
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `embroidery_design${format}`;  // 现在这是真的了！
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                })
                .catch(error => {
                    //处理错误
                    showMessageModal('Error', 'Export failed: ' + error.message);
                })
                .finally(() => {
                    processingIndicator.classList.add('hidden');
                });
            }, 'image/png');
        };
    })();
});