# coding=utf-8
# Copyright 2026 The Alibaba Qwen team.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
WebSocket-based streaming ASR server with server-side VAD.

This implementation provides real-time ASR with:
- WebSocket communication for low-latency streaming
- Server-side VAD (Silero VAD) for robust speech detection
- Efficient KV cache management (reuses previous computations)
- Endpointing detection for natural conversation flow
"""
import argparse
import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
import torch
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from qwen_asr import Qwen3ASRModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============= VAD Integration =============

class SileroVAD:
    """Server-side Voice Activity Detection using Silero VAD."""
    
    def __init__(self, threshold: float = 0.5, sample_rate: int = 16000):
        """
        Initialize Silero VAD.
        
        Args:
            threshold: Speech probability threshold (0.0-1.0)
            sample_rate: Audio sample rate (must be 16000 for Silero)
        """
        self.threshold = threshold
        self.sample_rate = sample_rate
        
        try:
            # Load Silero VAD model
            self.model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                onnx=False
            )
            self.get_speech_timestamps = utils[0]
            logger.info("Silero VAD loaded successfully")
        except Exception as e:
            logger.warning(f"Failed to load Silero VAD: {e}. VAD will be disabled.")
            self.model = None
    
    def is_speech(self, audio: np.ndarray) -> float:
        """
        Check if audio contains speech.
        
        Args:
            audio: Audio samples (float32, 16kHz)
        
        Returns:
            Speech probability (0.0-1.0)
        """
        if self.model is None:
            return 1.0  # Assume speech if VAD unavailable
        
        try:
            # Convert to torch tensor
            audio_tensor = torch.from_numpy(audio).float()
            
            # Get speech probability
            speech_prob = self.model(audio_tensor, self.sample_rate).item()
            
            return speech_prob
        except Exception as e:
            logger.error(f"VAD error: {e}")
            return 1.0  # Assume speech on error


# ============= Streaming Session Manager =============

@dataclass
class StreamingSession:
    """Manages state for one streaming ASR session."""
    session_id: str
    asr_state: object  # ASRStreamingState from Qwen3ASRModel
    vad: SileroVAD
    
    # Audio buffering
    audio_buffer: np.ndarray
    
    # VAD state
    is_speaking: bool
    silence_duration: float  # seconds of silence
    speech_duration: float   # seconds of speech
    
    # Timestamps
    created_at: float
    last_activity: float
    
    # Configuration
    silence_threshold: float  # seconds of silence to trigger endpointing
    min_speech_duration: float  # minimum speech duration before processing
    vad_sample_size: int  # samples to accumulate before VAD check


class SessionManager:
    """Manages multiple streaming sessions."""
    
    def __init__(
        self,
        asr_model: Qwen3ASRModel,
        vad_threshold: float = 0.5,
        silence_threshold: float = 0.8,
        min_speech_duration: float = 0.3,
        session_ttl: float = 600.0,
    ):
        self.asr_model = asr_model
        self.sessions: Dict[str, StreamingSession] = {}
        self.vad_threshold = vad_threshold
        self.silence_threshold = silence_threshold
        self.min_speech_duration = min_speech_duration
        self.session_ttl = session_ttl
        
        logger.info(f"SessionManager initialized with VAD threshold={vad_threshold}")
    
    def create_session(
        self,
        context: str = "",
        language: Optional[str] = None,
        unfixed_chunk_num: int = 4,
        unfixed_token_num: int = 5,
        chunk_size_sec: float = 1.0,
    ) -> str:
        """Create a new streaming session."""
        session_id = uuid.uuid4().hex
        
        # Initialize ASR streaming state
        asr_state = self.asr_model.init_streaming_state(
            context=context,
            language=language,
            unfixed_chunk_num=unfixed_chunk_num,
            unfixed_token_num=unfixed_token_num,
            chunk_size_sec=chunk_size_sec,
        )
        
        # Create VAD instance
        vad = SileroVAD(threshold=self.vad_threshold)
        
        # Create session
        session = StreamingSession(
            session_id=session_id,
            asr_state=asr_state,
            vad=vad,
            audio_buffer=np.zeros((0,), dtype=np.float32),
            is_speaking=False,
            silence_duration=0.0,
            speech_duration=0.0,
            created_at=time.time(),
            last_activity=time.time(),
            silence_threshold=self.silence_threshold,
            min_speech_duration=self.min_speech_duration,
            vad_sample_size=int(0.1 * 16000),  # 100ms chunks for VAD
        )
        
        self.sessions[session_id] = session
        logger.info(f"Created session {session_id}")
        
        return session_id
    
    def get_session(self, session_id: str) -> Optional[StreamingSession]:
        """Get a session by ID."""
        session = self.sessions.get(session_id)
        if session:
            session.last_activity = time.time()
        return session
    
    def delete_session(self, session_id: str):
        """Delete a session."""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            try:
                self.asr_model.finish_streaming_transcribe(session.asr_state)
            except Exception as e:
                logger.error(f"Error finishing session {session_id}: {e}")
            
            del self.sessions[session_id]
            logger.info(f"Deleted session {session_id}")
    
    def cleanup_stale_sessions(self):
        """Remove sessions that haven't been active recently."""
        now = time.time()
        stale = [
            sid for sid, sess in self.sessions.items()
            if now - sess.last_activity > self.session_ttl
        ]
        
        for sid in stale:
            logger.info(f"Cleaning up stale session {sid}")
            self.delete_session(sid)


