$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Start-Process powershell -ArgumentList "-NoExit", "-Command", @"
cd '$root\Streaming_Backend'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
"@

Start-Sleep -Seconds 3

Start-Process powershell -ArgumentList "-NoExit", "-Command", @"
cd '$root\RTAPS_Frontend'
npm start
"@

Start-Sleep -Seconds 5

Start-Process powershell -ArgumentList "-NoExit", "-Command", @"
cd '$root\Streaming_Backend'
python pupil_capture_bridge.py --stream_id 001
"@