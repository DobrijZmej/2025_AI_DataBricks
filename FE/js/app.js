/**
 * Main Application Entry Point
 * 
 * Initializes all modules and sets up event listeners
 */

document.addEventListener('DOMContentLoaded', async () => {
    log.info('IMDb Analytics Chat - Starting...');
    log.info('Device ID:', API.getDeviceId());

    // Initialize modules
    UI.init();
    Chat.init();

    // Load conversation history
    await Chat.loadHistory();

    // Resume active conversation if exists
    await Chat.resumeActiveConversation();

    // Event listeners
    setupEventListeners();

    log.info('Application ready! 🚀');
});

/**
 * Setup all event listeners
 */
function setupEventListeners() {
    // Send button click
    UI.elements.sendBtn.addEventListener('click', handleSendMessage);

    // Enter key in textarea (Ctrl+Enter or Cmd+Enter to send)
    UI.elements.userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            handleSendMessage();
        }
    });

    // Refresh history button
    UI.elements.refreshHistoryBtn.addEventListener('click', async () => {
        UI.elements.refreshHistoryBtn.classList.add('spinning');
        await Chat.loadHistory();
        UI.elements.refreshHistoryBtn.classList.remove('spinning');
    });

    // Auto-resize textarea
    UI.elements.userInput.addEventListener('input', () => {
        const textarea = UI.elements.userInput;
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
    });
}

/**
 * Handle send message
 */
async function handleSendMessage() {
    const question = UI.elements.userInput.value.trim();
    
    if (!question) {
        log.warn('Empty question, ignoring');
        return;
    }

    if (UI.elements.sendBtn.disabled) {
        log.warn('Send button disabled, ignoring');
        return;
    }

    await Chat.startConversation(question);
}

/**
 * Handle errors globally
 */
window.addEventListener('error', (event) => {
    log.error('Global error:', event.error);
});

window.addEventListener('unhandledrejection', (event) => {
    log.error('Unhandled promise rejection:', event.reason);
});

/**
 * Handle page visibility change (pause/resume polling)
 */
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        log.info('Page hidden - polling continues in background');
    } else {
        log.info('Page visible - polling active');
        // Optionally refresh history when user returns
        if (!Chat.currentConversationId) {
            Chat.loadHistory();
        }
    }
});