# ============= FastAPI WebSocket Server =============

app = FastAPI(title="Qwen3-ASR WebSocket Streaming Server")

# Global session manager
session_manager: Optional[SessionManager] = None


@app.get("/")
async def index():
    """Serve a simple HTML test client."""
    return HTMLResponse(HTML_CLIENT)


@app.websocket("/ws/asr")
async def websocket_asr_endpoint(websocket: WebSocket):
    """WebSocket endpoint for streaming ASR."""
    await websocket.accept()
    
    session_id = None
    
    try:
        # Wait for initial config message
        config_msg = await websocket.receive_json()
        
        if config_msg.get("type") != "config":
            await websocket.send_json({
                "type": "error",
                "message": "First message must be config"
            })
            await websocket.close()
            return
        
        # Create session
        session_id = session_manager.create_session(
            context=config_msg.get("context", ""),
            language=config_msg.get("language"),
            unfixed_chunk_num=config_msg.get("unfixed_chunk_num", 4),
            unfixed_token_num=config_msg.get("unfixed_token_num", 5),
            chunk_size_sec=config_msg.get("chunk_size_sec", 1.0),
        )
        
        session = session_manager.get_session(session_id)
        
        # Send session ID
        await websocket.send_json({
            "type": "session_created",
            "session_id": session_id
        })
        
        logger.info(f"WebSocket connected: session {session_id}")
        
        # Main streaming loop
        while True:
            try:
                message = await websocket.receive()
                
                if "bytes" in message:
                    # Audio data received
                    audio_bytes = message["bytes"]
                    
                    # Convert bytes to float32 audio
                    audio_chunk = np.frombuffer(audio_bytes, dtype=np.float32)
                    
                    # Process audio
                    result = await process_audio_chunk(session, audio_chunk)
                    
                    # Send result
                    if result:
                        await websocket.send_json(result)
                
                elif "text" in message:
                    # Control message
                    msg = json.loads(message["text"])
                    
                    if msg.get("type") == "finalize":
                        # Finalize transcription
                        final_result = await finalize_session(session)
                        await websocket.send_json(final_result)
                        break
                    
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected: session {session_id}")
                break
            except Exception as e:
                logger.error(f"Error in WebSocket loop: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": str(e)
                })
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })
    
    finally:
        # Cleanup
        if session_id:
            session_manager.delete_session(session_id)
        
        try:
            await websocket.close()
        except:
            pass


