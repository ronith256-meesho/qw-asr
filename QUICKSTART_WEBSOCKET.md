# Quick Start: WebSocket Streaming ASR

Get up and running with WebSocket-based streaming ASR in 5 minutes.

## Prerequisites

- Python 3.9+
- CUDA-capable GPU (recommended)
- Qwen3-ASR repository cloned

## Step 1: Install Dependencies

```bash
cd Qwen3-ASR

# Install base Qwen-ASR with vLLM
pip install -e ".[vllm]"

# Install WebSocket dependencies
./install_websocket.sh
```

Or manually:
```bash
pip install fastapi uvicorn[standard] websockets pyaudio
```

## Step 2: Start the Server

```bash
qwen-asr-serve-websocket \
    --asr-model-path Qwen/Qwen3-ASR-1.7B \
    --gpu-memory-utilization 0.8 \
    --host 0.0.0.0 \
    --port 8000
```

**First run:** Model will download automatically (~3.4GB for 1.7B model)

Expected output:
```
Loading ASR model...
ASR model loaded successfully
Silero VAD loaded successfully
SessionManager initialized with VAD threshold=0.5
Starting WebSocket server at 0.0.0.0:8000
Open http://0.0.0.0:8000 in your browser
```

## Step 3: Test in Browser

1. Open `http://localhost:8000` in your browser
2. Click "Start Recording"
3. Allow microphone access
4. Speak naturally
5. Watch real-time transcripts appear

**You should see:**
- 📝 Yellow "Partial" boxes during speech
- ✅ Green "Final" boxes when you pause

## Step 4: Test with Python Client

### From Microphone:
```bash
python examples/example_websocket_client.py \
    --host localhost \
    --port 8000
```

### From Audio File:
```bash
python examples/example_websocket_client.py \
    --host localhost \
    --port 8000 \
    --audio-file path/to/audio.wav
```

Expected output:
```
INFO - Connecting to ws://localhost:8000/ws/asr
INFO - Session created: abc123...
INFO - Starting microphone streaming. Press Ctrl+C to stop.

[PARTIAL] Hello
[PARTIAL] Hello world
[FINAL] Language: English
        Text: Hello world how are you
        Speech ended: True
```

## Troubleshooting

### "Module websockets not found"
```bash
pip install websockets
```

### "PyAudio not found" (optional, for microphone)
- **macOS:** `brew install portaudio && pip install pyaudio`
- **Ubuntu:** `sudo apt-get install portaudio19-dev && pip install pyaudio`
- **Skip:** You can still use file-based streaming

### Server not responding
- Check if port 8000 is available
- Try different port: `--port 8001`
- Check firewall settings

### Transcripts cut off too early
- Increase silence threshold: `--silence-threshold 1.2`

### Transcripts not updating
- Check VAD threshold: try `--vad-threshold 0.3` (more sensitive)
- Verify audio is 16kHz, mono, float32

## Configuration Tips

### For Voice Bots:
```bash
qwen-asr-serve-websocket \
    --asr-model-path Qwen/Qwen3-ASR-1.7B \
    --silence-threshold 0.6 \
    --vad-threshold 0.6 \
    --min-speech-duration 0.2
```

### For Transcription (High Accuracy):
```bash
qwen-asr-serve-websocket \
    --asr-model-path Qwen/Qwen3-ASR-1.7B \
    --silence-threshold 1.5 \
    --chunk-size-sec 2.0
```

### For Noisy Environments:
```bash
qwen-asr-serve-websocket \
    --asr-model-path Qwen/Qwen3-ASR-1.7B \
    --vad-threshold 0.7
```

## Next Steps

- Read [WEBSOCKET_STREAMING.md](WEBSOCKET_STREAMING.md) for detailed documentation
- Read [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) for architecture details
- Integrate with your voice bot using the protocol examples
- Tune parameters for your use case

## Help

```bash
qwen-asr-serve-websocket --help
```

## Production Checklist

Before deploying:
- [ ] Test with real audio (not just samples)
- [ ] Verify endpointing works for your use case
- [ ] Load test with concurrent connections
- [ ] Set up monitoring (GPU usage, latency)
- [ ] Configure proper logging
- [ ] Use HTTPS/WSS for security
- [ ] Add authentication if needed

## Support

- GitHub Issues: [Qwen3-ASR Issues](https://github.com/QwenLM/Qwen3-ASR/issues)
- Documentation: See WEBSOCKET_STREAMING.md
- Examples: See `examples/example_websocket_client.py`
