# Simple Test Script for Async API

$baseUrl = "https://imdb-dbx-backend-func-buheg0bce0bvahbz.westeurope-01.azurewebsites.net"

Write-Host "=================================================="
Write-Host "  IMDb Analytics - Async API Test"
Write-Host "=================================================="
Write-Host ""

# Test question
$question = "What are the top 3 highest rated movies?"
Write-Host "Question: $question"
Write-Host ""

# Step 1: Start conversation
Write-Host "[1/2] Starting conversation..."

$body = @{
    question = $question
} | ConvertTo-Json

$response = Invoke-WebRequest `
    -Uri "$baseUrl/api/chat/start" `
    -Method POST `
    -Body $body `
    -ContentType "application/json" `
    -UseBasicParsing

$data = $response.Content | ConvertFrom-Json
$conversationId = $data.conversation_id

Write-Host "Conversation ID: $conversationId"
Write-Host ""

# Step 2: Poll for completion
Write-Host "[2/2] Polling for completion..."
Write-Host ""

$maxAttempts = 60
$attempt = 0

while ($attempt -lt $maxAttempts) {
    $attempt++
    
    $statusResponse = Invoke-WebRequest `
        -Uri "$baseUrl/api/chat/$conversationId/status" `
        -UseBasicParsing
    
    $status = $statusResponse.Content | ConvertFrom-Json
    
    $percentage = $status.progress.percentage
    $step = $status.progress.current_step
    $state = $status.status
    
    Write-Host "[$attempt] $percentage% - $step"
    
    if ($state -eq "completed") {
        Write-Host ""
        Write-Host "=================================================="
        Write-Host "  COMPLETED"
        Write-Host "=================================================="
        Write-Host ""
        Write-Host "ANSWER:"
        Write-Host $status.final_answer
        Write-Host ""
        Write-Host "Databricks Jobs:"
        foreach ($job in $status.databricks_jobs) {
            Write-Host "  - Run ID: $($job.run_id)"
            Write-Host "    Status: $($job.status)"
            Write-Host "    SQL: $($job.sql_query)"
        }
        Write-Host ""
        break
    }
    
    if ($state -eq "error") {
        Write-Host ""
        Write-Host "ERROR: $($status.error)"
        break
    }
    
    Start-Sleep -Seconds 2
}

Write-Host "=================================================="
Write-Host "  TEST COMPLETED"
Write-Host "=================================================="
