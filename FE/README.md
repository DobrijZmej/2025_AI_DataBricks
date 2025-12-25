# IMDb Analytics Chat - Frontend

Pure JavaScript chat interface for IMDb analytics powered by Azure Databricks and OpenAI GPT-4.

## 🎯 Features

- ✅ Pure client-side (no build tools required)
- ✅ Async polling architecture
- ✅ Device-based conversation tracking
- ✅ Multilingual support (auto-detected by LLM)
- ✅ Real-time progress indicators
- ✅ SQL query visibility
- ✅ LLM reasoning transparency
- ✅ Conversation history
- ✅ Mobile responsive

## 🚀 Quick Start

### Local Development

Just open `index.html` in your browser:

```bash
# Option 1: Double-click index.html

# Option 2: Python HTTP server
python -m http.server 8000

# Option 3: Node.js http-server (if installed)
npx http-server
```

Then navigate to: `http://localhost:8000`

### Azure Static Web Apps Deployment

1. **Push to GitHub:**
   ```bash
   git add .
   git commit -m "Add frontend"
   git push
   ```

2. **Create Azure Static Web App:**
   ```bash
   az staticwebapp create \
     --name imdb-chat-frontend \
     --resource-group EPAM_AI_DataBricks \
     --source https://github.com/<your-username>/<your-repo> \
     --location "West Europe" \
     --branch main \
     --app-location "/FE" \
     --output-location "" \
     --login-with-github
   ```

3. **Auto-deploy:**
   - Every push to `main` triggers automatic deployment
   - GitHub Actions workflow created automatically

## 📁 Project Structure

```
/FE
├── index.html                 # Main HTML structure
├── css/
│   └── styles.css            # All styling
├── js/
│   ├── config.js             # Configuration (API endpoint, etc.)
│   ├── api.js                # API calls to Azure Functions
│   ├── ui.js                 # DOM manipulation
│   ├── chat.js               # Chat logic & polling
│   └── app.js                # Main initialization
├── staticwebapp.config.json  # Azure SWA config
├── .gitignore
└── README.md
```

## ⚙️ Configuration

Edit `js/config.js` to customize:

```javascript
const CONFIG = {
    API_BASE_URL: 'https://your-backend.azurewebsites.net/api',
    POLL_INTERVAL: 3000,           // 3 seconds
    MAX_POLL_ATTEMPTS: 600,        // 30 minutes
    SHOW_SQL_QUERIES: true,        // Show SQL in UI
    SHOW_REASONING: true,          // Show LLM reasoning
    DEBUG: false,                  // Console logs
};
```

## 🎨 Customization

### Change Colors

Edit CSS variables in `css/styles.css`:

```css
:root {
    --primary-color: #2563eb;      /* Main blue */
    --success-color: #10b981;      /* Success green */
    --error-color: #ef4444;        /* Error red */
    /* ... */
}
```

### Add Features

All modules are cleanly separated:

- **API calls:** `js/api.js`
- **UI updates:** `js/ui.js`
- **Chat logic:** `js/chat.js`
- **Event handling:** `js/app.js`

## 🧪 Testing

### Test Questions

**English:**
- "What are the top 10 highest rated movies?"
- "Show me action movies from 2020"
- "Which directors have the most movies?"

**Ukrainian:**
- "Які 5 найкращих фільмів за рейтингом?"
- "Покажи мені комедії з 2015 року"

### Expected Response Times

- Simple queries: 10-30 seconds
- Complex queries: 30-90 seconds
- First query (cold start): 60-120 seconds

## 🔒 Security

- Anonymous access (lab environment)
- Device-based isolation (localStorage UUID)
- Read-only SQL queries
- CORS enabled on backend
- CSP headers configured

## 📊 Architecture

```
User → index.html → JavaScript → Azure Functions → Databricks Jobs API → Spark SQL → Delta Lake
                      ↓
                 Cosmos DB (conversation storage)
                      ↓
                 Azure OpenAI (LLM orchestration)
```

## 🛠️ Troubleshooting

**Messages not appearing:**
- Check browser console (F12)
- Verify `CONFIG.API_BASE_URL` in `js/config.js`
- Check network tab for API errors

**Polling timeout:**
- Normal for first query (Databricks cluster startup)
- Wait up to 2 minutes for cluster
- Check backend logs if persists

**History not loading:**
- Check localStorage (DevTools → Application → Local Storage)
- Verify `device_id` exists
- Clear localStorage and reload

**CORS errors:**
- Backend must allow your domain
- Check `Access-Control-Allow-Origin` header

## 📝 Development Notes

### No Build Tools Required

This project uses vanilla JavaScript intentionally:
- Zero npm dependencies
- No webpack, babel, or bundlers
- Pure ES6+ (supported in all modern browsers)
- Easy to debug and understand

### Browser Compatibility

Tested on:
- ✅ Chrome 90+
- ✅ Firefox 88+
- ✅ Safari 14+
- ✅ Edge 90+

Requires:
- `fetch` API
- `async/await`
- `crypto.randomUUID()` (with fallback)
- CSS Grid and Flexbox

## 📚 API Reference

See backend documentation for full API details:
- `POST /api/chat/start` - Start conversation
- `GET /api/chat/{id}/status` - Poll status
- `GET /api/chat/{id}/messages` - Get messages
- `GET /api/chat/history` - Get device history

## 🚀 Future Enhancements

Possible additions:
- [ ] Export conversation as PDF
- [ ] Share conversation via link
- [ ] Dark mode toggle
- [ ] Voice input
- [ ] Charts/visualizations for results
- [ ] Save favorite queries

## 📄 License

Internal lab project for EPAM AI DataBricks training.

## 👤 Author

Zmij - Data Engineer @ EPAM
December 2025
