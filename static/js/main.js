// Theme toggle
(function() {
    const stored = localStorage.getItem('phub-theme');
    const theme = stored || 'dark';
    if (theme === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
    }

    document.addEventListener('DOMContentLoaded', () => {
        const btn = document.getElementById('theme-toggle');
        if (!btn) return;
        const updateIcon = () => {
            const isLight = document.documentElement.getAttribute('data-theme') === 'light';
            btn.textContent = isLight ? '☀️' : '🌙';
        };
        updateIcon();
        btn.addEventListener('click', () => {
            const isLight = document.documentElement.getAttribute('data-theme') === 'light';
            if (isLight) {
                document.documentElement.removeAttribute('data-theme');
                localStorage.setItem('phub-theme', 'dark');
            } else {
                document.documentElement.setAttribute('data-theme', 'light');
                localStorage.setItem('phub-theme', 'light');
            }
            updateIcon();
        });
    });
})();

// Global confirm dialog -intercepts form submits with data-confirm
(function() {
    let pendingForm = null;

    window.__closeGlobalConfirm = function() {
        document.getElementById('global-confirm-modal').style.display = 'none';
        pendingForm = null;
    };

    window.__confirmGlobalConfirm = function() {
        if (pendingForm) {
            pendingForm.setAttribute('data-confirmed', 'true');
            pendingForm.submit();
        }
        window.__closeGlobalConfirm();
    };

    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('form[data-confirm]').forEach(form => {
            form.addEventListener('submit', function(e) {
                if (form.getAttribute('data-confirmed') === 'true') return;
                e.preventDefault();
                pendingForm = form;
                document.getElementById('global-confirm-message').textContent = form.dataset.confirm || 'Are you sure?';
                document.getElementById('global-confirm-sub').textContent = form.dataset.confirmSub || '';
                document.getElementById('global-confirm-modal').style.display = 'flex';
            });
        });
    });
})();