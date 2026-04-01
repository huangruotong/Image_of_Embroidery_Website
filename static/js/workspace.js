// 等待 DOM 渲染完成后初始化 Workspace 页面交互。
document.addEventListener('DOMContentLoaded', function() {

    // 立即执行函数用于封装页面级状态，避免变量泄漏到全局。
    (function () {
        // uploadedImage: DataURL，用于前端 canvas 绘制。
        let uploadedImage = null;
        // uploadedFile: 原始 File 对象，用于发送给后端预览/导出接口。
        let uploadedFile = null;
        // 当前算法模式，默认 line。
        let currentMode = 'line';

        // 统一错误弹窗：复用一个 modal 展示上传、读取、导出等错误信息。
        function showMessageModal(title, message) {
            const modal = document.getElementById('test-error-modal');
            const msgEl = document.getElementById('test-error-message');
            const okBtn = document.getElementById('test-error-ok');
            const closeBtn = document.getElementById('test-error-close');

            // 缺少必要节点时直接返回，避免抛错中断后续逻辑。
            if (!modal || !okBtn || !msgEl) return;

            // 当前 UI 只渲染 message，title 参数保留给未来扩展。
            msgEl.textContent = message;

            // 打开弹窗。
            modal.classList.remove('hidden');

            // 抽取统一关闭函数，供多个按钮复用。
            const hide = () => modal.classList.add('hidden');
            okBtn.onclick = hide;
            if (closeBtn) closeBtn.onclick = hide;
        }

        // 页面中会被频繁访问的 DOM 节点集中缓存，减少重复查询。
        const fileInput = document.getElementById('file-input');
        const uploadZone = document.getElementById('upload-zone');
        const originalCanvas = document.getElementById('original-canvas');
        const processedCanvas = document.getElementById('processed-canvas');
        const previewEmpty = document.getElementById('preview-empty');
        const previewCanvases = document.getElementById('preview-canvases');
        const processingIndicator = document.getElementById('processing-indicator');

        // 左侧卡片容器：文件上传后才会显示参数和导出区。
        const modeCard = document.getElementById('mode-card');
        const settingsCard = document.getElementById('settings-card');
        const exportCard = document.getElementById('export-card');

        // 模式切换 tab 按钮集合。
        const tabButtons = document.querySelectorAll('.tab-button');

        // 各模式参数滑块与数值显示节点。
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

        // 点击上传区域时转发到隐藏 input，触发系统文件选择器。
        uploadZone.addEventListener('click', function () {
            fileInput.click();
        });

        // 普通文件选择上传。
        fileInput.addEventListener('change', handleFileUpload);

        // 拖拽进入上传区时高亮边框。
        uploadZone.addEventListener('dragover', function (e) {
            e.preventDefault();
            e.stopPropagation();
            uploadZone.style.borderColor = '#1A237E';
        });

        // 拖拽离开时恢复边框。
        uploadZone.addEventListener('dragleave', function (e) {
            e.preventDefault();
            e.stopPropagation();
            uploadZone.style.borderColor = '#E5E7EB';
        });

        // 拖拽释放时读取第一个文件并进行类型预检查。
        uploadZone.addEventListener('drop', function (e) {
            e.preventDefault();
            e.stopPropagation();
            uploadZone.style.borderColor = '#E5E7EB';

            const file = e.dataTransfer.files[0];
            if (file && file.type.startsWith('image/')) {
                handleFile(file);
            }
        });

        // 点击不同 tab 切换模式，并切换对应参数面板。
        tabButtons.forEach(button => {
            button.addEventListener('click', function () {
                const mode = this.getAttribute('data-mode');
                switchMode(mode);
            });
        });

        // 通用滑块监听：更新滑轨样式、更新显示值、触发实时预览。
        function setupSlider(slider, valueDisplay) {
            slider.addEventListener('input', function () {
                const percentage = ((this.value - this.min) / (this.max - this.min)) * 100;
                this.style.setProperty('--value', percentage + '%');
                valueDisplay.textContent = this.value;

                // 已有图片时参数变化立即触发重算预览。
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

        // Canny 对比度增强滑块：显示值按 x/10 呈现为一位小数。
        cannyContrastBoostSlider.addEventListener('input', function () {
            const percentage = ((this.value - this.min) / (this.max - this.min)) * 100;
            this.style.setProperty('--value', percentage + '%');
            cannyContrastBoostValue.textContent = (parseInt(this.value, 10) / 10).toFixed(1);
            if (uploadedImage) {
                processImage();
            }
        });

        // Raster 对比度增强滑块。
        rasterContrastBoostSlider.addEventListener('input', function () {
            const percentage = ((this.value - this.min) / (this.max - this.min)) * 100;
            this.style.setProperty('--value', percentage + '%');
            rasterContrastBoostValue.textContent = (parseInt(this.value, 10) / 10).toFixed(1);
            if (uploadedImage) {
                processImage();
            }
        });

        // Line 对比度增强滑块：当前仅影响导出参数，不触发即时前端线稿算法。
        lineContrastBoostSlider.addEventListener('input', function () {
            const percentage = ((this.value - this.min) / (this.max - this.min)) * 100;
            this.style.setProperty('--value', percentage + '%');
            lineContrastBoostValue.textContent = (parseInt(this.value, 10) / 10).toFixed(1);
        });

        // input[type=file] 选择文件后的入口。
        function handleFileUpload(event) {
            const file = event.target.files[0];
            if (file) {
                handleFile(file);
            }
        }

        // 对文件做前端校验并读取为 DataURL。
        function handleFile(file) {
            // 文件体积上限 5MB。
            if (file.size > 5 * 1024 * 1024) {
                showMessageModal('Error', 'File size cannot exceed 5MB. Please try again.');
                return;
            }

            // 仅接受这三种 MIME 类型。
            if (!['image/jpeg', 'image/png', 'image/bmp'].includes(file.type)) {
                showMessageModal('Error', 'Only JPG, PNG, BMP formats are supported！');
                return;
            }

            uploadedFile = file;

            const reader = new FileReader();
            reader.onload = function (e) {
                uploadedImage = e.target.result;
                showPreview();
                processImage();
            };
            reader.onerror = function(){
                showMessageModal('Error', 'Failed to read file. Please try again.');
            };
            reader.readAsDataURL(file);
        }

        // 显示预览与参数区，隐藏空状态占位图。
        function showPreview() {
            previewEmpty.classList.add('hidden');
            previewCanvases.classList.remove('hidden');
            modeCard.classList.remove('hidden');
            settingsCard.classList.remove('hidden');
            exportCard.classList.remove('hidden');
            uploadZone.style.borderColor = '#1A237E';
        }

        // 切换算法模式：更新 tab 样式和参数面板，并触发重算。
        function switchMode(mode) {
            currentMode = mode;

            // 激活态样式切换。
            tabButtons.forEach(btn => {
                if (btn.getAttribute('data-mode') === mode) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            });

            // 只显示当前模式的参数区。
            document.getElementById('line-params').classList.add('hidden');
            document.getElementById('canny-params').classList.add('hidden');
            document.getElementById('raster-params').classList.add('hidden');
            document.getElementById(`${mode}-params`).classList.remove('hidden');

            if (uploadedImage) {
                processImage();
            }
        }

        // 根据当前模式计算并渲染预览图。
        function processImage() {
            if (!uploadedImage) return;

            // 显示处理中状态，防止用户误以为页面无响应。
            processingIndicator.classList.remove('hidden');

            const img = new Image();
            img.onload = function () {
                // 原图与效果图 canvas 尺寸保持一致，防止拉伸失真。
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

                // 先绘制原图。
                originalCtx.drawImage(img, 0, 0);

                // Canny 预览走后端接口，确保与最终导出效果一致。
                if (currentMode === 'canny') {
                    processingIndicator.classList.add('hidden');
                    fetchCannyPreviewDebounced();
                    return;
                }

                // 获取像素数据供前端算法处理。
                const imageData = originalCtx.getImageData(0, 0, img.width, img.height);
                const processedData = processedCtx.createImageData(img.width, img.height);

                if (currentMode === 'line') {
                    // line 模式走前端快速二值化预览。
                    applyLineProcessing(imageData, processedData, parseInt(linePrecisionSlider.value, 10));
                } else if (currentMode === 'raster') {
                    // raster 预览走后端，保证所见即所得。
                    processingIndicator.classList.add('hidden');
                    fetchRasterPreviewDebounced();
                    return;
                }

                processedCtx.putImageData(processedData, 0, 0);
                processingIndicator.classList.add('hidden');
            };

            img.src = uploadedImage;
        }

        // 前端 line 模式的简化二值化处理。
        function applyLineProcessing(input, output, precision) {
            // precision 0-100 映射到阈值区间 255-0。
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

        // 预留的前端 Canny 示例算法（当前主流程实际走后端预览）。
        function applyCannyProcessing(input, output, low, high) {
            const width = input.width;
            const height = input.height;

            // 先转灰度，降低后续计算复杂度。
            const gray = new Uint8Array(width * height);
            for (let i = 0; i < input.data.length; i += 4) {
                gray[i / 4] = (input.data[i] + input.data[i + 1] + input.data[i + 2]) / 3;
            }

            // 使用 Sobel 算子计算梯度幅值。
            for (let y = 1; y < height - 1; y++) {
                for (let x = 1; x < width - 1; x++) {
                    const idx = y * width + x;

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

        // 预留的前端 Raster 二值化示例（当前主流程实际走后端预览）。
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

        // 防抖：在短时间连续触发时只执行最后一次，降低接口压力。
        function debounce(fn, delay) {
            let timer;
            return function (...args) {
                clearTimeout(timer);
                timer = setTimeout(() => fn.apply(this, args), delay);
            };
        }

        // 请求后端 Canny 预览图（与后端导出算法参数对齐）。
        function fetchCannyPreview() {
            if (!uploadedFile) return;

            processingIndicator.classList.remove('hidden');

            const formData = new FormData();
            formData.append('image', uploadedFile, uploadedFile.name);
            formData.append('mode', 'canny');
            formData.append('canny_low', cannyLowSlider.value);
            formData.append('canny_high', cannyHighSlider.value);
            formData.append('canny_contrast_boost', (parseInt(cannyContrastBoostSlider.value, 10) / 10).toFixed(1));

            fetch('/api/preview', {
                method: 'POST',
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                if (data.preview) {
                    // 后端返回 DataURL，加载后绘制到处理结果 canvas。
                    const previewImg = new Image();
                    previewImg.onload = function () {
                        processedCanvas.width = previewImg.width;
                        processedCanvas.height = previewImg.height;
                        processedCanvas.style.maxWidth = '100%';
                        processedCanvas.style.height = 'auto';
                        processedCanvas.getContext('2d').drawImage(previewImg, 0, 0);
                    };
                    previewImg.src = data.preview;
                }
            })
            .catch(() => {
                // 预览失败时保持静默，避免频繁参数拖动时弹窗打断体验。
            })
            .finally(() => {
                processingIndicator.classList.add('hidden');
            });
        }

        // Canny 预览防抖版。
        const fetchCannyPreviewDebounced = debounce(fetchCannyPreview, 400);

        // 请求后端 Raster 预览图（与导出逻辑保持一致）。
        function fetchRasterPreview() {
            if (!uploadedFile) return;

            processingIndicator.classList.remove('hidden');

            const formData = new FormData();
            formData.append('image', uploadedFile, uploadedFile.name);
            formData.append('mode', 'raster');
            formData.append('raster_row_spacing', rasterRowSpacingSlider.value);
            formData.append('raster_white_threshold', rasterWhiteThresholdSlider.value);
            formData.append('raster_contrast_boost', (parseInt(rasterContrastBoostSlider.value, 10) / 10).toFixed(1));

            fetch('/api/preview', { method: 'POST', body: formData })
            .then(res => res.json())
            .then(data => {
                if (data.preview) {
                    const previewImg = new Image();
                    previewImg.onload = function () {
                        processedCanvas.width = previewImg.width;
                        processedCanvas.height = previewImg.height;
                        processedCanvas.style.maxWidth = '100%';
                        processedCanvas.style.height = 'auto';
                        processedCanvas.getContext('2d').drawImage(previewImg, 0, 0);
                    };
                    previewImg.src = data.preview;
                }
            })
            .catch(() => {
                // 与 Canny 预览同策略：失败时静默。
            })
            .finally(() => {
                processingIndicator.classList.add('hidden');
            });
        }

        // Raster 预览防抖版。
        const fetchRasterPreviewDebounced = debounce(fetchRasterPreview, 400);

        // 暴露给模板按钮 onclick 使用的导出函数。
        window.exportFile = function (format) {
            // 展示处理中状态。
            processingIndicator.classList.remove('hidden');

            // 用 FormData 打包图片与所有参数，发送给后端生成刺绣文件。
            const formData = new FormData();
            formData.append('image', uploadedFile, uploadedFile ? uploadedFile.name : 'upload.png');
            formData.append('format', format);
            formData.append('mode', currentMode);

            // 通用刺绣参数。
            const targetWidth = document.getElementById('target-width');
            const minStitchLen = document.getElementById('min-stitch-len');
            const maxStitchLen = document.getElementById('max-stitch-len');
            formData.append('target_width_mm', targetWidth ? targetWidth.value : '100');
            formData.append('min_stitch_len_mm', minStitchLen ? minStitchLen.value : '0.8');
            formData.append('max_stitch_len_mm', maxStitchLen ? maxStitchLen.value : '6.0');

            // 各模式参数全部上传，由后端按 mode 选择性使用。
            formData.append('line_precision', linePrecisionSlider.value);
            formData.append('line_contrast_boost', (parseInt(lineContrastBoostSlider.value, 10) / 10).toFixed(1));
            formData.append('canny_low', cannyLowSlider.value);
            formData.append('canny_high', cannyHighSlider.value);
            formData.append('canny_contrast_boost', (parseInt(cannyContrastBoostSlider.value, 10) / 10).toFixed(1));
            formData.append('raster_row_spacing', rasterRowSpacingSlider.value);
            formData.append('raster_white_threshold', rasterWhiteThresholdSlider.value);
            formData.append('raster_contrast_boost', (parseInt(rasterContrastBoostSlider.value, 10) / 10).toFixed(1));

            const rasterMinStep = document.getElementById('raster-min-stitch');
            const rasterMaxStep = document.getElementById('raster-max-stitch');
            formData.append('raster_min_stitch', rasterMinStep ? rasterMinStep.value : '2');
            formData.append('raster_max_stitch', rasterMaxStep ? rasterMaxStep.value : '12');

            fetch('/api/export', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Export failed');
                }

                // 后端返回二进制文件流（Blob）。
                return response.blob();
            })
            .then(blob => {
                // 使用临时对象 URL 触发浏览器下载。
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
                showMessageModal('Error', 'Export failed: ' + error.message);
            })
            .finally(() => {
                processingIndicator.classList.add('hidden');
            });
        };
    })();
});