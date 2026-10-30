document.addEventListener('DOMContentLoaded', () => {
    // Password Toggle Functionality
    const togglePwdBtns = document.querySelectorAll('.toggle-pwd-btn');
    
    togglePwdBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            // Find the input within the same input-field container
            const inputContainer = btn.closest('.input-field');
            const pwdInput = inputContainer.querySelector('input');
            const icon = btn.querySelector('i');
            
            if (pwdInput && icon) {
                const isPassword = pwdInput.type === 'password';
                pwdInput.type = isPassword ? 'text' : 'password';
                icon.className = isPassword ? 'fa-regular fa-eye-slash' : 'fa-regular fa-eye';
            }
        });
    });

    // Handle Form Submission
    // const registerForm = document.getElementById('register-form');
    
    // if (registerForm) {
    //     registerForm.addEventListener('submit', (e) => {
    //         e.preventDefault();
            
    //         // Password match validation
    //         const pwd = document.getElementById('password').value;
    //         const confirmPwd = document.getElementById('confirm-password').value;
            
    //         if (pwd !== confirmPwd) {
    //             alert("Passwords do not match!");
    //             return;
    //         }
            
    //         const btn = registerForm.querySelector('.btn-primary');
    //         const originalText = btn.innerHTML;
            
    //         // Visual feedback for simulated loading
    //         btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Registering...';
    //         btn.disabled = true;
            
    //         // Simulate registration delay
    //         setTimeout(() => {
    //             // Redirect back to login or dashboard
    //             window.location.href = 'index.html';
    //         }, 1000);
    //     });
    // }
});