async def process_audio_chunk(
    session: StreamingSession,
    audio_chunk: np.ndarray
) -> Optional[Dict]:
    """
    Process incoming audio chunk with VAD and streaming ASR.
    
    Returns:
        Response dict to send to client, or None if no update
    """
    # Add to buffer
    session.audio_buffer = np.concatenate([session.audio_buffer, audio_chunk])
    
    # Run VAD on accumulated buffer (check every 100ms worth of audio)
    while len(session.audio_buffer) >= session.vad_sample_size:
        vad_chunk = session.audio_buffer[:session.vad_sample_size]
        speech_prob = session.vad.is_speech(vad_chunk)
        
        chunk_duration = len(vad_chunk) / 16000.0
        
        if speech_prob >= session.vad.threshold:
            # Speech detected
            if not session.is_speaking:
                logger.info(f"Speech started (session {session.session_id})")
                session.is_speaking = True
                session.silence_duration = 0.0
            
            session.speech_duration += chunk_duration
            
            # Feed to ASR if we have enough speech
            if session.speech_duration >= session.min_speech_duration:
                # Process through ASR
                session_manager.asr_model.streaming_transcribe(
                    vad_chunk,
                    session.asr_state
                )
                
                # Remove processed audio from buffer
                session.audio_buffer = session.audio_buffer[session.vad_sample_size:]
                
                # Return partial transcript
                return {
                    "type": "partial",
                    "language": session.asr_state.language or "",
                    "text": session.asr_state.text or "",
                    "timestamp": time.time(),
                }
            else:
                # Accumulating speech, remove from buffer but don't process yet
                session.audio_buffer = session.audio_buffer[session.vad_sample_size:]
        
        else:
            # Silence detected
            session.silence_duration += chunk_duration
            
            if session.is_speaking:
                # Check for endpointing
                if session.silence_duration >= session.silence_threshold:
                    logger.info(f"Speech ended (session {session.session_id})")
                    
                    # Finalize the current utterance
                    session_manager.asr_model.finish_streaming_transcribe(session.asr_state)
                    
                    result = {
                        "type": "final",
                        "language": session.asr_state.language or "",
                        "text": session.asr_state.text or "",
                        "timestamp": time.time(),
                        "is_speech_final": True,
                    }
                    
                    # Reset state for next utterance
                    session.is_speaking = False
                    session.silence_duration = 0.0
                    session.speech_duration = 0.0
                    session.audio_buffer = np.zeros((0,), dtype=np.float32)
                    
                    # Re-initialize streaming state for next utterance
                    session.asr_state = session_manager.asr_model.init_streaming_state(
                        context=session.asr_state.context,
                        language=session.asr_state.force_language,
                        unfixed_chunk_num=session.asr_state.unfixed_chunk_num,
                        unfixed_token_num=session.asr_state.unfixed_token_num,
                        chunk_size_sec=session.asr_state.chunk_size_sec,
                    )
                    
                    return result
            
            # Remove silence from buffer
            session.audio_buffer = session.audio_buffer[session.vad_sample_size:]
    
    return None


async def finalize_session(session: StreamingSession) -> Dict:
    """Finalize a streaming session and return final transcript."""
    try:
        session_manager.asr_model.finish_streaming_transcribe(session.asr_state)
        
        return {
            "type": "final",
            "language": session.asr_state.language or "",
            "text": session.asr_state.text or "",
            "timestamp": time.time(),
            "is_speech_final": True,
        }
    except Exception as e:
        logger.error(f"Error finalizing session: {e}")
        return {
            "type": "error",
            "message": str(e)
        }


# ============= HTML Test Client =============

