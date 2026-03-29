document.addEventListener('DOMContentLoaded', function() { //确保页面内容加载完成再运行

    // Authentication management
    (function () {
        function checkAuth() {
            const isLoggedIn = localStorage.getItem('isLoggedIn') === 'true';
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
            logoutButton.addEventListener('click', function () {
                localStorage.removeItem('isLoggedIn');
                localStorage.removeItem('userEmail');
                window.location.href = '/';
            });
        }

        // 检查 workspace 页面的登录状态
        function checkWorkspaceAuth() {
            const isLoggedIn = localStorage.getItem('isLoggedIn') === 'true';
            const loginModal = document.getElementById('login-modal');

            if (!isLoggedIn && loginModal) {
                // 显示登录弹窗
                loginModal.classList.remove('hidden');

                // 处理弹窗的"Cancel"按钮
                const modalCancel = document.getElementById('modal-cancel');
                if (modalCancel) {
                    modalCancel.addEventListener('click', function() {
                        loginModal.classList.add('hidden');
                        window.location.href = '/';  // 返回首页
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

        // 调用 workspace 检查
        checkWorkspaceAuth();

        // Initialize auth state
        checkAuth();
    })();
});