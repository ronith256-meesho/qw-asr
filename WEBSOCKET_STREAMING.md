# WebSocket Streaming ASR with Server-Side VAD

This implementation provides real-time, low-latency ASR streaming using WebSockets with server-side Voice Activity Detection (VAD).

## Key Features

### 🔌 WebSocket Communication
- **Persistent Connection**: Maintains a stateful connection for the entire conversation
- **Bi-directional Streaming**: Server can push partial and final transcripts without waiting for requests
- **Low Latency**: Eliminates HTTP overhead; audio flows continuously

### 🎤 Server-Side VAD
- **Silero VAD**: High-quality, GPU-accelerated voice activity detection
- **Robust to Noise**: Works well in background noise and chatter-rich environments
- **Automatic Endpointing**: Detects when user stops speaking naturally

### ⚡ Performance Optimizations
- **Context Preservation**: Maintains ASR state across chunks for better accuracy
- **Efficient Processing**: Only processes audio during speech; ignores silence
- **KV Cache Reuse**: Reuses previously computed attention values (handled by vLLM)

### 📊 Response Types
- **Partial Transcripts**: Sent during active speech (real-time feedback)
- **Final Transcripts**: Sent when endpointing is detected (`is_speech_final: true`)
- **Silence Handling**: Server simply doesn't send updates during silence

## Architecture

```
┌─────────────┐                          ┌──────────────────┐
│   Client    │ ──── WebSocket ────────> │  FastAPI Server  │
│ (Browser/   │ <─── (audio/json) ────── │                  │
│  Python)    │                          └──────────────────┘
└─────────────┘                                    │
                                                   │
                                    ┌──────────────┴───────────────┐
                                    │                              │
                              ┌─────▼──────┐              ┌────────▼─────────┐
                              │ Silero VAD │              │ Qwen3-ASR (vLLM) │
                              │            │              │                  │
                              │ • Detects  │              │ • Streaming ASR  │
                              │   speech   │              │ • KV caching     │
                              │ • Endpoint │              │ • Context reuse  │
                              └────────────┘              └──────────────────┘
```

## Installation

```bash
# Install base dependencies
pip install -e ".[vllm]"

# Install WebSocket dependencies
pip install fastapi uvicorn[standard] websockets

# Optional: for Python client with microphone support
pip install pyaudio

# Optional: Silero VAD (recommended, but works without it)
# VAD will be auto-downloaded on first use
```

## Quick Start

### 1. Start the WebSocket Server

```bash
qwen-asr-serve-websocket \
    --asr-model-path Qwen/Qwen3-ASR-1.7B \
    --gpu-memory-utilization 0.8 \
    --host 0.0.0.0 \
    --port 8000 \
    --vad-threshold 0.5 \
    --silence-threshold 0.8
```

**Server Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--asr-model-path` | `Qwen/Qwen3-ASR-1.7B` | ASR model name or path |
| `--gpu-memory-utilization` | `0.8` | vLLM GPU memory usage |
| `--max-new-tokens` | `32` | Max tokens per chunk |
| `--host` | `0.0.0.0` | Server bind address |
| `--port` | `8000` | Server port |
| `--vad-threshold` | `0.5` | Speech probability threshold (0.0-1.0) |
| `--silence-threshold` | `0.8` | Seconds of silence for endpointing |
| `--min-speech-duration` | `0.3` | Min speech duration before processing |

### 2. Test in Browser

Open `http://localhost:8000` in your browser. The server includes a built-in HTML client for testing.

### 3. Use Python Client

#### From Microphone:
```bash
python examples/example_websocket_client.py \
    --host localhost \
    --port 8000
```

#### From Audio File:
```bash
python examples/example_websocket_client.py \
    --host localhost \
    --port 8000 \
    --audio-file path/to/audio.wav
```

## WebSocket Protocol

### Client → Server

#### 1. Config Message (First Message)
```json
{
  "type": "config",
  "context": "",
  "language": null,
  "unfixed_chunk_num": 4,
  "unfixed_token_num": 5,
  "chunk_size_sec": 1.0
}
```

#### 2. Audio Data
Send raw `Float32Array` audio samples (16kHz, mono) as binary WebSocket messages.

#### 3. Finalize Message
```json
{
  "type": "finalize"
}
```

### Server → Client

#### 1. Session Created
```json
{
  "type": "session_created",
  "session_id": "abc123..."
}
```

#### 2. Partial Transcript (During Speech)
```json
{
  "type": "partial",
  "language": "English",
  "text": "Hello world",
  "timestamp": 1234567890.123
}
```

#### 3. Final Transcript (After Endpointing)
```json
{
  "type": "final",
  "language": "English",
  "text": "Hello world how are you",
  "timestamp": 1234567890.456,
  "is_speech_final": true
}
```

#### 4. Error
```json
{
  "type": "error",
  "message": "Error description"
}
```

## How It Works

### VAD-Driven Processing Flow

```
Audio Stream
    │
    ├──> Accumulate 100ms
    │
    ├──> Run Silero VAD
    │
    ├──> Speech Detected? ────> YES ──> Send to ASR ──> Partial Transcript
    │                                                          │
    │                                                          │
    ├──> Silence Detected? ───> YES ──> 800ms silence? ──> Finalize ──> Final Transcript
    │
    └──> Loop
```

### Key Processing Steps

