# WebSocket Streaming ASR Architecture Diagrams

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLIENT SIDE                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐   │
│  │ Microphone   │────────>│  Resampler   │────────>│  WebSocket   │   │
│  │   (Audio)    │         │  to 16kHz    │         │    Client    │   │
│  └──────────────┘         └──────────────┘         └──────┬───────┘   │
│                                                             │           │
│                                                   Sends Float32 PCM     │
│                                                             │           │
└─────────────────────────────────────────────────────────────┼───────────┘
                                                              │
                                    WebSocket (Persistent)   │
                              ┌─────────────────────────────┼───────────┐
                              │  Binary: Audio chunks       │           │
                              │  JSON: Config, control      │           │
                              └─────────────────────────────┼───────────┘
                                                              │
┌─────────────────────────────────────────────────────────────┼───────────┐
│                          SERVER SIDE                        │           │
├─────────────────────────────────────────────────────────────┼───────────┤
│                                                             │           │
│  ┌──────────────────────────────────────────────────────────▼─────────┐ │
│  │                    FastAPI WebSocket Server                        │ │
│  │                                                                    │ │
│  │  ┌──────────────────────────────────────────────────────────────┐ │ │
│  │  │                    Session Manager                            │ │ │
│  │  │                                                               │ │ │
│  │  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐ │ │ │
│  │  │  │ Session 1      │  │ Session 2      │  │ Session N      │ │ │ │
│  │  │  │ • Audio buffer │  │ • Audio buffer │  │ • Audio buffer │ │ │ │
│  │  │  │ • ASR state    │  │ • ASR state    │  │ • ASR state    │ │ │ │
│  │  │  │ • VAD state    │  │ • VAD state    │  │ • VAD state    │ │ │ │
│  │  │  └────────────────┘  └────────────────┘  └────────────────┘ │ │ │
│  │  └───────────────────────────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                          │                            │                  │
│                          │                            │                  │
│              ┌───────────▼────────────┐   ┌──────────▼────────────┐    │
│              │                        │   │                        │    │
│              │    Silero VAD          │   │   Qwen3-ASR (vLLM)    │    │
│              │    (Server GPU/CPU)    │   │      (Server GPU)     │    │
│              │                        │   │                        │    │
│              │  • Speech detection   │   │  • Streaming decode    │    │
│              │  • Noise robust       │   │  • KV cache (vLLM)     │    │
│              │  • Endpointing        │   │  • Context preservation│    │
│              │  • 100ms chunks       │   │  • Token rollback      │    │
│              │                        │   │                        │    │
│              └────────────────────────┘   └────────────────────────┘    │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Sends JSON responses:
                                    │ • partial transcripts
                                    │ • final transcripts
                                    │ • is_speech_final flag
                                    │
                              Back to client
```

## Processing Flow

```
┌───────────────────────────────────────────────────────────────────────┐
│                    Audio Processing Pipeline                          │
└───────────────────────────────────────────────────────────────────────┘

    Audio arrives from WebSocket
            │
            ▼
    ┌───────────────┐
    │ Add to buffer │  ◄──── Accumulate 100ms
    └───────┬───────┘
            │
            ▼
    ┌───────────────────┐
    │ Run Silero VAD    │  ◄──── Check speech probability
    └───────┬───────────┘
            │
            ▼
    ┌─────────────────────────┐
    │ Speech probability      │
    │   >= threshold?         │
    └────┬──────────────┬─────┘
         │ YES          │ NO
         │              │
         ▼              ▼
    ┌────────┐     ┌─────────┐
    │ SPEECH │     │ SILENCE │
    └────┬───┘     └────┬────┘
         │              │
         ▼              │
    ┌──────────────────┐│
    │ Was silent       ││
    │ before?          ││
    └────┬──────┬──────┘│
         │ YES  │ NO    │
         │      │       │
         ▼      ▼       ▼
     [Log      [Add    [Was
      speech    to      speaking
      start]    accum.  before?]
                buffer]    │
         │      │       │
         │      ▼       ▼
         │  ┌─────────────────┐
         │  │ Accumulated      │
         │  │ >= min_duration? │
         │  └────┬──────┬──────┘
         │       │ YES  │ NO
         │       │      │
         │       ▼      │
         │   ┌────────────────┐
         │   │ Send to ASR    │
         │   │ streaming      │
         │   └────┬───────────┘
         │        │
         │        ▼
         │   ┌────────────────┐
         │   │ Get partial    │◄──┐
         │   │ transcript     │   │
         │   └────┬───────────┘   │
         │        │               │
         │        ▼               │
         │   ┌────────────────┐   │
         │   │ Send to client │   │
         │   │ (type: partial)│   │
         │   └────────────────┘   │
         │                        │
         └────────────────────────┘
                     │
                     │ [Continue until silence detected]
                     │
                     ▼
         [Silence detected during speech]
                     │
                     ▼
         ┌────────────────────────┐
         │ Silence duration       │
         │ >= silence_threshold?  │
         └────┬──────────────┬────┘
              │ YES          │ NO
              │              │
              ▼              │
         ┌────────────┐      │
         │ ENDPOINTING│      │
         │ DETECTED   │      │
         └────┬───────┘      │
              │              │
              ▼              │
         ┌────────────┐      │
         │ Finalize   │      │
         │ utterance  │      │
         └────┬───────┘      │
              │              │
              ▼              │
         ┌────────────┐      │
         │ Get final  │      │
         │ transcript │      │
         └────┬───────┘      │
              │              │
              ▼              │
         ┌────────────────────┐
         │ Send to client     │
         │ (type: final,      │
         │ is_speech_final:   │
         │ true)              │
         └────┬───────────────┘
              │
              ▼
         ┌────────────────┐
         │ Reset state    │
         │ for next       │
         │ utterance      │
         └────────────────┘
              │
              └──────► [Back to top, ready for next speech]
