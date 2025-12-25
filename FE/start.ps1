# Quick start script for IMDb Chat Frontend
Write-Host "Starting IMDb Analytics Chat..." -ForegroundColor Cyan

# Check if Python is available
if (Get-Command python -ErrorAction SilentlyContinue) {
    Write-Host "Starting HTTP server on http://localhost:8000" -ForegroundColor Green
    Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
    Write-Host ""
    
    # Open browser
    Start-Sleep -Seconds 2
    Start-Process "http://localhost:8000"
    
    # Start server
    python -m http.server 8000
} else {
    Write-Host "Python not found. Opening file directly..." -ForegroundColor Yellow
    Start-Process "index.html"
}
