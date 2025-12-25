# Test Script for Production API
# Usage: .\test_async_api.ps1

$baseUrl = "https://imdb-dbx-backend-func-buheg0bce0bvahbz.westeurope-01.azurewebsites.net"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  IMDb Analytics - Async API Test" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# Test question
$question = "What are the top 3 highest rated movies?"
Write-Host "Question: $question" -ForegroundColor Yellow
Write-Host ""

# Step 1: Start conversation
Write-Host "[1/3] Starting conversation..." -ForegroundColor Green

$body = @{
    question = $question
    user_id = "test_user_123"
} | ConvertTo-Json

try {
    $response = Invoke-WebRequest `
        -Uri "$baseUrl/api/chat/start" `
        -Method POST `
        -Body $body `
        -ContentType "application/json" `
        -UseBasicParsing
    
    $data = $response.Content | ConvertFrom-Json
    $conversationId = $data.conversation_id
    
    Write-Host "✓ Conversation started: $conversationId" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "✗ Failed to start conversation: $_" -ForegroundColor Red
    exit 1
}

# Step 2: Poll for completion
Write-Host "[2/3] Polling for completion..." -ForegroundColor Green
Write-Host ""

$maxAttempts = 60
$attempt = 0
$pollInterval = 2

while ($attempt -lt $maxAttempts) {
    $attempt++
    
    try {
        $statusResponse = Invoke-WebRequest `
            -Uri "$baseUrl/api/chat/$conversationId/status" `
            -UseBasicParsing
        
        $status = $statusResponse.Content | ConvertFrom-Json
        
        $percentage = $status.progress.percentage
        $step = $status.progress.current_step
        $state = $status.status
        
        # Progress bar
        $barLength = 40
        $filled = [math]::Floor($barLength * $percentage / 100)
        $empty = $barLength - $filled
        $bar = ("#" * $filled) + ("." * $empty)
        
        Write-Host "`r[$bar] $percentage% - $step" -NoNewline
        
        if ($state -eq "completed") {
            Write-Host ""
            Write-Host ""
            Write-Host "✓ Processing completed!" -ForegroundColor Green
            Write-Host ""
            
            # Display final answer
            Write-Host "==================================================" -ForegroundColor Cyan
            Write-Host "  FINAL ANSWER" -ForegroundColor Cyan
            Write-Host "==================================================" -ForegroundColor Cyan
            Write-Host ""
            Write-Host $status.final_answer -ForegroundColor White
            Write-Host ""
            
            # Display execution details
            Write-Host "==================================================" -ForegroundColor Cyan
            Write-Host "  EXECUTION DETAILS" -ForegroundColor Cyan
            Write-Host "==================================================" -ForegroundColor Cyan
            Write-Host ""
            
            foreach ($job in $status.databricks_jobs) {
                Write-Host "Databricks Job:" -ForegroundColor Yellow
                Write-Host "  Run ID: $($job.run_id)"
                Write-Host "  Status: $($job.status)"
                Write-Host "  SQL: $($job.sql_query)"
                Write-Host ""
            }
            
            $elapsed = [DateTime]::Parse($status.updated_at) - [DateTime]::Parse($status.created_at)
            Write-Host "Total time: $($elapsed.TotalSeconds) seconds" -ForegroundColor Green
            Write-Host ""
            
            break
        } elseif ($state -eq "error") {
            Write-Host ""
            Write-Host ""
            Write-Host "✗ Error: $($status.error)" -ForegroundColor Red
            exit 1
        }
        
        Start-Sleep -Seconds $pollInterval
    } catch {
        Write-Host ""
        Write-Host "✗ Error polling status: $_" -ForegroundColor Red
        exit 1
    }
}

if ($attempt -ge $maxAttempts) {
    Write-Host ""
    Write-Host "✗ Timeout: Processing took longer than expected" -ForegroundColor Red
    exit 1
}

# Step 3: Get full message history
Write-Host "[3/3] Fetching conversation history..." -ForegroundColor Green

try {
    $messagesResponse = Invoke-WebRequest `
        -Uri "$baseUrl/api/chat/$conversationId/messages" `
        -UseBasicParsing
    
    $messages = $messagesResponse.Content | ConvertFrom-Json
    
    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host "  CONVERSATION HISTORY" -ForegroundColor Cyan
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host ""
    
    foreach ($msg in $messages.messages) {
        $role = $msg.role.ToUpper()
        $color = if ($role -eq "USER") { "Yellow" } else { "Cyan" }
        
        Write-Host "[$role]" -ForegroundColor $color
        Write-Host $msg.content
        Write-Host ""
    }
} catch {
    Write-Host "✗ Failed to fetch messages: $_" -ForegroundColor Red
}

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  TEST COMPLETED" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
