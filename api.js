/**
 * SecureCAPTCHA Pro - JavaScript API Library
 * 商用レベル セキュアキャプチャ JavaScript ライブラリ
 * Usage: Similar to reCAPTCHA - just include script and call render()
 */

(function(window) {
    'use strict';
    
    const API_BASE_URL = 'https://api.kamichitateam.f5.si';
    
    // Global SecureCaptcha object
    window.SecureCaptcha = {
        _containers: new Map(),
        _sessions: new Map(),
        _deobfuscationKey: null,
        _readyCallbacks: [],
        _isReady: false,
        
        /**
         * Initialize the library (called automatically)
         */
        _init: function() {
            this._loadDeobfuscationKey().then(() => {
                this._isReady = true;
                this._readyCallbacks.forEach(callback => callback());
                this._readyCallbacks = [];
                
                // Auto-render containers with data-sitekey
                this._autoRender();
            });
        },
        
        /**
         * Auto-render containers with data-sitekey attribute
         */
        _autoRender: function() {
            const containers = document.querySelectorAll('[data-sitekey]');
            containers.forEach(container => {
                if (!container.hasAttribute('data-rendered')) {
                    this.render(container, {
                        sitekey: container.getAttribute('data-sitekey'),
                        callback: window[container.getAttribute('data-callback')] || null,
                        'expired-callback': window[container.getAttribute('data-expired-callback')] || null,
                        'error-callback': window[container.getAttribute('data-error-callback')] || null,
                        theme: container.getAttribute('data-theme') || 'light',
                        size: container.getAttribute('data-size') || 'normal'
                    });
                }
            });
        },
        
        /**
         * Load deobfuscation key from server
         */
        _loadDeobfuscationKey: async function() {
            try {
                const response = await fetch(`${API_BASE_URL}/api/captcha_license_key`);
                const data = await response.json();
                if (data.success) {
                    this._deobfuscationKey = data.deobfuscation_key;
                }
            } catch (error) {
                console.error('SecureCaptcha: Failed to load deobfuscation key', error);
            }
        },
        
        /**
         * Render CAPTCHA in a container
         * @param {HTMLElement|string} container - Container element or ID
         * @param {Object} parameters - Configuration parameters
         */
        render: function(container, parameters = {}) {
            if (!this._isReady) {
                this.ready(() => this.render(container, parameters));
                return;
            }
            
            const element = typeof container === 'string' ? 
                document.getElementById(container) : container;
            
            if (!element) {
                console.error('SecureCaptcha: Container not found');
                return null;
            }
            
            const widgetId = this._generateWidgetId();
            const config = {
                sitekey: parameters.sitekey || 'default',
                callback: parameters.callback || null,
                'expired-callback': parameters['expired-callback'] || null,
                'error-callback': parameters['error-callback'] || null,
                theme: parameters.theme || 'light',
                size: parameters.size || 'normal',
                ...parameters
            };
            
            this._containers.set(widgetId, {
                element: element,
                config: config,
                response: null,
                expired: false
            });
            
            this._createCaptchaUI(element, widgetId);
            element.setAttribute('data-rendered', 'true');
            
            return widgetId;
        },
        
        /**
         * Get response token from widget
         * @param {string} widgetId - Widget ID (optional, uses first widget if not provided)
         */
        getResponse: function(widgetId) {
            if (!widgetId && this._containers.size > 0) {
                widgetId = this._containers.keys().next().value;
            }
            
            const container = this._containers.get(widgetId);
            return container ? container.response : null;
        },
        
        /**
         * Reset a widget
         * @param {string} widgetId - Widget ID (optional)
         */
        reset: function(widgetId) {
            if (!widgetId && this._containers.size > 0) {
                widgetId = this._containers.keys().next().value;
            }
            
            const container = this._containers.get(widgetId);
            if (container) {
                container.response = null;
                container.expired = false;
                this._resetUI(container.element, widgetId);
            }
        },
        
        /**
         * Execute callback when ready
         * @param {Function} callback - Callback function
         */
        ready: function(callback) {
            if (this._isReady) {
                callback();
            } else {
                this._readyCallbacks.push(callback);
            }
        },
        
        /**
         * Create CAPTCHA UI
         */
        _createCaptchaUI: function(element, widgetId) {
            const container = this._containers.get(widgetId);
            const theme = container.config.theme;
            const size = container.config.size;
            
            const isDark = theme === 'dark';
            const isCompact = size === 'compact';
            
            const html = `
                <div class="securecaptcha-widget ${isDark ? 'dark' : 'light'} ${isCompact ? 'compact' : 'normal'}" 
                     data-widget-id="${widgetId}">
                    <div class="securecaptcha-header">
                        <div class="securecaptcha-logo">
                            <div class="securecaptcha-icon">🛡️</div>
                            <span>SecureCaptcha</span>
                        </div>
                        <div class="securecaptcha-status" id="status-${widgetId}">
                            <div class="securecaptcha-spinner"></div>
                        </div>
                    </div>
                    
                    <div class="securecaptcha-content" id="content-${widgetId}">
                        <div class="securecaptcha-loading">
                            <div class="loading-spinner"></div>
                            <p>Loading challenge...</p>
                        </div>
                    </div>
                    
                    <div class="securecaptcha-footer">
                        <div class="securecaptcha-info">
                            <span>Privacy</span> • <span>Terms</span>
                        </div>
                    </div>
                </div>
            `;
            
            element.innerHTML = html;
            this._injectStyles();
            this._loadChallenge(widgetId);
        },
        
        /**
         * Reset UI
         */
        _resetUI: function(element, widgetId) {
            const content = element.querySelector(`#content-${widgetId}`);
            content.innerHTML = `
                <div class="securecaptcha-loading">
                    <div class="loading-spinner"></div>
                    <p>Loading challenge...</p>
                </div>
            `;
            this._loadChallenge(widgetId);
        },
        
        /**
         * Load CAPTCHA challenge
         */
        _loadChallenge: async function(widgetId) {
            try {
                const response = await fetch(`${API_BASE_URL}/api/captcha/create`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
                
                const data = await response.json();
                
                if (data.success) {
                    this._sessions.set(widgetId, {
                        sessionId: data.data.session_id,
                        securityToken: data.data.security_token,
                        obfuscatedToken: data.obfuscated_token
                    });
                    
                    this._displayChallenge(widgetId, data.data);
                } else {
                    this._displayError(widgetId, 'Failed to load challenge');
                }
            } catch (error) {
                console.error('SecureCaptcha: Error loading challenge', error);
                this._displayError(widgetId, 'Network error');
            }
        },
        
        /**
         * Display challenge UI
         */
        _displayChallenge: function(widgetId, challengeData) {
            const container = this._containers.get(widgetId);
            const element = container.element;
            const content = element.querySelector(`#content-${widgetId}`);
            
            const html = `
                <div class="securecaptcha-challenge">
                    <div class="challenge-instruction">
                        <strong>Select all images with <span class="challenge-type">${challengeData.challenge_type}</span></strong>
                        <p>Click verify once there are none left.</p>
                    </div>
                    
                    <div class="image-grid" id="grid-${widgetId}">
                        ${challengeData.images.map((img, index) => `
                            <div class="image-cell" data-index="${index}">
                                <img src="${img}" alt="Challenge image" loading="lazy" />
                                <div class="selection-overlay"></div>
                            </div>
                        `).join('')}
                    </div>
                    
                    <div class="challenge-controls">
                        <button class="refresh-btn" onclick="SecureCaptcha._refreshChallenge('${widgetId}')">
                            🔄 New Challenge
                        </button>
                        <button class="verify-btn" onclick="SecureCaptcha._verifyChallenge('${widgetId}')">
                            ✓ Verify
                        </button>
                    </div>
                </div>
            `;
            
            content.innerHTML = html;
            this._setupImageSelection(widgetId);
        },
        
        /**
         * Setup image selection handlers
         */
        _setupImageSelection: function(widgetId) {
            const grid = document.querySelector(`#grid-${widgetId}`);
            const cells = grid.querySelectorAll('.image-cell');
            
            cells.forEach(cell => {
                cell.addEventListener('click', () => {
                    cell.classList.toggle('selected');
                });
            });
        },
        
        /**
         * Refresh challenge
         */
        _refreshChallenge: function(widgetId) {
            const container = this._containers.get(widgetId);
            const content = container.element.querySelector(`#content-${widgetId}`);
            content.innerHTML = `
                <div class="securecaptcha-loading">
                    <div class="loading-spinner"></div>
                    <p>Loading new challenge...</p>
                </div>
            `;
            this._loadChallenge(widgetId);
        },
        
        /**
         * Verify challenge solution
         */
        _verifyChallenge: async function(widgetId) {
            const session = this._sessions.get(widgetId);
            const grid = document.querySelector(`#grid-${widgetId}`);
            const selected = Array.from(grid.querySelectorAll('.image-cell.selected'))
                .map(cell => parseInt(cell.dataset.index));
            
            try {
                const response = await fetch(`${API_BASE_URL}/api/captcha/verify`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        session_id: session.sessionId,
                        selected_indices: selected,
                        security_token: session.securityToken
                    })
                });
                
                const data = await response.json();
                
                if (data.success && data.license_key) {
                    this._displaySuccess(widgetId, data.license_key);
                    
                    const container = this._containers.get(widgetId);
                    container.response = data.license_key;
                    
                    // Call success callback
                    if (container.config.callback) {
                        container.config.callback(data.license_key);
                    }
                } else {
                    this._displayError(widgetId, data.error || 'Verification failed');
                }
            } catch (error) {
                console.error('SecureCaptcha: Verification error', error);
                this._displayError(widgetId, 'Network error');
            }
        },
        
        /**
         * Display success state
         */
        _displaySuccess: function(widgetId, licenseKey) {
            const container = this._containers.get(widgetId);
            const content = container.element.querySelector(`#content-${widgetId}`);
            const status = container.element.querySelector(`#status-${widgetId}`);
            
            content.innerHTML = `
                <div class="securecaptcha-success">
                    <div class="success-icon">✅</div>
                    <p>Challenge completed successfully!</p>
                    <div class="success-token">${licenseKey.substring(0, 20)}...</div>
                </div>
            `;
            
            status.innerHTML = '<div class="success-checkmark">✓</div>';
        },
        
        /**
         * Display error state
         */
        _displayError: function(widgetId, message) {
            const container = this._containers.get(widgetId);
            const content = container.element.querySelector(`#content-${widgetId}`);
            
            content.innerHTML = `
                <div class="securecaptcha-error">
                    <div class="error-icon">❌</div>
                    <p>Error: ${message}</p>
                    <button class="retry-btn" onclick="SecureCaptcha._refreshChallenge('${widgetId}')">
                        Try Again
                    </button>
                </div>
            `;
            
            // Call error callback
            if (container.config['error-callback']) {
                container.config['error-callback'](message);
            }
        },
        
        /**
         * Generate unique widget ID
         */
        _generateWidgetId: function() {
            return 'securecaptcha_' + Math.random().toString(36).substr(2, 9);
        },
        
        /**
         * Inject CSS styles
         */
        _injectStyles: function() {
            if (document.getElementById('securecaptcha-styles')) return;
            
            const styles = `
                <style id="securecaptcha-styles">
                    .securecaptcha-widget {
                        border: 1px solid #d3d3d3;
                        border-radius: 8px;
                        background: #fafafa;
                        font-family: 'Roboto', 'Helvetica Neue', Arial, sans-serif;
                        width: 304px;
                        max-width: 100%;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    }
                    .securecaptcha-widget.dark {
                        background: #2d2d2d;
                        border-color: #444;
                        color: #fff;
                    }
                    .securecaptcha-widget.compact {
                        width: 256px;
                    }
                    .securecaptcha-header {
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        padding: 12px 16px;
                        border-bottom: 1px solid #e0e0e0;
                    }
                    .securecaptcha-widget.dark .securecaptcha-header {
                        border-bottom-color: #444;
                    }
                    .securecaptcha-logo {
                        display: flex;
                        align-items: center;
                        font-weight: 500;
                        font-size: 14px;
                    }
                    .securecaptcha-icon {
                        margin-right: 8px;
                        font-size: 16px;
                    }
                    .securecaptcha-status {
                        display: flex;
                        align-items: center;
                    }
                    .securecaptcha-spinner {
                        width: 16px;
                        height: 16px;
                        border: 2px solid #f3f3f3;
                        border-top: 2px solid #4285f4;
                        border-radius: 50%;
                        animation: securecaptcha-spin 1s linear infinite;
                    }
                    .success-checkmark {
                        color: #34a853;
                        font-weight: bold;
                        font-size: 16px;
                    }
                    @keyframes securecaptcha-spin {
                        0% { transform: rotate(0deg); }
                        100% { transform: rotate(360deg); }
                    }
                    .securecaptcha-content {
                        padding: 16px;
                        min-height: 120px;
                    }
                    .securecaptcha-loading {
                        text-align: center;
                        padding: 20px;
                    }
                    .loading-spinner {
                        width: 24px;
                        height: 24px;
                        border: 3px solid #f3f3f3;
                        border-top: 3px solid #4285f4;
                        border-radius: 50%;
                        animation: securecaptcha-spin 1s linear infinite;
                        margin: 0 auto 10px;
                    }
                    .securecaptcha-challenge {
                        text-align: center;
                    }
                    .challenge-instruction {
                        margin-bottom: 16px;
                        font-size: 14px;
                    }
                    .challenge-instruction strong {
                        display: block;
                        margin-bottom: 4px;
                    }
                    .challenge-type {
                        color: #1976d2;
                        font-weight: bold;
                    }
                    .image-grid {
                        display: grid;
                        grid-template-columns: repeat(3, 1fr);
                        gap: 4px;
                        margin-bottom: 16px;
                        border: 1px solid #ddd;
                        border-radius: 4px;
                        overflow: hidden;
                    }
                    .image-cell {
                        position: relative;
                        aspect-ratio: 1;
                        cursor: pointer;
                        overflow: hidden;
                    }
                    .image-cell img {
                        width: 100%;
                        height: 100%;
                        object-fit: cover;
                        display: block;
                    }
                    .selection-overlay {
                        position: absolute;
                        top: 0;
                        left: 0;
                        right: 0;
                        bottom: 0;
                        background: rgba(66, 133, 244, 0.3);
                        opacity: 0;
                        transition: opacity 0.2s;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                    }
                    .selection-overlay::after {
                        content: '✓';
                        color: white;
                        font-size: 24px;
                        font-weight: bold;
                        text-shadow: 0 0 4px rgba(0,0,0,0.5);
                    }
                    .image-cell.selected .selection-overlay {
                        opacity: 1;
                    }
                    .image-cell:hover .selection-overlay {
                        opacity: 0.2;
                    }
                    .challenge-controls {
                        display: flex;
                        justify-content: space-between;
                        gap: 8px;
                    }
                    .refresh-btn, .verify-btn, .retry-btn {
                        flex: 1;
                        padding: 8px 16px;
                        border: 1px solid #dadce0;
                        background: white;
                        color: #1976d2;
                        border-radius: 4px;
                        cursor: pointer;
                        font-size: 13px;
                        font-weight: 500;
                        transition: all 0.2s;
                    }
                    .verify-btn {
                        background: #1976d2;
                        color: white;
                        border-color: #1976d2;
                    }
                    .refresh-btn:hover, .retry-btn:hover {
                        background: #f8f9fa;
                    }
                    .verify-btn:hover {
                        background: #1565c0;
                    }
                    .securecaptcha-success, .securecaptcha-error {
                        text-align: center;
                        padding: 20px;
                    }
                    .success-icon, .error-icon {
                        font-size: 32px;
                        margin-bottom: 12px;
                    }
                    .success-token {
                        font-family: monospace;
                        font-size: 12px;
                        color: #666;
                        margin-top: 8px;
                        padding: 4px 8px;
                        background: #f0f0f0;
                        border-radius: 4px;
                    }
                    .securecaptcha-footer {
                        padding: 8px 16px;
                        border-top: 1px solid #e0e0e0;
                        text-align: right;
                    }
                    .securecaptcha-widget.dark .securecaptcha-footer {
                        border-top-color: #444;
                    }
                    .securecaptcha-info {
                        font-size: 10px;
                        color: #666;
                    }
                    .securecaptcha-widget.dark .securecaptcha-info {
                        color: #aaa;
                    }
                    .securecaptcha-info span:hover {
                        text-decoration: underline;
                        cursor: pointer;
                    }
                </style>
            `;
            
            document.head.insertAdjacentHTML('beforeend', styles);
        }
    };
    
    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            SecureCaptcha._init();
        });
    } else {
        SecureCaptcha._init();
    }
    
    // Global functions for backward compatibility
    window.securecaptchaCallback = function() {
        // Called when script is loaded
    };
    
})(window);
