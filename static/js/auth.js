document.addEventListener('DOMContentLoaded', function() { //确保页面内容加载完成再运行

    // Authentication management
    (async function () {
        async function fetchAuthState() {
            try {
                const response = await fetch('/api/auth/me');
                if (!response.ok) {
                    return { authenticated: false, user: null };
                }
                return await response.json();
            } catch (_) {
                return { authenticated: false, user: null };
            }
        }

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

        async function checkAuth() {
            const authState = await fetchAuthState();
            applyAuthToNav(Boolean(authState.authenticated));
            return authState;
        }

        // Toggle user dropdown menu
        const userButton = document.getElementById('user-button');
        const dropdown = document.getElementById('dropdown');

        if (userButton && dropdown) {
            userButton.addEventListener('click', function (e) {
                e.stopPropagation();
                dropdown.classList.toggle('hidden');
            });

            // Close dropdown when clicking outside
            document.addEventListener('click', function () {
                if (dropdown && !dropdown.classList.contains('hidden')) {
                    dropdown.classList.add('hidden');
                }
            });
        }

        // Handle logout
        const logoutButton = document.getElementById('logout-button');
        if (logoutButton) {
            logoutButton.addEventListener('click', async function () {
                try {
                    await fetch('/api/auth/logout', { method: 'POST' });
                } catch (_) {
                    // Ignore network errors and still redirect.
                }
                window.location.href = '/';
            });
        }

        // 检查 workspace 页面的登录状态
        async function checkWorkspaceAuth(authState) {
            const loginModal = document.getElementById('login-modal');

            if (!authState.authenticated && loginModal) {
                // 显示登录弹窗
                loginModal.classList.remove('hidden');

                const closeLoginModal = function() {
                    loginModal.classList.add('hidden');
                };

                // 处理弹窗右上角关闭按钮
                const modalClose = document.getElementById('modal-close');
                if (modalClose) {
                    modalClose.addEventListener('click', function() {
                        closeLoginModal();
                    });
                }

                // 处理弹窗的"Cancel"按钮
                const modalCancel = document.getElementById('modal-cancel');
                if (modalCancel) {
                    modalCancel.addEventListener('click', function() {
                        closeLoginModal();
                    });
                }

                // 处理弹窗的"Login Now"按钮
                const modalLogin = document.getElementById('modal-login');
                if (modalLogin) {
                    modalLogin.addEventListener('click', function() {
                        window.location.href = '/login';  // 跳转到登录页
                    });
                }
            }
        }

        const authState = await checkAuth();
        await checkWorkspaceAuth(authState);
    })();
});