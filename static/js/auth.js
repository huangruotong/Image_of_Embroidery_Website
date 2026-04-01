// 在 DOM 完全就绪后再初始化，避免查询节点时拿到 null。
document.addEventListener('DOMContentLoaded', function() {

    // 使用 IIFE 隔离变量，避免污染全局作用域。
    (async function () {
        // 向后端查询当前会话的登录状态。
        async function fetchAuthState() {
            try {
                const response = await fetch('/api/auth/me');

                // 非 2xx 响应统一视为未登录，前端保持安全兜底。
                if (!response.ok) {
                    return { authenticated: false, user: null };
                }

                // 正常返回时，解析后端提供的认证状态 JSON。
                return await response.json();
            } catch (_) {
                // 网络异常或 JSON 解析异常时也按未登录处理，避免页面报错中断。
                return { authenticated: false, user: null };
            }
        }

        // 根据登录态更新导航区：已登录显示头像菜单，未登录显示 Login 链接。
        function applyAuthToNav(isLoggedIn) {
            const loginLink = document.getElementById('login-link');
            const userMenu = document.getElementById('user-menu');

            if (isLoggedIn) {
                if (loginLink) loginLink.classList.add('hidden');
                if (userMenu) userMenu.classList.remove('hidden');
            } else {
                if (loginLink) loginLink.classList.remove('hidden');
                if (userMenu) userMenu.classList.add('hidden');
            }
        }

        // 组合执行：先拉取登录态，再同步导航显示状态，并把状态返回给后续流程复用。
        async function checkAuth() {
            const authState = await fetchAuthState();
            applyAuthToNav(Boolean(authState.authenticated));
            return authState;
        }

        // 头像按钮与下拉菜单节点（不同页面可能不存在，因此都要判空）。
        const userButton = document.getElementById('user-button');
        const dropdown = document.getElementById('dropdown');

        if (userButton && dropdown) {
            // 点击头像切换下拉菜单可见性。
            userButton.addEventListener('click', function (e) {
                // 阻止冒泡，避免触发 document 点击事件后立刻被关闭。
                e.stopPropagation();
                dropdown.classList.toggle('hidden');
            });

            // 点击页面其他区域时自动收起下拉菜单。
            document.addEventListener('click', function () {
                if (dropdown && !dropdown.classList.contains('hidden')) {
                    dropdown.classList.add('hidden');
                }
            });
        }

        // 绑定退出登录动作。
        const logoutButton = document.getElementById('logout-button');
        if (logoutButton) {
            logoutButton.addEventListener('click', async function () {
                try {
                    // 通知后端销毁会话。
                    await fetch('/api/auth/logout', { method: 'POST' });
                } catch (_) {
                    // 即使网络异常也继续跳转，确保前端状态回到访客视图。
                }

                // 退出后统一回到首页。
                window.location.href = '/';
            });
        }

        // 仅在 Workspace 页有登录弹窗时生效：未登录则提示先登录。
        async function checkWorkspaceAuth(authState) {
            const loginModal = document.getElementById('login-modal');

            if (!authState.authenticated && loginModal) {
                // 展示登录提示弹窗。
                loginModal.classList.remove('hidden');

                // 抽取统一关闭逻辑，供多个按钮复用。
                const closeLoginModal = function() {
                    loginModal.classList.add('hidden');
                };

                // 右上角关闭按钮。
                const modalClose = document.getElementById('modal-close');
                if (modalClose) {
                    modalClose.addEventListener('click', function() {
                        closeLoginModal();
                    });
                }

                // Cancel 按钮。
                const modalCancel = document.getElementById('modal-cancel');
                if (modalCancel) {
                    modalCancel.addEventListener('click', function() {
                        closeLoginModal();
                    });
                }

                // Login Now 按钮：跳转登录页。
                const modalLogin = document.getElementById('modal-login');
                if (modalLogin) {
                    modalLogin.addEventListener('click', function() {
                        window.location.href = '/login';
                    });
                }
            }
        }

        // 页面初始化主流程：先更新导航登录态，再执行 workspace 专属检查。
        const authState = await checkAuth();
        await checkWorkspaceAuth(authState);
    })();
});