/**
 * Core Admin Panel — JavaScript utilities.
 * 
 * Minimal JS for admin interactions. 
 * Most interactivity handled by HTMX + Alpine.js.
 */

// Initialize Lucide icons on page load and after HTMX swaps
document.addEventListener('DOMContentLoaded', () => {
    if (window.lucide) lucide.createIcons();
});

document.addEventListener('htmx:afterSwap', () => {
    if (window.lucide) lucide.createIcons();
});

// Auto-dismiss success messages after 5 seconds
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-auto-dismiss]').forEach(el => {
        setTimeout(() => {
            el.style.opacity = '0';
            el.style.transition = 'opacity 0.3s ease';
            setTimeout(() => el.remove(), 300);
        }, 5000);
    });
});
