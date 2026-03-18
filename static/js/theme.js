const themeToggle = document.getElementById('theme-toggle');
const themeIcon = document.querySelector('.theme-icon');

function applyTheme(theme) {
    document.body.classList.remove('light-mode', 'dark-mode');
    document.body.classList.add(`${theme}-mode`);
    localStorage.setItem('cyberpoa-theme', theme);
    if (theme === 'dark') {
        themeIcon.textContent = '☀️';
        themeToggle.setAttribute('aria-label', 'Switch to light mode');
    } else {
        themeIcon.textContent = '🌙';
        themeToggle.setAttribute('aria-label', 'Switch to dark mode');
    }
}

function loadTheme() {
    const saved = localStorage.getItem('cyberpoa-theme') || 'light';
    applyTheme(saved);
}

if (themeToggle) {
    themeToggle.addEventListener('click', () => {
        const current = document.body.classList.contains('dark-mode') ? 'dark' : 'light';
        const next = current === 'dark' ? 'light' : 'dark';
        applyTheme(next);
    });
}

loadTheme();
