document.addEventListener('DOMContentLoaded', () => {
    const togglePwdBtn = document.getElementById('toggle-password');
    const passwordInput = document.getElementById('password');
    const loginForm = document.getElementById('login-form');

    if (togglePwdBtn && passwordInput) {
        togglePwdBtn.addEventListener('click', () => {
            const isPassword = passwordInput.type === 'password';
            
            // Toggle input type
            passwordInput.type = isPassword ? 'text' : 'password';
            
            // Toggle icon
            const icon = togglePwdBtn.querySelector('i');
            if (icon) {
                icon.className = isPassword ? 'fa-regular fa-eye-slash' : 'fa-regular fa-eye';
            }
        });
    }

    if (loginForm) {
        loginForm.addEventListener('submit', () => {
            const btn = loginForm.querySelector('.btn-primary');
            // Visual feedback for submission
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Logging in...';
            // We don't preventDefault so the form will actually submit to the backend
        });
    }

    window.addEventListener('pageshow', (event) => {
        if (event.persisted && loginForm) {
            const btn = loginForm.querySelector('.btn-primary');
            if (btn) btn.innerHTML = 'Login';
        }
    });
});
