/**
 * UI Layer - All DOM manipulation
 * 
 * Handles:
 * - Rendering messages
 * - Updating progress
 * - Managing history sidebar
 * - User interactions
 */

const UI = {
    // DOM elements (initialized in init())
    elements: {},

    /**
     * Initialize UI references
     */
    init() {
        this.elements = {
            messagesContainer: document.getElementById('messages-container'),
            userInput: document.getElementById('user-input'),
            sendBtn: document.getElementById('send-btn'),
            sendBtnText: document.getElementById('send-btn-text'),
            sendBtnIcon: document.getElementById('send-btn-icon'),
            progressContainer: document.getElementById('progress-container'),
            progressStatus: document.getElementById('progress-status'),
            progressPercentage: document.getElementById('progress-percentage'),
            progressFill: document.getElementById('progress-fill'),
            progressMessage: document.getElementById('progress-message'),
            sqlDetails: document.getElementById('sql-details'),
            sqlQuery: document.getElementById('sql-query'),
            historyList: document.getElementById('history-list'),
            refreshHistoryBtn: document.getElementById('refresh-history'),
        };
    },

    /**
     * Clear welcome message
     */
    clearWelcome() {
        const welcome = this.elements.messagesContainer.querySelector('.welcome-message');
        if (welcome) {
            welcome.remove();
        }
    },

    /**
     * Add user message
     */
    addUserMessage(text) {
        this.clearWelcome();

        const messageEl = document.createElement('div');
        messageEl.className = 'message user';
        messageEl.innerHTML = `
            <div class="message-content">
                ${this.escapeHtml(text)}
                <div class="message-time">${this.formatTime(new Date())}</div>
            </div>
            <div class="message-avatar">👤</div>
        `;

        this.elements.messagesContainer.appendChild(messageEl);
        this.scrollToBottom();
    },

    /**
     * Add assistant message
     */
    addAssistantMessage(text, timestamp = new Date()) {
        const messageEl = document.createElement('div');
        messageEl.className = 'message assistant';
        messageEl.innerHTML = `
            <div class="message-avatar">🤖</div>
            <div class="message-content">
                ${this.formatMarkdown(text)}
                <div class="message-time">${this.formatTime(timestamp)}</div>
            </div>
        `;

        this.elements.messagesContainer.appendChild(messageEl);
        this.scrollToBottom();
    },

    /**
     * Add error message
     */
    addErrorMessage(text) {
        const errorEl = document.createElement('div');
        errorEl.className = 'error-message';
        errorEl.textContent = '❌ ' + text;

        this.elements.messagesContainer.appendChild(errorEl);
        this.scrollToBottom();
    },

    /**
     * Show/hide progress indicator
     */
    showProgress(show = true) {
        this.elements.progressContainer.style.display = show ? 'block' : 'none';
    },

    /**
     * Update progress bar
     */
    updateProgress(percentage, status, message = '') {
        // Update percentage
        this.elements.progressPercentage.textContent = `${Math.round(percentage)}%`;
        this.elements.progressFill.style.width = `${percentage}%`;

        // Update status icon and text
        const statusIcons = {
            'processing': '🔄',
            'completed': '✅',
            'error': '❌',
        };
        
        let icon = '🔄';
        let text = 'Processing...';

        if (percentage <= 20) {
            icon = '🤔';
            text = 'Analyzing question with AI...';
        } else if (percentage <= 40) {
            icon = '⚡';
            text = 'Generating database query...';
        } else if (percentage < 85) {
            icon = '🔄';
            text = 'Executing Spark SQL...';
        } else if (percentage < 100) {
            icon = '📊';
            text = 'Processing results...';
        } else {
            icon = '✅';
            text = 'Completed';
        }

        if (status === 'error') {
            icon = '❌';
            text = 'Error occurred';
        }

        this.elements.progressStatus.textContent = `${icon} ${text}`;

        // Update message
        if (message) {
            this.elements.progressMessage.textContent = message;
            this.elements.progressMessage.style.display = 'block';
        } else {
            this.elements.progressMessage.style.display = 'none';
        }
    },

    /**
     * Show SQL query
     */
    showSqlQuery(sql) {
        if (!CONFIG.SHOW_SQL_QUERIES || !sql) return;

        this.elements.sqlDetails.style.display = 'block';
        this.elements.sqlQuery.textContent = sql;
    },

    /**
     * Hide SQL query
     */
    hideSqlQuery() {
        this.elements.sqlDetails.style.display = 'none';
    },

    /**
     * Render conversation history
     */
    renderHistory(conversations) {
        this.elements.historyList.innerHTML = '';

        if (!conversations || conversations.length === 0) {
            this.elements.historyList.innerHTML = `
                <div class="history-empty">
                    <p>No conversations yet</p>
                    <p style="margin-top: 8px; font-size: 12px;">Start by asking a question!</p>
                </div>
            `;
            return;
        }

        conversations.forEach(conv => {
            const item = this.createHistoryItem(conv);
            this.elements.historyList.appendChild(item);
        });
    },

    /**
     * Create history item element
     */
    createHistoryItem(conversation) {
        const item = document.createElement('div');
        item.className = 'history-item';
        item.dataset.conversationId = conversation.id;

        const statusIcons = {
            'completed': '✅',
            'processing': '🔄',
            'error': '❌',
        };

        const icon = statusIcons[conversation.status] || '⏳';
        const preview = conversation.final_answer 
            ? conversation.final_answer.substring(0, 80) + '...'
            : conversation.error || 'Processing...';

        item.innerHTML = `
            <div class="history-item-header">
                <span class="history-time">${this.formatTime(new Date(conversation.created_at))}</span>
                <span class="history-status">${icon}</span>
            </div>
            <div class="history-question">${this.escapeHtml(conversation.question)}</div>
            <div class="history-preview">${this.escapeHtml(preview)}</div>
        `;

        item.addEventListener('click', () => {
            this.loadConversation(conversation.id);
        });

        return item;
    },

    /**
     * Load conversation (placeholder for Chat.loadConversation)
     */
    loadConversation(conversationId) {
        log.info('Loading conversation:', conversationId);
        // This will be called from Chat module
        if (window.Chat && window.Chat.loadConversation) {
            window.Chat.loadConversation(conversationId);
        }
    },

    /**
     * Enable/disable input
     */
    setInputEnabled(enabled) {
        this.elements.userInput.disabled = !enabled;
        this.elements.sendBtn.disabled = !enabled;

        if (enabled) {
            this.elements.sendBtnText.textContent = 'Send';
            this.elements.sendBtnIcon.textContent = '📤';
            this.elements.sendBtnIcon.classList.remove('spinning');
        } else {
            this.elements.sendBtnText.textContent = 'Processing';
            this.elements.sendBtnIcon.textContent = '⏳';
            this.elements.sendBtnIcon.classList.add('spinning');
        }
    },

    /**
     * Clear messages
     */
    clearMessages() {
        this.elements.messagesContainer.innerHTML = '';
    },

    /**
     * Scroll to bottom
     */
    scrollToBottom() {
        if (CONFIG.AUTO_SCROLL_TO_BOTTOM) {
            this.elements.messagesContainer.scrollTop = this.elements.messagesContainer.scrollHeight;
        }
    },

    /**
     * Format timestamp
     */
    formatTime(date) {
        if (CONFIG.MESSAGE_TIMESTAMP_FORMAT === 'iso') {
            return date.toISOString();
        }
        
        const now = new Date();
        const diff = now - date;
        const minutes = Math.floor(diff / 60000);
        const hours = Math.floor(diff / 3600000);
        const days = Math.floor(diff / 86400000);

        if (minutes < 1) return 'Just now';
        if (minutes < 60) return `${minutes}m ago`;
        if (hours < 24) return `${hours}h ago`;
        if (days < 7) return `${days}d ago`;

        return date.toLocaleDateString();
    },

    /**
     * Escape HTML
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    /**
     * Format markdown (basic)
     */
    formatMarkdown(text) {
        // Basic markdown support
        text = this.escapeHtml(text);
        
        // Bold
        text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        
        // Numbered lists
        text = text.replace(/^\d+\.\s(.+)$/gm, '<li>$1</li>');
        text = text.replace(/(<li>.*<\/li>)/s, '<ol>$1</ol>');
        
        // Line breaks
        text = text.replace(/\n/g, '<br>');

        return text;
    },
};
