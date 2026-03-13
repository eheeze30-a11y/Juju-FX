// static/js/dashboard.js - Dashboard with debounced level changes

let performanceChart = null;
let pairChart = null;
let refreshInterval = null;
let lastLevelChangeTime = 0;
let levelChangeDebounce = 2000; // 2 second debounce
let currentLevel = 0;

document.addEventListener('DOMContentLoaded', function() {
    console.log('Juju FX Dashboard Initializing...');
    
    // Load all dashboard data
    loadDashboardData();
    
    // Set up auto-refresh every 30 seconds
    refreshInterval = setInterval(loadDashboardData, 30000);
    
    // Set up event listeners
    setupEventListeners();
    
    // Update current level display immediately
    updateCurrentLevelDisplay();
    
    // Check server connection
    checkServerConnection();
});

function setupEventListeners() {
    // Period buttons
    document.querySelectorAll('[data-period]').forEach(btn => {
        btn.addEventListener('click', function() {
            const period = this.getAttribute('data-period');
            loadPerformanceData(period);
            
            // Update active state
            document.querySelectorAll('[data-period]').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
        });
    });
    
    // Level buttons - Add debounce
    document.querySelectorAll('.level-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const level = parseInt(this.getAttribute('data-level'));
            debouncedSetLevel(level);
        });
    });
    
    // Refresh button
    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            console.log('Manual refresh triggered');
            loadDashboardData();
            showNotification('info', 'Refreshing dashboard data...', 2000);
        });
    }
    
    // Export button
    const exportBtn = document.getElementById('export-btn');
    if (exportBtn) {
        exportBtn.addEventListener('click', exportDashboardData);
    }
    
    // View all trades button
    const viewAllTradesBtn = document.getElementById('view-all-trades');
    if (viewAllTradesBtn) {
        viewAllTradesBtn.addEventListener('click', function() {
            window.location.href = '/trades';
        });
    }
}

function debouncedSetLevel(level) {
    const now = Date.now();
    
    // Check if we're clicking too fast
    if (now - lastLevelChangeTime < levelChangeDebounce) {
        const timeLeft = Math.ceil((levelChangeDebounce - (now - lastLevelChangeTime)) / 1000);
        showNotification('warning', `Please wait ${timeLeft} second(s) before changing level again`);
        return;
    }
    
    // Check if this is the same level (prevent accidental double-clicks)
    const currentDisplayLevel = parseInt(document.getElementById('current-level-display')?.textContent || '0');
    if (level === currentDisplayLevel) {
        showNotification('info', `Already at Level ${level}`);
        return;
    }
    
    lastLevelChangeTime = now;
    setLevel(level);
}

async function loadDashboardData() {
    try {
        showLoadingState(true);
        console.log('Loading dashboard data...');
        
        // Load all data in parallel
        const [summary, recentTrades, levels, performance] = await Promise.all([
            fetch('/api/dashboard/summary').then(r => r.json()),
            fetch('/api/trades/recent').then(r => r.json()),
            fetch('/api/performance/levels').then(r => r.json()),
            fetch('/api/performance/day').then(r => r.json())
        ]);
        
        console.log('Dashboard data loaded:', {
            summaryTrades: summary.summary?.all?.trades || 0,
            recentTradesCount: recentTrades.trades?.length || 0,
            levelsCount: Object.keys(levels.levels || {}).length
        });
        
        // Update all dashboard sections
        updateSummaryCards(summary);
        updateRecentTradesTable(recentTrades);
        updateLevelPerformance(levels);
        updatePerformanceChart('day', performance); // Load with data
        
        showLoadingState(false);
        
        // Update current level display
        updateCurrentLevelDisplay();
        
    } catch (error) {
        console.error('Error loading dashboard data:', error);
        showNotification('error', 'Failed to load dashboard data. Check server connection.');
        showLoadingState(false);
    }
}

async function loadPerformanceData(period = 'day') {
    try {
        console.log(`Loading performance data for period: ${period}`);
        const response = await fetch(`/api/performance/${period}`);
        const data = await response.json();
        updatePerformanceChart(period, data);
    } catch (error) {
        console.error('Error loading performance data:', error);
        showNotification('error', 'Failed to load performance data');
    }
}

