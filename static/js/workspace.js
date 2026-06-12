document.addEventListener('DOMContentLoaded', function () { //等html页面加载完之后在执行下面内容
    (function () {
        let uploadedImage = null; //自定义变量，保存的是图片dataurl，给前端
        let uploadedFile = null; //用户上传的图片文件相关信息，给后端
        let currentMode = 'canny'; //当前处理模式，默认值
        let lastPreviewDataUrl = null; //最后一次生成预览图
        let isPreviewLoading = false; //布尔，当前是否正在生成浏览图，没生成完就不能导出png
        let previewRequestId = 0; //防止旧请求覆盖新请求，所以每次加1
        let cannyAutoThresholds = true; //是否在用自动开关，默认是开启
        let currentTargetWidthMm = 100; //目标宽度
        const MAX_UPLOAD_SIZE_MB = 10; //常量
        const MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024; //将文件换成字节转换单位
        const SIZE_OPTION_WIDTHS = { //不同尺寸选项对应不同大小
            small: 100,
            medium: 100,
            big: 100
        };

        //检查是否登录，拦截未登录
        function requireAuthenticatedWorkspaceAction() { 
            if (window.appAuthState && window.appAuthState.authenticated) {
                return false; //全局访问，一个是对象里面会包含属性，一个是登录状态属性
            }

            if (typeof window.showLoginRequiredModal === 'function') {
                window.showLoginRequiredModal(); //判断是否存在弹窗函数，有就调用
            }
            return true;
        }

        //显示错误弹窗
        function showMessageModal(message) { 
            const modal = document.getElementById('error-modal'); //弹窗框
            const msgEl = document.getElementById('error-modal-message');//弹窗内容
            const okBtn = document.getElementById('error-modal-ok');//弹窗确认按钮
            const closeBtn = document.getElementById('error-modal-close');//关闭按钮

            if (!modal || !okBtn || !msgEl) return; //只要有一个没找到就结束，

            msgEl.textContent = message; //传入的文字就为弹窗内容
            modal.classList.remove('hidden'); //平常是隐藏，这里是去除隐藏

            const hide = () => modal.classList.add('hidden');
            okBtn.onclick = hide; //把函数交给按钮，等点击时执行
            if (closeBtn) closeBtn.onclick = hide; //判断是否同时有关闭键，有也是点击执行关闭
        }

        const fileInput = document.getElementById('file-input'); //通过id在html找到这个变量，存储进去，文件上传区
        const uploadZone = document.getElementById('upload-zone'); //上传区域，用户点击或拖拽图片到这里来上传
        const originalCanvas = document.getElementById('original-canvas');//原图画布，显示用户上传的图片
        const processedCanvas = document.getElementById('processed-canvas');//处理后画布，显示生成的预览图
        const previewEmpty = document.getElementById('preview-empty');//还没上传时的空区域
        const previewCanvases = document.getElementById('preview-canvases');//显示前后的预览区，没上传是隐藏的
        const processingIndicator = document.getElementById('processing-indicator');//生成预览时，会显示加载中
        const patternMetrics = document.getElementById('pattern-metrics');//显示预览图的相关数据，针数，跳针

        const modeCard = document.getElementById('mode-card'); //模式选择卡
        const settingsCard = document.getElementById('settings-card');//参数设置卡
        const exportCard = document.getElementById('export-card');//导出卡
        const tabButtons = document.querySelectorAll('.tab-button');//查看全部匹配的按钮
        const sizeOptionButtons = document.querySelectorAll('.size-option-button');//尺寸选项按钮

        const cannyLowSlider = document.getElementById('canny-low'); //低滑块
        const cannyLowValue = document.getElementById('canny-low-value');//低滑块数值显示
        const cannyHighSlider = document.getElementById('canny-high');//高滑块
        const cannyHighValue = document.getElementById('canny-high-value');//高滑块数值显示
        const cannyAutoThresholdsToggle = document.getElementById('canny-auto-thresholds');//自动阈值开关
        const rasterRowSpacingSlider = document.getElementById('raster-row-spacing'); //光栅行距滑块
        const rasterRowSpacingValue = document.getElementById('raster-row-spacing-value');//光栅行距数值显示
        const rasterWhiteThresholdSlider = document.getElementById('raster-white-threshold');//白色阈值滑块
        const rasterWhiteThresholdValue = document.getElementById('raster-white-threshold-value');//数值显示
        const rasterContrastBoostSlider = document.getElementById('raster-contrast-boost');//对比度增强滑块
        const rasterContrastBoostValue = document.getElementById('raster-contrast-boost-value');//对比度数值

        //给滑块设计背景颜色
        function updateSliderBackground(slider) {
            const percentage = ((slider.value - slider.min) / (slider.max - slider.min)) * 100;
            slider.style.setProperty('--value', percentage + '%');//滑块里的风格里的自带函数，根据百分比调整颜色
        }

        //安全设计滑块的值，同时更新显示数字和背景颜色
        function setSliderValue(slider, valueDisplay, value) { //滑块，显示的数值，设置的值
            const numericValue = Number(value); //将传进来的值转换成数字
            if (!Number.isFinite(numericValue)) return; //自带函数，是否是一个正常的数值，布尔值。如不是，返回结束

            const min = Number(slider.min); //取滑块最大值和最小
            const max = Number(slider.max); //四舍五入取大取小，防止接收到的数值不对，防止显示错误
            const clampedValue = Math.min(max, Math.max(min, Math.round(numericValue)));
            slider.value = String(clampedValue); //将这个值传给滑块，滑块移动到对应位置
            valueDisplay.textContent = String(clampedValue); //数值显示也更新
            updateSliderBackground(slider);//更新滑块背景颜色
        }

        function setCannyAutoThresholds(isAuto) { //设置是否使用自动阈值,看传入的布尔值
            cannyAutoThresholds = Boolean(isAuto); //再次将这个转成布尔值，防止出错，防御编程
            if (cannyAutoThresholdsToggle) { //如果有自动开关，就打开自动键
                cannyAutoThresholdsToggle.checked = cannyAutoThresholds;
            }
        }

        //更新对比度显示数值，滑块背景和数值显示。光栏法
        function updateContrastDisplay(slider, valueDisplay) {
            updateSliderBackground(slider);//将滑块的字符串数值转换成整数。保留一位小数并转成字符串
            valueDisplay.textContent = (parseInt(slider.value, 10) / 10).toFixed(1);
        }

        function updateTenthsDisplay(slider, valueDisplay) {
            updateSliderBackground(slider);
            valueDisplay.textContent = (parseInt(slider.value, 10) / 10).toFixed(1);
        }

        //有照片或拖拽，上传框保持高亮
        function syncUploadZoneState(isDragActive = false) {
            if (!uploadZone) return; //防御编程,如果没有上传区域就结束
            uploadZone.classList.toggle('upload-zone-active', isDragActive || Boolean(uploadedImage));
        }

        //选择尺寸
        function setSizeOption(option) { //方括号是传进来的尺寸，如没有接收到是中寸，防御
            currentTargetWidthMm = SIZE_OPTION_WIDTHS[option] || SIZE_OPTION_WIDTHS.medium;
            sizeOptionButtons.forEach(button => { 
                const isActive = button.dataset.sizeOption === option; //判断当前按钮是否是被选中
                button.classList.toggle('primary-bg', isActive);
                button.classList.toggle('text-white', isActive);
                button.classList.toggle('border-transparent', isActive);//选中，被高亮
                button.classList.toggle('bg-white', !isActive); //没选中
                button.classList.toggle('text-gray-700', !isActive);
                button.classList.toggle('border-gray-200', !isActive);
                button.classList.toggle('hover:bg-gray-50', !isActive);
            });
        }

        //切换模式，更新按钮的高亮和参数面板
        //这里是已经将模式传入，所以隐藏全部再移除隐藏。当在一个模式时，隐藏另一模式
        function applyModeUI(mode) {
            currentMode = mode; //记住当前模式

            tabButtons.forEach(btn => { //遍历全部的按钮
                if (btn.getAttribute('data-mode') === mode) { //如果当前按钮的属性等于当前模式
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active'); //为了只显示当前模式的样式
                }
            });

            document.getElementById('canny-params').classList.add('hidden');//找个元素隐藏起来
            document.getElementById('raster-params').classList.add('hidden');//隐藏全部参数内容
            document.getElementById(`${mode}-params`).classList.remove('hidden');//对应显示
        }

        //切换模式总入口，传入参数是模式，是否需要浏览
        function setMode(mode, shouldPreview) {
            applyModeUI(mode); //必做，更新对应的按钮样式
            if (shouldPreview && uploadedImage) { //浏览和已上传图片都完成，才进入
                requestPatternPreview();
            }
        }

        //在参数面板显示正确对应的数值。传入的是处理图像的相关设置数值
        function applySettings(settings) {
            if (!settings) return; //后端的数据是否为空，空就退出

            const nextMode = settings.mode || currentMode;//接收当前模式，并调用函数显示样式
            applyModeUI(nextMode);

            if (settings.canny_auto_thresholds !== undefined) { //自动键不是未定义，就调用
                setCannyAutoThresholds(settings.canny_auto_thresholds);//更新样式
            }

            const appliedCannyLow = settings.canny_resolved_low !== undefined
                ? settings.canny_resolved_low //自动值不是未定义，就将自动值存储到开头变量中
                : settings.canny_low;
            const appliedCannyHigh = settings.canny_resolved_high !== undefined
                ? settings.canny_resolved_high
                : settings.canny_high;
            if (appliedCannyLow !== undefined) { //阈值不是未定义，调用函数更新显示数值
                setSliderValue(cannyLowSlider, cannyLowValue, appliedCannyLow);
            }
            if (appliedCannyHigh !== undefined) {
                setSliderValue(cannyHighSlider, cannyHighValue, appliedCannyHigh);
            }
            if (settings.raster_row_spacing !== undefined) {
                rasterRowSpacingSlider.value = settings.raster_row_spacing;//滑块位置
                rasterRowSpacingValue.textContent = settings.raster_row_spacing;//显示数值
                updateSliderBackground(rasterRowSpacingSlider);//滑块颜色
            }
            if (settings.raster_white_threshold !== undefined) { 
                rasterWhiteThresholdSlider.value = settings.raster_white_threshold;
                rasterWhiteThresholdValue.textContent = settings.raster_white_threshold;
                updateSliderBackground(rasterWhiteThresholdSlider);
            }
            if (settings.raster_contrast_boost !== undefined) {
                rasterContrastBoostSlider.value = String(Math.round(settings.raster_contrast_boost * 10));
                updateContrastDisplay(rasterContrastBoostSlider, rasterContrastBoostValue);
            }//后端是小数，页面扩大十倍显示，四舍五入数值
        }

        //预览请求，判断是否用户登录
        function requestPatternPreview() {
            if (requireAuthenticatedWorkspaceAction()) return;
            if (!uploadedImage) return; //没图退出函数，有图就下面

            processingIndicator.classList.remove('hidden');//里面是加载图像，移除隐藏

            //异步加载，回调
            const img = new Image();
            img.onload = function () {//加载完后要做的事情，执行函数。回调函数
                originalCanvas.width = img.width; //画布
                originalCanvas.height = img.height;
                originalCanvas.style.maxWidth = '100%';
                originalCanvas.style.height = 'auto';

                processedCanvas.width = img.width; //浏览的画布
                processedCanvas.height = img.height;
                processedCanvas.style.maxWidth = '100%';
                processedCanvas.style.height = 'auto';

                const originalCtx = originalCanvas.getContext('2d');
                const processedCtx = processedCanvas.getContext('2d');
                originalCtx.drawImage(img, 0, 0);
                processedCtx.clearRect(0, 0, processedCanvas.width, processedCanvas.height);

                processingIndicator.classList.add('hidden');
                fetchPatternPreviewDebounced();
            };
            img.src = uploadedImage;//图像dataurl赋给属性，并浏览器解析这张图片
        }

        //将数据传给后端
        function appendEmbroiderySettings(formData) {
            formData.append('target_width_mm', String(currentTargetWidthMm));
            formData.append('canny_low', cannyLowSlider.value);
            formData.append('canny_high', cannyHighSlider.value);
            formData.append('canny_auto_thresholds', cannyAutoThresholds ? '1' : '0');
            formData.append('raster_row_spacing', rasterRowSpacingSlider.value);
            formData.append('raster_white_threshold', rasterWhiteThresholdSlider.value);
            formData.append('raster_contrast_boost', (parseInt(rasterContrastBoostSlider.value, 10) / 10).toFixed(1));
        }

        //将后端的图片放到画布上。新建图片容器，等图片加载好了开始做
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

        function renderPatternMetrics(metrics, truncated, maxStitches) {
            if (!patternMetrics || !metrics) return;

            const truncatedMessage = truncated
                ? `<div class="text-red-600">Pattern was truncated at ${maxStitches || 'the stitch limit'} stitches.</div>`
                : '';

            patternMetrics.innerHTML = `
                <div>Stitches: ${metrics.stitch_count || 0}</div>
                <div>Jumps: ${metrics.jump_count || 0}</div>
                <div>Trims: ${metrics.trim_count || 0}</div>
                ${truncatedMessage}
            `;
            patternMetrics.classList.remove('hidden');
        }

        function clearPatternMetrics() {
            if (!patternMetrics) return;
            patternMetrics.classList.add('hidden');
            patternMetrics.innerHTML = '';
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

        //防抖函数，传入执行的函数，和等待时间
        function debounce(fn, delay) {
            let timer;

            function debounced(...args) {//剩余参数，不管多少个参数，全部放进去
                clearTimeout(timer); //清空上一个时间
                timer = setTimeout(() => fn.apply(this, args), delay);
            }//定一个新的闹钟，等待时间执行,把全部的参数传入

            debounced.cancel = function () { //取消还没响的闹钟
                clearTimeout(timer);
                timer = null;
            };

            return debounced;
        }

        //生成预览图的核心函数，把图片和参数传给后端，返回预览图到页面
        function fetchPatternPreview() {
            if (requireAuthenticatedWorkspaceAction()) return;
            if (!uploadedFile) return;

            const requestId = ++previewRequestId;//自增，生成浏览图都增加，防止覆盖
            isPreviewLoading = true; //正在生成预览图
            lastPreviewDataUrl = null; //最后生成预览图等于空
            processingIndicator.classList.remove('hidden');

            const formData = new FormData();//创建新表单。加入标签，上传内容，文件名
            formData.append('image', uploadedFile, uploadedFile.name);
            formData.append('mode', currentMode); 
            appendEmbroiderySettings(formData);

            fetch('/api/preview', { //发请求到后端接口，生成预览图
                method: 'POST',
                body: formData
            })
                .then(async response => { //成功。后端返回的内容存储到这个变量里
                    if (response.status === 401) { //返回未登录，没有就展示弹窗
                        if (typeof window.showLoginRequiredModal === 'function') {
                            window.showLoginRequiredModal();//防御。判断是否存在正确，再调用
                        }
                        return null;//未登录退出
                    }

                    //从右开始，先获得并翻译变量，会返回承诺，所以要加上等待，等到获取完再存储
                    const data = await response.json();//接收错误或正确信息
                    if (!response.ok) {//这里查看变量的属性，也就是看后端返回的数值。
                        throw new Error(data.error || 'Preview failed'); 
                    }//错误就进入语句，从后端得错误信息，存储在新建错误对象，扔给下面
                    return data;
                })
                .then(data => { //防止被覆盖，所以要判断是否最新图片
                    if (requestId !== previewRequestId) return;//不相等会进入并退出
                    if (!data) return; //为空就退出
                    if (data.applied_settings) { //有参数就运行，去更新
                        applySettings(data.applied_settings);//将后端得到的设置
                    }
                    if (data.preview) { //有预览图就显示
                        lastPreviewDataUrl = data.preview;
                        renderPreview(data.preview);//将预览图用画布展示
                    } //显示刺绣的数值，针数，跳针，剪线等
                    renderPatternMetrics(data.metrics, data.truncated, data.max_stitches);
                })
                .catch(error => { //失败，出错。错误数据存在变量里。调用对应错误弹窗
                    if (requestId !== previewRequestId) return;
                    showMessageModal('Preview failed: ' + error.message);
                })
                .finally(() => { //都要执行。查看请求是否最新。为了关闭加载状态
                    if (requestId !== previewRequestId) return;
                    isPreviewLoading = false; //不在生成预览图，隐藏图标
                    processingIndicator.classList.add('hidden');
                });
        }

        //将生成预览图函数做防抖处理，放进前面的函数
        const fetchPatternPreviewDebounced = debounce(fetchPatternPreview, 400);

        function showPreview() {
            previewEmpty.classList.add('hidden');
            previewCanvases.classList.remove('hidden');
            modeCard.classList.remove('hidden');
            settingsCard.classList.remove('hidden');
            exportCard.classList.remove('hidden');
            syncUploadZoneState();
        }

        //拖动滑块。加入监听器，监听是否滑动，更新颜色显示数字，
        function setupSlider(slider, valueDisplay) {
            slider.addEventListener('input', function () {
                updateSliderBackground(this);
                valueDisplay.textContent = this.value;//将当前值写入文本
                if (uploadedImage) {
                    requestPatternPreview();
                }
            });
        }

        //滑块移动。就给自动开关传入假就为关闭自动开关，如果图片上传，重新更新
        function setupCannySlider(slider, valueDisplay) {
            slider.addEventListener('input', function () {
                setCannyAutoThresholds(false);
                setSliderValue(this, valueDisplay, this.value);
                if (uploadedImage) {
                    requestPatternPreview();
                }
            });
        }

        //检查格式，大小
        function handleFile(file) {
            if (requireAuthenticatedWorkspaceAction()) return;
            if (file.size > MAX_UPLOAD_SIZE_BYTES) {
                showMessageModal(`File size cannot exceed ${MAX_UPLOAD_SIZE_MB}MB. Please try again.`);
                return;//超过十内存
            }

            if (!['image/jpeg', 'image/png', 'image/bmp'].includes(file.type)) {
                showMessageModal('Only JPG, PNG, BMP formats are supported.');
                return;//限定格式
            }

            uploadedFile = file; //保存原始文件
            lastPreviewDataUrl = null;
            clearPatternMetrics();
            setCannyAutoThresholds(true);

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
                event.target.value = ''; //清空上次的内容
                return;
            }
            const file = event.target.files[0];//用户选的文件里面取第一个
            if (file) {
                handleFile(file);
            }
        }

        //点击上传区，如果登录就弹出文件选择窗口
        uploadZone.addEventListener('click', function () {
            if (requireAuthenticatedWorkspaceAction()) return;
            fileInput.click();
        });

        fileInput.addEventListener('change', handleFileUpload); //如果有变化，执行上面函数

        uploadZone.addEventListener('dragover', function (e) {
            e.preventDefault(); //阻止浏览器默认行为，拖进来会直接打开文件。要上传才打开
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

            const file = e.dataTransfer.files[0]; //上传的文件
            if (file && file.type.startsWith('image/')) {
                handleFile(file);
            }
        });

        tabButtons.forEach(button => { //查看每个按钮，加上监听
            button.addEventListener('click', function () {
                setMode(this.getAttribute('data-mode'), true);//更新按钮样式
            });
        });

        sizeOptionButtons.forEach(button => {
            button.addEventListener('click', function () {
                setSizeOption(this.dataset.sizeOption);
                if (uploadedImage) {
                    requestPatternPreview();
                }
            });
        });

        //加了事件监听，监听类型是改变
        if (cannyAutoThresholdsToggle) {
            cannyAutoThresholdsToggle.addEventListener('change', function () {
                setCannyAutoThresholds(this.checked); //回调函数，要是开了，就回来执行
                if (uploadedImage) { //如果上传了图片，更新更新预览图
                    fetchPatternPreviewDebounced.cancel();
                    fetchPatternPreview();
                }
            });
        }

        //滑块的监听
        setupCannySlider(cannyLowSlider, cannyLowValue);
        setupCannySlider(cannyHighSlider, cannyHighValue);
        setupSlider(rasterRowSpacingSlider, rasterRowSpacingValue);
        setupSlider(rasterWhiteThresholdSlider, rasterWhiteThresholdValue);

        rasterContrastBoostSlider.addEventListener('input', function () {
            updateContrastDisplay(this, rasterContrastBoostValue);
            if (uploadedImage) {
                requestPatternPreview();
            }
        });

        //根据样式
        updateSliderBackground(cannyLowSlider);
        updateSliderBackground(cannyHighSlider);
        updateSliderBackground(rasterRowSpacingSlider);
        updateSliderBackground(rasterWhiteThresholdSlider);
        updateContrastDisplay(rasterContrastBoostSlider, rasterContrastBoostValue);
        setSizeOption('medium');
        syncUploadZoneState();

        window.exportFile = function (format) {
            if (requireAuthenticatedWorkspaceAction()) return;
            if (!uploadedFile) {
                showMessageModal('Please upload an image first.');
                return;
            }

            processingIndicator.classList.remove('hidden');

            const formData = new FormData(); //需要发给后端的数据
            formData.append('image', uploadedFile, uploadedFile.name);
            formData.append('format', format);
            formData.append('mode', currentMode);
            appendEmbroiderySettings(formData); //加入参数

            fetch('/api/export', { //向后端请求
                method: 'POST',
                body: formData
            })
                .then(async response => {
                    if (response.status === 401) { //未登录，并检查弹窗是否存在
                        if (typeof window.showLoginRequiredModal === 'function') {
                            window.showLoginRequiredModal();
                        }
                        return null;
                    }
                    if (!response.ok) {//有错误进入。其他错误，为了给有用的错误提示
                        let message = 'Export failed';
                        try {
                            const data = await response.json();//查看错误原因并存储
                            message = data.error || message;
                        } catch (_) {
                            //出错了，运行这里。下划线是不关心错误内容，也不使用
                        }
                        throw new Error(message); //最后给出一个新的错误提示
                    }
                    return response.blob();//返回文件数据
                })
                //从后端得到的刺绣文件，真正的下载到用户电脑上
                .then(blob => {
                    if (!blob) return; //检查是否有文件，没有就退出
                    const url = URL.createObjectURL(blob);//给数据做了一个临时网址和元素
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `embroidery_design${format}`;
                    document.body.appendChild(a); //下载出现在网站中，并直接下载
                    a.click();
                    document.body.removeChild(a);//清理网站
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
