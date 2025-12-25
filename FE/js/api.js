/**
 * API Layer - All backend communication
 * 
 * Handles:
 * - Device ID management
 * - HTTP requests to Azure Functions
 * - Error handling and retries
 */

const API = {
    /**
     * Get or create device ID
     */
    getDeviceId() {
        let deviceId = localStorage.getItem(CONFIG.STORAGE_KEY_DEVICE_ID);
        if (!deviceId) {
            deviceId = this.generateUUID();
            localStorage.setItem(CONFIG.STORAGE_KEY_DEVICE_ID, deviceId);
            log.info('Generated new device ID:', deviceId);
        }
        return deviceId;
    },

    /**
     * Generate UUID v4
     */
    generateUUID() {
        if (typeof crypto !== 'undefined' && crypto.randomUUID) {
            return crypto.randomUUID();
        }
        // Fallback for older browsers
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    },

    /**
     * Start new conversation
     * @param {string} question - User's question
     * @returns {Promise<Object>} Response with conversation_id
     */
    async startConversation(question) {
        const url = `${CONFIG.API_BASE_URL}/chat/start`;
        const deviceId = this.getDeviceId();

        log.debug('Starting conversation:', { question, deviceId });

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                mode: 'cors', // Explicitly request CORS
                body: JSON.stringify({
                    question,
                    device_id: deviceId,
                }),
            });

            if (!response.ok) {
                const error = await response.json().catch(() => ({ error: 'Unknown error' }));
                throw new Error(error.error || `HTTP ${response.status}`);
            }

            const data = await response.json();
            log.debug('Conversation started:', data);
            return data;
        } catch (error) {
            // Enhanced CORS error handling
            if (error.message.includes('CORS') || error.name === 'TypeError') {
                throw new Error('CORS error: Backend is not accessible. Please check Azure Functions CORS settings or use HTTP server instead of file://');
            }
            throw error;
        }
    },

    /**
     * Poll conversation status
     * @param {string} conversationId - Conversation ID
     * @returns {Promise<Object>} Conversation status
     */
    async getConversationStatus(conversationId) {
        const url = `${CONFIG.API_BASE_URL}/chat/${conversationId}/status`;
        
        log.debug('Polling status for:', conversationId);

        const response = await fetch(url, {
            mode: 'cors',
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ error: 'Unknown error' }));
            throw new Error(error.error || `HTTP ${response.status}`);
        }

        const data = await response.json();
        log.debug('Status:', data.status, data.progress);
        return data;
    },

    /**
     * Get conversation messages
     * @param {string} conversationId - Conversation ID
     * @returns {Promise<Object>} Messages array
     */
    async getConversationMessages(conversationId) {
        const url = `${CONFIG.API_BASE_URL}/chat/${conversationId}/messages`;
        
        const response = await fetch(url, {
            mode: 'cors',
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ error: 'Unknown error' }));
            throw new Error(error.error || `HTTP ${response.status}`);
        }

        const data = await response.json();
        return data;
    },

    /**
     * Get conversation history for device
     * @param {number} limit - Max conversations to return
     * @returns {Promise<Object>} History array
     */
    async getConversationHistory(limit = CONFIG.MAX_HISTORY_ITEMS) {
        const deviceId = this.getDeviceId();
        const url = `${CONFIG.API_BASE_URL}/chat/history?device_id=${deviceId}&limit=${limit}`;
        
        log.debug('Loading history for device:', deviceId);

        const response = await fetch(url, {
            mode: 'cors',
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ error: 'Unknown error' }));
            throw new Error(error.error || `HTTP ${response.status}`);
        }

        const data = await response.json();
        log.debug('Loaded history:', data.conversations.length, 'items');
        return data;
    },

    /**
     * Handle API errors with retry logic
     * @param {Function} fn - API function to retry
     * @param {number} maxRetries - Max retry attempts
     * @param {number} delay - Delay between retries (ms)
     */
    async withRetry(fn, maxRetries = 3, delay = 1000) {
        for (let i = 0; i < maxRetries; i++) {
            try {
                return await fn();
            } catch (error) {
                if (i === maxRetries - 1) throw error;
                log.warn(`Retry ${i + 1}/${maxRetries} after error:`, error.message);
                await new Promise(resolve => setTimeout(resolve, delay * (i + 1)));
            }
        }
    },
};