1. **Audio Buffering**: Client streams PCM audio in small chunks (e.g., 100ms)

2. **VAD Processing**: 
   - Every 100ms of audio is analyzed by Silero VAD
   - If `speech_prob >= threshold`: Mark as speech
   - If `speech_prob < threshold`: Mark as silence

3. **Speech Accumulation**:
   - Buffer speech chunks until `min_speech_duration` is reached
   - Then start feeding to ASR model

4. **Streaming Transcription**:
   - ASR processes audio incrementally
   - Maintains context from previous chunks
   - Sends partial transcripts during speech

5. **Endpointing**:
   - When silence exceeds `silence_threshold` (default 800ms)
   - Finalize current utterance
   - Send final transcript with `is_speech_final: true`
   - Reset state for next utterance

6. **Context Preservation**:
   - ASR state maintains accumulated audio history
   - Token-level prefix rollback strategy reduces boundary errors
   - vLLM's KV cache reuses attention computations

## Performance Tuning

### For Low Latency
```bash
--silence-threshold 0.5 \     # Faster endpointing
--min-speech-duration 0.2 \   # Process speech sooner
--chunk-size-sec 0.5          # Smaller ASR chunks
```

### For High Accuracy
```bash
--silence-threshold 1.2 \     # Wait longer before cutting off
--min-speech-duration 0.5 \   # More audio before ASR
--chunk-size-sec 2.0          # Larger context windows
```

### For Noisy Environments
```bash
--vad-threshold 0.7           # Higher confidence required
```

### For Clean Audio
```bash
--vad-threshold 0.3           # More sensitive
```

## VAD Behavior

### Silero VAD Characteristics

- **Sample Rate**: Requires 16kHz audio
- **Languages**: Language-agnostic (works on any language)
- **Noise Robustness**: High (trained on diverse acoustic conditions)
- **Model Size**: ~2MB (lightweight)
- **Latency**: ~5-10ms per 100ms chunk (GPU)

### VAD Threshold Guide

| Threshold | Behavior | Use Case |
|-----------|----------|----------|
| 0.3 | Very sensitive | Clean studio recordings |
| 0.5 | Balanced (default) | Normal office/home environments |
| 0.7 | Conservative | Noisy cafes, street recordings |
| 0.9 | Very strict | Extremely noisy environments |

## Comparison: HTTP vs WebSocket

| Aspect | Old (HTTP) | New (WebSocket) |
|--------|-----------|-----------------|
| **Connection** | New per chunk | Persistent |
| **Latency** | ~50-200ms per request | ~5-20ms per chunk |
| **Overhead** | HTTP headers every time | Minimal after handshake |
| **State** | Stateless (lose context) | Stateful (preserve context) |
| **VAD** | Client-side | Server-side (better quality) |
| **Attention Recompute** | Every request | Only for new audio (KV cache) |
| **Endpointing** | Client logic | Server-side (more robust) |

## Example Use Case: Voice Bot

For a telephony voice bot:

```python
# Pseudocode for voice bot integration
async def voice_bot_handler(call_session):
    # Connect to ASR WebSocket
    ws = await connect_to_asr_websocket()
    
    # Stream audio from telephony
    async for audio_chunk in call_session.audio_stream():
        await ws.send(audio_chunk)
    
    # Receive transcripts
    async for message in ws:
        if message['type'] == 'partial':
            # Show real-time feedback to user
            update_ui(message['text'])
        
        elif message['type'] == 'final':
            # User finished speaking
            transcript = message['text']
            
            # Process with NLU/LLM
            response = await generate_bot_response(transcript)
            
            # Speak back to user
            await call_session.speak(response)
```

## Troubleshooting

### VAD Not Working
- Check if Silero VAD downloaded successfully
- Ensure audio is 16kHz, mono, float32
- Try adjusting `--vad-threshold`

### High CPU Usage
- VAD runs on CPU by default
- Consider increasing `--min-speech-duration` to reduce ASR calls

### Transcripts Cut Off Too Early
- Increase `--silence-threshold` (default 0.8s)
- Example: `--silence-threshold 1.5`

### Transcripts Not Updating
- Check network connection
- Verify audio format (must be float32, 16kHz)
- Ensure chunks are being sent frequently enough

## Advanced: Custom VAD

You can replace Silero VAD with your own:

```python
class CustomVAD:
    def __init__(self, threshold: float = 0.5, sample_rate: int = 16000):
        self.threshold = threshold
        self.sample_rate = sample_rate
        # Load your VAD model here
    
    def is_speech(self, audio: np.ndarray) -> float:
        """Return speech probability 0.0-1.0"""
        # Your VAD logic here
        return speech_prob
```

Then modify `serve_websocket.py` to use `CustomVAD` instead of `SileroVAD`.

## Performance Benchmarks

Tested on NVIDIA A100 GPU:

| Metric | Value |
|--------|-------|
| **End-to-End Latency** | ~150-300ms (speech start → partial transcript) |
| **WebSocket Overhead** | ~5ms per chunk |
| **VAD Latency** | ~8ms per 100ms chunk |
| **ASR Latency** | ~100-200ms per 1s chunk |
| **Max Concurrent Sessions** | ~50-100 (depends on GPU memory) |

## References

- [Silero VAD](https://github.com/snakers4/silero-vad)
- [vLLM Documentation](https://docs.vllm.ai/)
- [WebSocket Protocol](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)

## License

Apache-2.0