```

## Comparison: Old vs New

```
╔════════════════════════════════════════════════════════════════════════╗
║                    OLD APPROACH (HTTP API)                             ║
╚════════════════════════════════════════════════════════════════════════╝

Client                          Server
  │                               │
  ├─── HTTP POST (chunk 1) ─────>│
  │    • Headers (overhead)       │
  │    • Audio data               │
  │    • New request              │
  │                               ├─── Compute attention (ALL audio)
  │                               ├─── Generate tokens
  │                               │
  │<──── Response (chunk 1) ──────┤
  │                               │
  ├─── HTTP POST (chunk 2) ─────>│  [No state preserved]
  │    • Headers (overhead)       │
  │    • Audio data               │
  │    • New request              │
  │                               ├─── Compute attention (ALL audio AGAIN)
  │                               ├─── Generate tokens
  │                               │
  │<──── Response (chunk 2) ──────┤
  │                               │
  └─── (Repeat for each chunk) ───┘

Issues:
  ❌ High latency (~50-200ms per request)
  ❌ Re-compute attention every time
  ❌ No state preservation
  ❌ Client-side VAD (limited quality)


╔════════════════════════════════════════════════════════════════════════╗
║                 NEW APPROACH (WebSocket + VAD)                         ║
╚════════════════════════════════════════════════════════════════════════╝

Client                          Server
  │                               │
  ├──── WebSocket handshake ─────>│
  │<───── Connection accepted ────┤
  │                               │
  ├──── Config (JSON) ───────────>│
  │<──── Session created ─────────┤
  │                               │
  ├──── Audio stream ────────────>│ [Persistent connection]
  │    (continuous binary)        │
  │                               ├─── VAD: Speech?
  │                               │     └─> YES: Buffer
  │                               │
  │<──── Partial transcript ──────┤     (only during speech)
  │    (pushed proactively)       │
  │                               │
  ├──── Audio stream ────────────>│
  │    (continuous)               ├─── ASR: Process new audio only
  │                               │     └─> Reuse KV cache
  │                               │
  │<──── Partial transcript ──────┤
  │                               │
  ├──── Audio stream ────────────>│
  │                               ├─── VAD: Silence detected
  │                               ├─── Trigger endpointing
  │                               │
  │<──── Final transcript ────────┤
  │    (is_speech_final: true)   │
  │                               │
  │                               ├─── Reset for next utterance
  │                               │
  └──── (Seamless continuation) ──┘

Benefits:
  ✅ Low latency (~5-20ms per chunk)
  ✅ Only compute attention for new audio
  ✅ State preserved across chunks
  ✅ Server-side VAD (high quality)
  ✅ Automatic endpointing
```

## Data Flow Timeline

```
Time │ Client                │ VAD         │ ASR              │ Response to Client
─────┼───────────────────────┼─────────────┼──────────────────┼────────────────────
0.0s │ [Start recording]     │             │                  │
     │                       │             │                  │
0.1s │ Send 100ms audio ────>│ Check: 0.2  │                  │ (Below threshold)
     │                       │ (silence)   │                  │
     │                       │             │                  │
0.2s │ Send 100ms audio ────>│ Check: 0.8  │                  │ (Speech starting)
     │                       │ (SPEECH!)   │                  │
     │                       │             │                  │
0.3s │ Send 100ms audio ────>│ Check: 0.9  │ Accumulating...  │
     │                       │ (SPEECH!)   │                  │
     │                       │             │                  │
0.4s │ Send 100ms audio ────>│ Check: 0.9  │ Send to ASR ────>│ <- Partial: "Hello"
     │                       │ (SPEECH!)   │ (min duration    │
     │                       │             │  reached)        │
     │                       │             │                  │
