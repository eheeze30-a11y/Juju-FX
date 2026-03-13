// static/js/main.js - Main JavaScript functions

// Initialize tooltips
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Bootstrap tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
    });
    
    // Update current time every second
    updateCurrentTime();
    setInterval(updateCurrentTime, 1000);
    
    // Check server status
    checkServerStatus();
    
    // Load initial data if on dashboard
    if (window.location.pathname === '/') {
        loadInitialData();
    }
});

function updateCurrentTime() {
    const now = new Date();
    const timeString = now.toISOString().slice(0, 19).replace('T', ' ');
    const timeElement = document.getElementById('current-time');
    if (timeElement) {
        timeElement.textContent = timeString;
    }
}

async function checkServerStatus() {
    try {
        const response = await fetch('/health');
        const data = await response.json();
        
        const statusBadge = document.getElementById('server-status');
        if (statusBadge) {
            if (data.status === 'healthy') {
                statusBadge.innerHTML = '<i class="fas fa-check-circle"></i> Online';
                statusBadge.className = 'badge bg-success';
            } else {
                statusBadge.innerHTML = '<i class="fas fa-exclamation-circle"></i> Offline';
                statusBadge.className = 'badge bg-danger';
            }
        }
    } catch (error) {
        console.error('Server status check failed:', error);
    }
}

function loadInitialData() {
    // This will be called by dashboard-specific JS
    console.log('Dashboard loaded');
}

// Notification system
function showNotification(type, message, duration = 5000) {
    // Create notification container if it doesn't exist
    let container = document.getElementById('notification-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'notification-container';
        container.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 9999;';
        document.body.appendChild(container);
    }
    
    // Create notification
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show`;
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" onclick="this.parentElement.remove()"></button>
    `;
    notification.style.cssText = 'min-width: 300px; margin-bottom: 10px;';
    
    container.appendChild(notification);
    
    // Auto-remove after duration
    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, duration);
}

// Format currency
function formatCurrency(amount, currency = 'ZAR') {
    const formatter = new Intl.NumberFormat('en-ZA', {
        style: 'currency',
        currency: currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
    return formatter.format(amount);
}

// Format number with commas
function formatNumber(num) {
    return num.toLocaleString('en-ZA');
}

// Get color for P/L value
function getPLColor(value) {
    if (value > 0) return 'text-success';
    if (value < 0) return 'text-danger';
    return 'text-secondary';
}

// Debounce function for performance
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}