function updateSummaryCards(summary) {
    if (!summary || !summary.summary) {
        console.warn('No summary data available');
        return;
    }
    
    // Today's P/L
    const today = summary.summary.all || {};
    document.getElementById('today-pl').textContent = formatCurrency(today.pnl_zar || 0);
    document.getElementById('today-change').textContent = 
        `${today.trades || 0} trades • ${(today.win_rate || 0).toFixed(1)}% win rate`;
    document.getElementById('today-pl').className = `stat-value ${getPLColor(today.pnl_zar || 0)}`;
    
    // Weekly P/L (using all data for now)
    document.getElementById('weekly-pl').textContent = formatCurrency(today.pnl_zar || 0);
    document.getElementById('weekly-change').textContent = 
        `${today.trades || 0} trades • ${(today.win_rate || 0).toFixed(1)}% win rate`;
    document.getElementById('weekly-pl').className = `stat-value ${getPLColor(today.pnl_zar || 0)}`;
    
    // Monthly P/L (using all data for now)
    document.getElementById('monthly-pl').textContent = formatCurrency(today.pnl_zar || 0);
    document.getElementById('monthly-change').textContent = 
        `${today.trades || 0} trades • ${(today.win_rate || 0).toFixed(1)}% win rate`;
    document.getElementById('monthly-pl').className = `stat-value ${getPLColor(today.pnl_zar || 0)}`;
    
    // Overall win rate
    document.getElementById('win-rate').textContent = `${(today.win_rate || 0).toFixed(1)}%`;
    document.getElementById('total-trades').textContent = `${today.trades || 0} total trades`;
}

function updateRecentTradesTable(tradesData) {
    const tbody = document.getElementById('recent-trades-body');
    if (!tbody) {
        console.warn('Recent trades table body not found');
        return;
    }
    
    if (!tradesData.trades || tradesData.trades.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="text-center py-4 text-muted">
                    <i class="fas fa-chart-line fa-2x mb-3"></i><br>
                    No trades recorded yet
                </td>
            </tr>
        `;
        return;
    }
    
    let html = '';
    tradesData.trades.forEach(trade => {
        const plClass = trade.profit_usd > 0 ? 'trade-row-win' : 
                       trade.profit_usd < 0 ? 'trade-row-loss' : 'trade-row-even';
        
        // Format the time display
        let timeDisplay = trade.formatted_time || trade.close_time || 'N/A';
        if (timeDisplay.length > 16) {
            timeDisplay = timeDisplay.substring(0, 16);
        }
        
        html += `
            <tr class="${plClass}">
                <td class="small">${timeDisplay}</td>
                <td><strong>${trade.symbol || 'Unknown'}</strong></td>
                <td><span class="badge ${trade.type === 'buy' ? 'bg-success' : 'bg-danger'}">
                    ${(trade.type || '').toUpperCase()}
                </span></td>
                <td class="text-center">${(trade.volume || 0).toFixed(2)}</td>
                <td class="text-center"><span class="badge bg-secondary">${trade.level || 0}</span></td>
                <td class="${getPLColor(trade.profit_usd || 0)}">$${(trade.profit_usd || 0).toFixed(2)}</td>
                <td class="${getPLColor(trade.profit_zar || 0)}">${formatCurrency(trade.profit_zar || 0)}</td>
            </tr>
        `;
    });
    
    tbody.innerHTML = html;
    
    // Update "View All" button text
    const viewAllBtn = document.getElementById('view-all-trades');
    if (viewAllBtn) {
        viewAllBtn.textContent = `View All ${tradesData.trades.length}+ Trades`;
    }
}

function updateLevelPerformance(levelsData) {
    const container = document.getElementById('level-pl-container');
    if (!container) {
        console.warn('Level performance container not found');
        return;
    }
    
    if (!levelsData.levels || Object.keys(levelsData.levels).length === 0) {
        container.innerHTML = `
            <div class="col-12 text-center py-4 text-muted">
                <i class="fas fa-layer-group fa-2x mb-3"></i><br>
                No level performance data available
            </div>
        `;
        return;
    }
    
    let html = '<div class="row">';
    
    // Sort levels 0-6
    const sortedLevels = Object.keys(levelsData.levels)
        .sort((a, b) => parseInt(a) - parseInt(b))
        .map(key => ({ level: key, ...levelsData.levels[key] }));
    
    sortedLevels.forEach(level => {
        const isActive = level.level == currentLevel;
        const activeClass = isActive ? 'border-primary shadow-sm' : '';
        const plClass = getPLColor(level.pnl_zar || 0);
        
        html += `
            <div class="col-6 col-md-4 col-lg-2 mb-3">
                <div class="card h-100 ${activeClass}">
                    <div class="card-body text-center p-2">
                        <div class="small text-muted">Level ${level.level}</div>
                        <div class="h5 mb-1 ${plClass}">${formatCurrency(level.pnl_zar || 0)}</div>
                        <div class="small text-muted">
                            ${level.trades || 0} trades<br>
                            ${(level.win_rate || 0).toFixed(1)}% win rate
                        </div>
                        ${isActive ? '<span class="badge bg-primary mt-1">Active</span>' : ''}
                    </div>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    container.innerHTML = html;
}

function updatePerformanceChart(period, data) {
    const ctx = document.getElementById('performanceChart');
    if (!ctx) {
        console.warn('Performance chart canvas not found');
        return;
    }
    
    // Destroy existing chart
    if (performanceChart) {
        performanceChart.destroy();
    }
    
    // If no data, show empty chart
    if (!data) {
        performanceChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'No data available',
                    data: [],
                    borderColor: '#ccc',
                    backgroundColor: 'transparent',
                    borderWidth: 2
                }]
            },
            options: getChartOptions('No Data')
        });
        return;
    }
    
    // Prepare data
    const labels = Object.keys(data.hourly_pnl || {});
    const values = Object.values(data.hourly_pnl || {});
    
    // Create gradient
    const gradient = ctx.getContext('2d').createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(67, 97, 238, 0.3)');
    gradient.addColorStop(1, 'rgba(67, 97, 238, 0.05)');
    
    performanceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: `P/L (ZAR) - ${data.period_name || period}`,
                data: values,
                borderColor: '#4361ee',
                backgroundColor: gradient,
                borderWidth: 3,
                fill: true,
                tension: 0.4,
                pointRadius: 4,
                pointBackgroundColor: '#4361ee',
                pointBorderColor: '#ffffff',
                pointBorderWidth: 2
            }]
        },
        options: getChartOptions(data.period_name || period)
    });
}