0.5s │ Send 100ms audio ────>│ Check: 0.9  │ Process new ────>│ <- Partial: "Hello w"
     │                       │ (SPEECH!)   │ chunk (KV reuse) │
     │                       │             │                  │
0.8s │ Send 100ms audio ────>│ Check: 0.3  │                  │
     │                       │ (silence)   │ [Count silence]  │
     │                       │             │                  │
0.9s │ Send 100ms audio ────>│ Check: 0.2  │                  │
     │                       │ (silence)   │ [800ms silence]  │
     │                       │             │ ENDPOINT! ──────>│ <- Final: 
     │                       │             │                  │    "Hello world"
     │                       │             │                  │    is_speech_final: true
     │                       │             │                  │
1.0s │ [Continue recording]  │ [Reset]     │ [Reset for next] │
     │                       │             │                  │
1.1s │ Send 100ms audio ────>│ Check: 0.9  │                  │ (New utterance)
     │                       │ (SPEECH!)   │                  │
     └───────────────────────┴─────────────┴──────────────────┴────────────────────
```

## Memory and State Management

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Per-Session State                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Session ID: abc123                                                  │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │ Audio Buffer (100ms chunks)                                 │    │
│  │ ┌──┬──┬──┬──┬──┬──┬──┬──┬──┬──┐                             │    │
│  │ │  │  │  │  │  │  │  │  │  │  │                             │    │
│  │ └──┴──┴──┴──┴──┴──┴──┴──┴──┴──┘                             │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │ ASR State (Qwen3ASRModel.init_streaming_state)             │    │
│  │                                                              │    │
│  │  • audio_accum: Full audio history (no padding)            │    │
│  │  • prompt_raw: Base prompt                                  │    │
│  │  • context: User-provided context                           │    │
│  │  • language: Detected/forced language                       │    │
│  │  • text: Current transcript                                 │    │
│  │  • _raw_decoded: Internal state for rollback                │    │
│  │  • chunk_id: Current chunk counter                          │    │
│  │                                                              │    │
│  │  [vLLM maintains KV cache internally]                       │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │ VAD State                                                    │    │
│  │                                                              │    │
│  │  • is_speaking: Boolean                                     │    │
│  │  • silence_duration: Float (seconds)                        │    │
│  │  • speech_duration: Float (seconds)                         │    │
│  │  • last_activity: Timestamp                                 │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘

Multiple sessions managed concurrently:
┌──────────┬──────────┬──────────┬─────┬──────────┐
│Session 1 │Session 2 │Session 3 │ ... │Session N │
│ (Active) │ (Active) │ (Idle)   │     │ (Active) │
└──────────┴──────────┴──────────┴─────┴──────────┘
     │           │           │              │
     └───────────┴───────────┴──────────────┘
                  │
          Session Manager
     • Creates/deletes sessions
     • Cleanup stale (TTL)
     • Garbage collection
```

## Latency Breakdown

```
┌────────────────────────────────────────────────────────────────────┐
│            End-to-End Latency Components                           │
└────────────────────────────────────────────────────────────────────┘

Speech starts ──────┐
                    │
                    ▼
        ┌────────────────────┐
        │ Audio capture      │  ~20ms   [Client buffering]
        └─────────┬──────────┘
                  │
                  ▼
        ┌────────────────────┐
        │ Network transmission│  ~5-10ms [LAN/local]
        └─────────┬──────────┘
                  │
                  ▼
        ┌────────────────────┐
        │ VAD processing     │  ~8ms    [Per 100ms chunk]
        └─────────┬──────────┘
                  │
                  ▼
        ┌────────────────────┐
        │ Wait for min       │  ~300ms  [Configurable]
        │ speech duration    │          [min_speech_duration]
        └─────────┬──────────┘
                  │
                  ▼
        ┌────────────────────┐
        │ ASR processing     │  ~100-   [Per chunk_size_sec]
        │ (first chunk)      │  200ms   [GPU dependent]
        └─────────┬──────────┘
                  │
                  ▼
        ┌────────────────────┐
        │ Network transmission│  ~5-10ms [Response back]
        └─────────┬──────────┘
                  │
                  ▼
        ┌────────────────────┐
        │ UI update          │  ~1-5ms  [Client rendering]
        └─────────┬──────────┘
                  │
                  ▼
First partial transcript appears

═══════════════════════════════════════════════════════════════════

Total: ~450-600ms (speech start → first partial)

After first partial, subsequent updates are much faster:
  ~100-200ms per chunk (only ASR latency + network)

By comparison:
  Old HTTP approach: ~500-800ms per update (with re-computation overhead)
```
