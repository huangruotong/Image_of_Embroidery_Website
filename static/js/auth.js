document.addEventListener('DOMContentLoaded', function () {
    (async function () {
        const loginModal = document.getElementById('login-modal');
        const modalClose = document.getElementById('modal-close');
        const modalCancel = document.getElementById('modal-cancel');
        const modalLogin = document.getElementById('modal-login');

        function showLoginRequiredModal() {
            if (!loginModal) return;
            loginModal.classList.remove('hidden');
        }

        function hideLoginRequiredModal() {
            if (!loginModal) return;
            loginModal.classList.add('hidden');
        }

        // Expose modal helpers so workspace-specific actions can reuse them.
        window.showLoginRequiredModal = showLoginRequiredModal;
        window.hideLoginRequiredModal = hideLoginRequiredModal;

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

        //根据登录态更新导航区，已登录显示用户图标，未登录显示login
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
            window.appAuthState = authState;
            applyAuthToNav(Boolean(authState.authenticated));
            document.dispatchEvent(new CustomEvent('auth-state-changed', {
                detail: authState
            }));
            return authState;
        }

        const userButton = document.getElementById('user-button');
        const dropdown = document.getElementById('dropdown');

        if (userButton && dropdown) {
            userButton.addEventListener('click', function (e) {
                e.stopPropagation();
                dropdown.classList.toggle('hidden');
            });

            document.addEventListener('click', function () {
                if (dropdown && !dropdown.classList.contains('hidden')) {
                    dropdown.classList.add('hidden');
                }
            });
        }

        const logoutButton = document.getElementById('logout-button');
        if (logoutButton) {
            logoutButton.addEventListener('click', async function () {
                try {
                    await fetch('/api/auth/logout', { method: 'POST' });
                } catch (_) {
                    // Ignore network errors and still redirect out.
                }
                window.location.href = '/';
            });
        }

        if (modalClose) {
            modalClose.addEventListener('click', function () {
                hideLoginRequiredModal();
            });
        }

        if (modalCancel) {
            modalCancel.addEventListener('click', function () {
                hideLoginRequiredModal();
            });
        }

        if (modalLogin) {
            modalLogin.addEventListener('click', function () {
                window.location.href = '/login';
            });
        }

        await checkAuth();
    })();
});