function getChartOptions(title) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                display: true,
                position: 'top'
            },
            tooltip: {
                callbacks: {
                    label: function(context) {
                        return `P/L: ${formatCurrency(context.raw)}`;
                    }
                }
            }
        },
        scales: {
            y: {
                beginAtZero: true,
                ticks: {
                    callback: function(value) {
                        return formatCurrency(value);
                    }
                },
                grid: {
                    color: 'rgba(0,0,0,0.05)'
                }
            },
            x: {
                grid: {
                    color: 'rgba(0,0,0,0.05)'
                }
            }
        }
    };
}

async function setLevel(level) {
    try {
        console.log(`Setting level to: ${level}`);
        
        // Disable level buttons temporarily
        disableLevelButtons(true);
        
        // Show loading state on the button
        const activeBtn = document.querySelector(`.level-btn[data-level="${level}"]`);
        const originalText = activeBtn ? activeBtn.innerHTML : level;
        if (activeBtn) {
            activeBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        }
        
        // Use the public endpoint
        const response = await fetch('/api/public/set_level', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ level: level })
        });
        
        const data = await response.json();
        
        // Re-enable buttons
        disableLevelButtons(false);
        
        // Reset button text
        if (activeBtn) {
            activeBtn.innerHTML = originalText;
        }
        
        if (data.status === 'success') {
            // Update current level
            currentLevel = level;
            
            // Update UI
            updateCurrentLevelDisplay();
            
            // Update level buttons
            document.querySelectorAll('.level-btn').forEach(btn => {
                btn.classList.remove('active');
                if (parseInt(btn.getAttribute('data-level')) === level) {
                    btn.classList.add('active');
                }
            });
            
            showNotification('success', `Level ${level} activated`, 3000);
            
            // Refresh data after a short delay
            setTimeout(() => {
                loadDashboardData();
            }, 1000);
            
        } else {
            showNotification('error', data.message || 'Failed to update level');
        }
        
    } catch (error) {
        console.error('Error setting level:', error);
        showNotification('error', 'Failed to update level. Check server connection.');
        disableLevelButtons(false);
    }
}

function updateCurrentLevelDisplay() {
    fetch('/api/level')
        .then(r => r.json())
        .then(data => {
            currentLevel = data.level || 0;
            const display = document.getElementById('current-level-display');
            if (display) {
                display.textContent = currentLevel;
                display.className = `level-display level-${currentLevel}`;
                
                // Also update level buttons active state
                document.querySelectorAll('.level-btn').forEach(btn => {
                    btn.classList.remove('active');
                    if (parseInt(btn.getAttribute('data-level')) === currentLevel) {
                        btn.classList.add('active');
                    }
                });
            }
            
            // Update page title
            document.title = `Juju FX - Level ${currentLevel}`;
        })
        .catch(error => {
            console.error('Error getting current level:', error);
        });
}

function disableLevelButtons(disable) {
    document.querySelectorAll('.level-btn').forEach(btn => {
        if (disable) {
            btn.setAttribute('disabled', 'disabled');
            btn.classList.add('disabled');
        } else {
            btn.removeAttribute('disabled');
            btn.classList.remove('disabled');
            
            // Reset button text
            const level = btn.getAttribute('data-level');
            btn.textContent = level;
        }
    });
}

function showLoadingState(show) {
    const loading = document.getElementById('loading-indicator');
    if (loading) {
        loading.style.display = show ? 'block' : 'none';
    }
    
    // Also show/hide a global spinner
    const globalSpinner = document.getElementById('global-spinner');
    if (globalSpinner) {
        globalSpinner.style.display = show ? 'flex' : 'none';
    }
}