HTML_CLIENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Qwen3-ASR WebSocket Streaming</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .container {
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 800px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        
        h1 {
            color: #333;
            margin-bottom: 30px;
            text-align: center;
            font-size: 28px;
        }
        
        .controls {
            display: flex;
            gap: 15px;
            margin-bottom: 30px;
            justify-content: center;
        }
        
        button {
            padding: 12px 30px;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        #startBtn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        
        #startBtn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        
        #stopBtn {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
        }
        
        #stopBtn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(245, 87, 108, 0.4);
        }
        
        .status {
            text-align: center;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 30px;
            font-weight: 600;
        }
        
        .status.idle { background: #e0e7ff; color: #4f46e5; }
        .status.connecting { background: #fef3c7; color: #d97706; }
        .status.listening { background: #d1fae5; color: #059669; }
        .status.error { background: #fee2e2; color: #dc2626; }
        
        .transcript-box {
            background: #f9fafb;
            border: 2px solid #e5e7eb;
            border-radius: 10px;
            padding: 20px;
            min-height: 200px;
            max-height: 400px;
            overflow-y: auto;
        }
        
        .transcript-item {
            margin-bottom: 15px;
            padding: 10px;
            border-radius: 8px;
            animation: fadeIn 0.3s ease;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .transcript-item.partial {
            background: #fef3c7;
            border-left: 4px solid #f59e0b;
        }
        
        .transcript-item.final {
            background: #d1fae5;
            border-left: 4px solid #10b981;
        }
        
        .transcript-label {
            font-size: 12px;
            font-weight: 600;
            color: #6b7280;
            margin-bottom: 5px;
        }
        
        .transcript-text {
            font-size: 16px;
            color: #111827;
            line-height: 1.5;
        }
        
        .transcript-meta {
            font-size: 12px;
            color: #9ca3af;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎤 Qwen3-ASR WebSocket Streaming</h1>
        
        <div class="controls">
            <button id="startBtn">Start Recording</button>
            <button id="stopBtn" disabled>Stop Recording</button>
        </div>
        
        <div id="status" class="status idle">Idle - Click "Start Recording" to begin</div>
        
        <div class="transcript-box" id="transcriptBox">
            <p style="text-align: center; color: #9ca3af;">Your transcriptions will appear here...</p>
        </div>
    </div>

    <script>
        let ws = null;
        let audioContext = null;
        let mediaStream = null;
        let processor = null;
        let source = null;
        
        const startBtn = document.getElementById('startBtn');
        const stopBtn = document.getElementById('stopBtn');
        const statusEl = document.getElementById('status');
        const transcriptBox = document.getElementById('transcriptBox');
        
        function setStatus(message, className) {
            statusEl.textContent = message;
            statusEl.className = `status ${className}`;
        }
        
        function addTranscript(type, text, language, timestamp) {
            // Remove placeholder if exists
            if (transcriptBox.children.length === 1 && transcriptBox.children[0].tagName === 'P') {
                transcriptBox.innerHTML = '';
            }
            
            const item = document.createElement('div');
            item.className = `transcript-item ${type}`;
            
            const label = document.createElement('div');
            label.className = 'transcript-label';
            label.textContent = type === 'partial' ? '📝 Partial' : '✅ Final';
            
            const text_el = document.createElement('div');
            text_el.className = 'transcript-text';
            text_el.textContent = text || '(empty)';
            
            const meta = document.createElement('div');
            meta.className = 'transcript-meta';
            meta.textContent = `Language: ${language || 'unknown'} | ${new Date(timestamp * 1000).toLocaleTimeString()}`;
            
            item.appendChild(label);
            item.appendChild(text_el);
            item.appendChild(meta);
            
            transcriptBox.appendChild(item);
            transcriptBox.scrollTop = transcriptBox.scrollHeight;
        }
        
        async function startRecording() {
            try {
                setStatus('Connecting...', 'connecting');
                startBtn.disabled = true;
                
                // Create WebSocket connection
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws/asr`;
                ws = new WebSocket(wsUrl);
                
                ws.onopen = async () => {
                    console.log('WebSocket connected');
                    
                    // Send config
                    ws.send(JSON.stringify({
                        type: 'config',
                        context: '',
                        language: null,
                        unfixed_chunk_num: 4,
                        unfixed_token_num: 5,
                        chunk_size_sec: 1.0
                    }));
                };
                
                ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    console.log('Received:', data);
                    
                    if (data.type === 'session_created') {
                        console.log('Session created:', data.session_id);
                        startAudioCapture();
                    } else if (data.type === 'partial') {
                        addTranscript('partial', data.text, data.language, data.timestamp);
                    } else if (data.type === 'final') {
                        addTranscript('final', data.text, data.language, data.timestamp);
                    } else if (data.type === 'error') {
                        setStatus(`Error: ${data.message}`, 'error');
                    }
                };
                
                ws.onerror = (error) => {
                    console.error('WebSocket error:', error);
                    setStatus('Connection error', 'error');
                };
                
                ws.onclose = () => {
                    console.log('WebSocket closed');
                    stopRecording();
                };
                
            } catch (error) {
                console.error('Error starting recording:', error);
                setStatus(`Error: ${error.message}`, 'error');
                startBtn.disabled = false;
            }
        }
        
        async function startAudioCapture() {
            try {
                mediaStream = await navigator.mediaDevices.getUserMedia({
                    audio: {
                        channelCount: 1,
                        sampleRate: 16000,
                        echoCancellation: true,
                        noiseSuppression: true,
                        autoGainControl: true
                    }
                });
                
                audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
                source = audioContext.createMediaStreamSource(mediaStream);
                processor = audioContext.createScriptProcessor(4096, 1, 1);
                
                processor.onaudioprocess = (e) => {
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        const audioData = e.inputBuffer.getChannelData(0);
                        const float32Array = new Float32Array(audioData);
                        ws.send(float32Array.buffer);
                    }
                };
                
                source.connect(processor);
                processor.connect(audioContext.destination);
                
                setStatus('🎙️ Listening...', 'listening');
                stopBtn.disabled = false;
                
            } catch (error) {
                console.error('Error capturing audio:', error);
                setStatus(`Microphone error: ${error.message}`, 'error');
            }
        }
        
        function stopRecording() {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'finalize' }));
                ws.close();
            }
            
            if (processor) {
                processor.disconnect();
                processor.onaudioprocess = null;
            }
            
            if (source) {
                source.disconnect();
            }
            
            if (audioContext) {
                audioContext.close();
            }
            
            if (mediaStream) {
                mediaStream.getTracks().forEach(track => track.stop());
            }
            
            ws = null;
            audioContext = null;
            mediaStream = null;
            processor = null;
            source = null;
            
            setStatus('Stopped', 'idle');
            startBtn.disabled = false;
            stopBtn.disabled = true;
        }
        
        startBtn.addEventListener('click', startRecording);
        stopBtn.addEventListener('click', stopRecording);
    </script>
</body>
</html>
"""


# ============= CLI Entry Point =============

def parse_args():
    parser = argparse.ArgumentParser(
        description="Qwen3-ASR WebSocket Streaming Server with Server-side VAD"
    )
    
    # Model args
    parser.add_argument(
        "--asr-model-path",
        default="Qwen/Qwen3-ASR-1.7B",
        help="ASR model name or local path"
    )
    parser.add_argument(
        "--gpu-memory-utilization",
        type=float,
        default=0.8,
        help="vLLM GPU memory utilization"
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=32,
        help="Maximum tokens to generate per chunk"
    )
    
    # Server args
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Server host"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server port"
    )
    
    # VAD args
    parser.add_argument(
        "--vad-threshold",
        type=float,
        default=0.5,
        help="VAD speech probability threshold (0.0-1.0)"
    )
    parser.add_argument(
        "--silence-threshold",
        type=float,
        default=0.8,
        help="Seconds of silence to trigger endpointing"
    )
    parser.add_argument(
        "--min-speech-duration",
        type=float,
        default=0.3,
        help="Minimum speech duration before ASR processing (seconds)"
    )
    
    # Streaming ASR args
    parser.add_argument(
        "--unfixed-chunk-num",
        type=int,
        default=4,
        help="Number of chunks without prefix rollback"
    )
    parser.add_argument(
        "--unfixed-token-num",
        type=int,
        default=5,
        help="Number of tokens to rollback for prefix"
    )
    parser.add_argument(
        "--chunk-size-sec",
        type=float,
        default=1.0,
        help="ASR chunk size in seconds"
    )
    
    return parser.parse_args()


def main():
    args = parse_args()
    
    global session_manager
    
    logger.info("Loading ASR model...")
    asr_model = Qwen3ASRModel.LLM(
        model=args.asr_model_path,
        gpu_memory_utilization=args.gpu_memory_utilization,
        max_new_tokens=args.max_new_tokens,
    )
    logger.info("ASR model loaded successfully")
    
    # Initialize session manager
    session_manager = SessionManager(
        asr_model=asr_model,
        vad_threshold=args.vad_threshold,
        silence_threshold=args.silence_threshold,
        min_speech_duration=args.min_speech_duration,
    )
    
    # Start cleanup task
    async def cleanup_task():
        while True:
            await asyncio.sleep(60)  # Run every minute
            session_manager.cleanup_stale_sessions()
    
    # Run server
    import uvicorn
    
    logger.info(f"Starting WebSocket server at {args.host}:{args.port}")
    logger.info(f"Open http://{args.host}:{args.port} in your browser")
    
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
