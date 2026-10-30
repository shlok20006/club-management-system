document.addEventListener('DOMContentLoaded', () => {
    const navLinks = document.querySelectorAll('.nav-link[data-target]');
    const sections = document.querySelectorAll('.content-section');
    const pageTitle = document.getElementById('page-title');

    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();

            // Remove active from all links
            navLinks.forEach(nav => nav.classList.remove('active'));
            // Add active to clicked link
            link.classList.add('active');

            // Update Title
            pageTitle.style.opacity = 0;
            setTimeout(() => {
                pageTitle.textContent = link.getAttribute('data-title');
                pageTitle.style.opacity = 1;
            }, 150);

            // Hide all sections
            sections.forEach(sec => sec.classList.remove('active'));
            
            // Show target section
            const targetId = link.getAttribute('data-target');
            document.getElementById(targetId).classList.add('active');
        });
    });
});
