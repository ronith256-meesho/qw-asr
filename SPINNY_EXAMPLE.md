# Example: Running WebSocket Server with Custom Prompts

## For Spinny Voice Bot (Hindi + English)

```bash
qwen-asr-serve-websocket \
    --asr-model-path Qwen/Qwen3-ASR-1.7B \
    --generate-self-signed-cert \
    --default-language "Hindi" \
    --default-prompt "You are transcribing a voice call for Spinny, a used car marketplace in India. Only transcribe the primary speaker (the customer). Focus on Hindi and English. Accurately capture car-related terms, model names, and automotive terminology. This is a customer service call." \
    --vad-threshold 0.6 \
    --silence-threshold 0.6 \
    --min-speech-duration 0.2 \
    --chunk-size-sec 0.8
```

## Explanation

### Language Settings
- `--default-language "Hindi"` - Tells ASR to expect Hindi
- Note: Model can auto-detect Hindi/English code-mixing

### Custom Prompt
The prompt helps the model:
- ✅ Focus on primary speaker (filter out background voices)
- ✅ Understand domain context (Spinny = cars)
- ✅ Better recognize car models and automotive terms  
- ✅ Handle Hindi-English code-switching

### Performance Tuning (Voice Bot Optimized)
- `--vad-threshold 0.6` - Slightly higher for noisy call centers
- `--silence-threshold 0.6` - Faster turn-taking (600ms pause)
- `--min-speech-duration 0.2` - Very responsive (200ms)
- `--chunk-size-sec 0.8` - Smaller chunks for lower latency

## Per-Session Custom Configuration

You can also override settings per WebSocket connection:

```json
{
  "type": "config",
  "language": "Hindi",
  "prompt": "Transcribe customer speaking about car issues. Focus on Hindi and English.",
  "context": "Call ID: 12345, Customer: Rahul Sharma",
  "chunk_size_sec": 0.8
}
```

## Example Code (Python Client)

```python
import asyncio
import websockets
import json
import numpy as np

async def connect_spinny_bot():
    uri = "wss://localhost:8000/ws/asr"
    
    # Disable SSL verification for self-signed cert (testing only)
    import ssl
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    async with websockets.connect(uri, ssl=ssl_context) as ws:
        # Send config with Spinny-specific prompt
        config = {
            "type": "config",
            "language": "Hindi",  # Can also be "English" or None for auto-detect
            "prompt": """You are transcribing a customer service call for Spinny used cars. 
                         Only transcribe the primary speaker (customer). 
                         This is Hindi-English code-mixed conversation about cars.""",
            "context": "Spinny Customer Service - Used Cars",
            "chunk_size_sec": 0.8,
            "unfixed_chunk_num": 2,
            "unfixed_token_num": 3
        }
        
        await ws.send(json.dumps(config))
        
        # Wait for session created
        response = await ws.receive()
        print(json.loads(response))
        
        # Your audio streaming code here
        # ...

asyncio.run(connect_spinny_bot())
```

## Expected Behavior

### With Proper Prompting:
```
[PARTIAL] hello i want to buy a used car
[PARTIAL] hello i want to buy a used swift
[FINAL] hello i want to buy a used swift petrol model
```

### Without Prompting:
```
[PARTIAL] hello i want to buy [background noise transcribed]
[PARTIAL] hello i want to buy [other speaker transcribed]
[FINAL] hello i want to buy something [incorrect]
```

## Multi-Language Support

### Hindi + English (Code-Mixing)
```bash
--default-language "Hindi"
```

This works well for conversations like:
> "Main ek car kharidna chahta hoon, preferably Swift"

### English Only
```bash
--default-language "English"
```

### Auto-Detect
```bash
# Don't set --default-language
```

## Performance Impact

| Setting | Latency | Accuracy | Use Case |
|---------|---------|----------|----------|
| With prompt | Same | ✅ Better | Recommended |
| With language | Same | ✅ Better | Recommended |
| Fast settings | ⚡ 200-400ms | Good | Interactive bots |
| Accuracy settings | 🐌 500-800ms | ✅ Best | Transcription |

## Testing the Setup

### 1. Start Server
```bash
qwen-asr-serve-websocket \
    --asr-model-path Qwen/Qwen3-ASR-1.7B \
    --generate-self-signed-cert \
    --default-language "Hindi" \
    --default-prompt "Spinny customer service call. Transcribe primary speaker only." \
    --vad-threshold 0.6 \
    --silence-threshold 0.6
```

### 2. Open Browser
```
https://localhost:8000
```

### 3. Test Phrases (Hindi-English)
Try saying:
- "Main ek Swift kharidna chahta hoon"
- "Do you have used Honda City?"
- "Mujhe automatic transmission chahiye"

### 4. Check Logs
Server will show:
```
Created session abc123 (language: Hindi, prompt: Spinny customer service...)
Speech started (session abc123)
Speech ended (session abc123), finalizing...
```

## Troubleshooting

### Transcription Too Slow
- Reduce `--silence-threshold` (try 0.4)
- Reduce `--chunk-size-sec` (try 0.5)

### Missing Initial Words
- **FIXED** in latest version - now processes immediately
- Check logs for "Speech started" message

### Finalization Takes Time
- **FIXED** in latest version - flushes remaining audio
- Should be < 100ms now

### Wrong Language Detected
- Set explicit `--default-language "Hindi"`
- Or send in config: `"language": "Hindi"`

### Background Noise Transcribed
- Increase `--vad-threshold` (try 0.7)
- Add prompt: "Only transcribe primary speaker"

## Advanced: Multiple Languages

For calls that might be in different languages:

```python
# Option 1: Auto-detect (no language specified)
config = {
    "type": "config",
    "language": None,  # Let model detect
    "prompt": "Customer service call, primary speaker only"
}

# Option 2: Specify expected languages in prompt
config = {
    "type": "config",  
    "language": None,
    "prompt": "Transcribe in Hindi or English. Primary speaker only."
}
```

## Production Checklist

- [ ] Set appropriate `--default-language`
- [ ] Add domain-specific prompt (Spinny, cars, etc.)
- [ ] Tune VAD threshold for your noise level
- [ ] Tune silence threshold for turn-taking speed
- [ ] Test with real customer recordings
- [ ] Monitor latency metrics
- [ ] Set up proper SSL certificate (not self-signed)
- [ ] Add authentication
- [ ] Log transcripts for quality monitoring

## Getting Help

- Check server logs for detailed processing info
- Try without prompt first to establish baseline
- Compare transcripts with/without language setting
- Test VAD threshold with your audio environment
