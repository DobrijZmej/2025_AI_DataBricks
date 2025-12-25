/**
 * Chat Logic - Core conversation management
 * 
 * Handles:
 * - Starting conversations
 * - Polling status
 * - Managing conversation state
 * - Processing results
 */

const Chat = {
    // Current conversation state
    currentConversationId: null,
    pollingInterval: null,
    pollCount: 0,

    /**
     * Initialize chat
     */
    init() {
        log.info('Chat initialized');
    },

    /**
     * Start new conversation
     */
    async startConversation(question) {
        try {
            // Validate input
            if (!question || !question.trim()) {
                throw new Error('Please enter a question');
            }

            // UI updates
            UI.addUserMessage(question);
            UI.setInputEnabled(false);
            UI.showProgress(true);
            UI.updateProgress(0, 'processing', '');
            UI.hideSqlQuery();

            // Clear input
            UI.elements.userInput.value = '';

            // Start conversation
            log.info('Starting conversation with question:', question);
            const response = await API.withRetry(() => API.startConversation(question));

            this.currentConversationId = response.conversation_id;
            localStorage.setItem(CONFIG.STORAGE_KEY_ACTIVE_CONVERSATION, this.currentConversationId);

            log.info('Conversation started:', this.currentConversationId);

            // Start polling
            this.startPolling();

        } catch (error) {
            log.error('Failed to start conversation:', error);
            UI.addErrorMessage(`Failed to start conversation: ${error.message}`);
            UI.setInputEnabled(true);
            UI.showProgress(false);
        }
    },

    /**
     * Start polling for status
     */
    startPolling() {
        this.pollCount = 0;
        this.stopPolling(); // Clear any existing interval

        log.info('Starting polling for conversation:', this.currentConversationId);

        // Poll immediately
        this.pollStatus();

        // Then poll every N seconds
        this.pollingInterval = setInterval(() => {
            this.pollStatus();
        }, CONFIG.POLL_INTERVAL);
    },

    /**
     * Stop polling
     */
    stopPolling() {
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
            log.info('Polling stopped');
        }
    },

    /**
     * Poll conversation status
     */
    async pollStatus() {
        try {
            this.pollCount++;

            // Check max attempts
            if (this.pollCount > CONFIG.MAX_POLL_ATTEMPTS) {
                throw new Error('Polling timeout: Maximum attempts reached');
            }

            // Get status
            const status = await API.getConversationStatus(this.currentConversationId);

            log.debug(`Poll #${this.pollCount}:`, status.status, status.progress);

            // Update progress
            const progress = status.progress || { percentage: 0, current_step: '' };
            UI.updateProgress(
                progress.percentage || 0,
                status.status,
                CONFIG.SHOW_REASONING ? progress.current_step : ''
            );

            // Show SQL query if available
            if (status.databricks_jobs && status.databricks_jobs.length > 0) {
                const job = status.databricks_jobs[0];
                if (job.sql_query) {
                    UI.showSqlQuery(job.sql_query);
                }
            }

            // Check status
            if (status.status === 'completed') {
                this.handleCompleted(status);
            } else if (status.status === 'error') {
                this.handleError(status);
            }
            // else keep polling (status === 'processing')

        } catch (error) {
            log.error('Polling error:', error);
            this.handleError({ error: error.message });
        }
    },

    /**
     * Handle completed conversation
     */
    handleCompleted(status) {
        log.info('Conversation completed:', status);

        this.stopPolling();

        // Update progress to 100%
        UI.updateProgress(100, 'completed', 'Completed');

        // Add assistant message
        if (status.final_answer) {
            UI.addAssistantMessage(status.final_answer);
        }

        // Hide progress after a delay
        setTimeout(() => {
            UI.showProgress(false);
            UI.hideSqlQuery();
        }, 2000);

        // Re-enable input
        UI.setInputEnabled(true);

        // Refresh history
        this.loadHistory();

        // Clear active conversation
        localStorage.removeItem(CONFIG.STORAGE_KEY_ACTIVE_CONVERSATION);
        this.currentConversationId = null;
    },

    /**
     * Handle error
     */
    handleError(status) {
        log.error('Conversation error:', status);

        this.stopPolling();

        // Update progress
        UI.updateProgress(0, 'error', '');

        // Show error
        const errorMessage = status.error || 'An unknown error occurred';
        UI.addErrorMessage(errorMessage);

        // Hide progress
        setTimeout(() => {
            UI.showProgress(false);
            UI.hideSqlQuery();
        }, 3000);

        // Re-enable input
        UI.setInputEnabled(true);

        // Refresh history
        this.loadHistory();

        // Clear active conversation
        localStorage.removeItem(CONFIG.STORAGE_KEY_ACTIVE_CONVERSATION);
        this.currentConversationId = null;
    },

    /**
     * Load conversation history
     */
    async loadHistory() {
        try {
            log.info('Loading history...');
            const history = await API.getConversationHistory();
            UI.renderHistory(history.conversations);
        } catch (error) {
            log.error('Failed to load history:', error);
            // Don't show error to user - history is optional
        }
    },

    /**
     * Load specific conversation
     */
    async loadConversation(conversationId) {
        try {
            log.info('Loading conversation:', conversationId);

            // Get messages
            const data = await API.getConversationMessages(conversationId);

            // Clear and render messages
            UI.clearMessages();
            
            if (data.messages && data.messages.length > 0) {
                data.messages.forEach(msg => {
                    if (msg.role === 'user') {
                        UI.addUserMessage(msg.content);
                    } else {
                        UI.addAssistantMessage(msg.content, new Date(msg.timestamp));
                    }
                });
            }

            // Highlight in history
            document.querySelectorAll('.history-item').forEach(item => {
                item.classList.remove('active');
            });
            const activeItem = document.querySelector(`[data-conversation-id="${conversationId}"]`);
            if (activeItem) {
                activeItem.classList.add('active');
            }

        } catch (error) {
            log.error('Failed to load conversation:', error);
            UI.addErrorMessage(`Failed to load conversation: ${error.message}`);
        }
    },

    /**
     * Resume active conversation (on page reload)
     */
    async resumeActiveConversation() {
        const conversationId = localStorage.getItem(CONFIG.STORAGE_KEY_ACTIVE_CONVERSATION);
        
        if (!conversationId) return;

        try {
            log.info('Resuming active conversation:', conversationId);
            
            const status = await API.getConversationStatus(conversationId);

            if (status.status === 'processing') {
                // Resume polling
                this.currentConversationId = conversationId;
                UI.showProgress(true);
                UI.setInputEnabled(false);
                this.startPolling();
            } else {
                // Conversation already finished
                localStorage.removeItem(CONFIG.STORAGE_KEY_ACTIVE_CONVERSATION);
            }

        } catch (error) {
            log.error('Failed to resume conversation:', error);
            localStorage.removeItem(CONFIG.STORAGE_KEY_ACTIVE_CONVERSATION);
        }
    },
};

// Export for UI to use
window.Chat = Chat;
