"""
Meeting control endpoints (manual join, etc).
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any

from app.api.v1.schemas.meeting import ManualJoinRequest, ManualJoinResponse
from app.core.dependencies import get_meeting_bot_service
from app.core.logging import get_logger
from fastapi.responses import HTMLResponse

router = APIRouter()
logger = get_logger("api.meetings")


@router.get("/join", response_class=HTMLResponse, tags=["Meetings"])
async def manual_join_page():
    """
    Render the manual meeting join page.
    
    Returns:
        HTML page for manual meeting join
    """
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Meeting Bot - Manual Join</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                background-color: #f5f5f5;
            }
            .container {
                background: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            h1 {
                color: #333;
            }
            input, button {
                width: 100%;
                padding: 12px;
                margin: 10px 0;
                border: 1px solid #ddd;
                border-radius: 4px;
                box-sizing: border-box;
                font-size: 16px;
            }
            button {
                background-color: #0066cc;
                color: white;
                border: none;
                cursor: pointer;
            }
            button:hover {
                background-color: #0052a3;
            }
            .result {
                margin-top: 20px;
                padding: 15px;
                border-radius: 4px;
            }
            .success {
                background-color: #d4edda;
                color: #155724;
            }
            .error {
                background-color: #f8d7da;
                color: #721c24;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Join Meeting</h1>
            <form id="joinForm">
                <label for="bot_name">Bot Display Name:</label>
                <input type="text" id="bot_name" name="bot_name" value="Meeting Transcriber" required>
                
                <label for="meeting_url">Meeting URL:</label>
                <input type="text" id="meeting_url" name="meeting_url" placeholder="https://meet.google.com/xxx-yyyy-zzz" required>
                
                <button type="submit">Join Meeting</button>
            </form>
            <div id="result"></div>
            <p><a href="/">← Back to Dashboard</a></p>
        </div>
        
        <script>
            document.getElementById('joinForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                
                const bot_name = document.getElementById('bot_name').value;
                const meeting_url = document.getElementById('meeting_url').value;
                const resultDiv = document.getElementById('result');
                
                try {
                    const response = await fetch('/api/v1/meetings/join', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ bot_name, meeting_url }),
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        resultDiv.className = 'result success';
                        resultDiv.innerHTML = `
                            <strong>✅ Success!</strong><br>
                            Meeting ID: ${result.meeting_id}<br>
                            Session ID: ${result.session_id}<br>
                            Platform: ${result.platform}
                        `;
                    } else {
                        resultDiv.className = 'result error';
                        resultDiv.innerHTML = `<strong>❌ Error:</strong> ${result.error}`;
                    }
                } catch (error) {
                    resultDiv.className = 'result error';
                    resultDiv.innerHTML = `<strong>❌ Error:</strong> ${error.message}`;
                }
            });
        </script>
    </body>
    </html>
    """


@router.post("/join", response_model=ManualJoinResponse, tags=["Meetings"])
async def manual_join(
    request: ManualJoinRequest,
    bot=Depends(get_meeting_bot_service)
) -> Dict[str, Any]:
    """
    Manually join a meeting by providing the meeting URL.
    
    Args:
        request: Manual join request with bot_name and meeting_url
        bot: Meeting bot service (injected)
    
    Returns:
        Manual join response with meeting details or error
    """
    try:
        logger.info(f"Manual join request: {request.bot_name} -> {request.meeting_url}")
        
        result = await bot.manual_join(
            bot_name=request.bot_name,
            meeting_url=request.meeting_url
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Manual join failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