function exportDashboardData() {
    try {
        fetch('/api/dashboard/summary')
            .then(r => r.json())
            .then(data => {
                const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `juju-fx-dashboard-${new Date().toISOString().slice(0,10)}.json`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                
                showNotification('success', 'Data exported successfully');
            });
    } catch (error) {
        console.error('Error exporting data:', error);
        showNotification('error', 'Failed to export data');
    }
}

function checkServerConnection() {
    fetch('/api/health')
        .then(r => r.json())
        .then(data => {
            if (data.status === 'healthy') {
                console.log('Server connection OK');
                const serverStatus = document.getElementById('server-status');
                if (serverStatus) {
                    serverStatus.innerHTML = '<i class="fas fa-check-circle text-success"></i> Connected';
                }
            }
        })
        .catch(error => {
            console.error('Server connection failed:', error);
            const serverStatus = document.getElementById('server-status');
            if (serverStatus) {
                serverStatus.innerHTML = '<i class="fas fa-times-circle text-danger"></i> Disconnected';
            }
            showNotification('error', 'Cannot connect to server. Please check if the server is running.', 10000);
        });
}

// Helper function: Format currency
function formatCurrency(amount) {
    if (amount === null || amount === undefined) return 'R 0.00';
    return new Intl.NumberFormat('en-ZA', {
        style: 'currency',
        currency: 'ZAR',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(amount);
}

// Helper function: Get P/L color class
function getPLColor(value) {
    if (value > 0) return 'text-success';
    if (value < 0) return 'text-danger';
    return 'text-muted';
}

// Helper function: Show notification
function showNotification(type, message, duration = 5000) {
    // Remove existing notifications
    document.querySelectorAll('.alert-notification').forEach(el => el.remove());
    
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-notification alert-dismissible fade show`;
    alert.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 1050; max-width: 350px;';
    alert.innerHTML = `
        <div class="d-flex align-items-center">
            <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'warning' ? 'exclamation-triangle' : 'exclamation-circle'} me-2"></i>
            <div>${message}</div>
        </div>
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(alert);
    
    // Auto-dismiss
    setTimeout(() => {
        if (alert.parentNode) {
            alert.classList.remove('show');
            setTimeout(() => alert.remove(), 150);
        }
    }, duration);
}

// Clean up on page unload
window.addEventListener('beforeunload', function() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
});

// Add some global keyboard shortcuts
document.addEventListener('keydown', function(e) {
    // Ctrl+R to refresh
    if (e.ctrlKey && e.key === 'r') {
        e.preventDefault();
        loadDashboardData();
        showNotification('info', 'Dashboard refreshed', 2000);
    }
    
    // Ctrl+E to export
    if (e.ctrlKey && e.key === 'e') {
        e.preventDefault();
        exportDashboardData();
    }
});

// Add CSS for level display (only if not already added)
if (!document.querySelector('#dashboard-styles')) {
    const style = document.createElement('style');
    style.id = 'dashboard-styles';
    style.textContent = `
        .level-display {
            font-size: 2.5rem;
            font-weight: bold;
            padding: 10px 20px;
            border-radius: 10px;
            display: inline-block;
            margin: 10px 0;
            transition: all 0.3s ease;
        }
        
        .level-0 { background-color: #dc3545; color: white; }
        .level-1 { background-color: #ff6b6b; color: white; }
        .level-2 { background-color: #ffa726; color: white; }
        .level-3 { background-color: #ffd166; color: #333; }
        .level-4 { background-color: #06d6a0; color: white; }
        .level-5 { background-color: #118ab2; color: white; }
        .level-6 { background-color: #073b4c; color: white; }
        
        .level-btn {
            width: 50px;
            height: 50px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            margin: 0 5px;
            transition: all 0.3s ease;
        }
        
        .level-btn.active {
            transform: scale(1.1);
            box-shadow: 0 0 0 3px rgba(0,123,255,0.5);
        }
        
        .level-btn:hover:not(.disabled) {
            transform: translateY(-2px);
        }
        
        .trade-row-win { background-color: rgba(40, 167, 69, 0.1); }
        .trade-row-loss { background-color: rgba(220, 53, 69, 0.1); }
        .trade-row-even { background-color: rgba(108, 117, 125, 0.1); }
        
        #global-spinner {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(255, 255, 255, 0.8);
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 9999;
        }
        
        .spinner {
            width: 50px;
            height: 50px;
            border: 5px solid #f3f3f3;
            border-top: 5px solid #4361ee;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    `;
    document.head.appendChild(style);
}

// Add global spinner HTML if not present
if (!document.getElementById('global-spinner')) {
    const spinner = document.createElement('div');
    spinner.id = 'global-spinner';
    spinner.innerHTML = '<div class="spinner"></div>';
    document.body.appendChild(spinner);
}