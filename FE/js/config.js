/**
 * Configuration for IMDb Analytics Chat
 * 
 * Switch between development and production environments
 */

const CONFIG = {
    // API Configuration
    API_BASE_URL: 'https://imdb-dbx-backend-func-buheg0bce0bvahbz.westeurope-01.azurewebsites.net/api',
    
    // Polling Configuration
    POLL_INTERVAL: 3000, // 3 seconds
    MAX_POLL_ATTEMPTS: 600, // 30 minutes (600 * 3 seconds)
    
    // Local Storage Keys
    STORAGE_KEY_DEVICE_ID: 'imdb_device_id',
    STORAGE_KEY_ACTIVE_CONVERSATION: 'imdb_active_conversation',
    
    // UI Configuration
    MAX_HISTORY_ITEMS: 50,
    MESSAGE_TIMESTAMP_FORMAT: 'locale', // 'locale' or 'iso'
    
    // Feature Flags
    SHOW_SQL_QUERIES: true,
    SHOW_REASONING: true,
    AUTO_SCROLL_TO_BOTTOM: true,
    
    // Debug Mode
    DEBUG: true, // Set to true to enable console logs
};

// Logging utility
const log = {
    debug: (...args) => CONFIG.DEBUG && console.log('[DEBUG]', ...args),
    info: (...args) => console.log('[INFO]', ...args),
    warn: (...args) => console.warn('[WARN]', ...args),
    error: (...args) => console.error('[ERROR]', ...args),
};
