# WebSocket Server Settings Guide: What Each Setting Does

## Quick Reference: Common Scenarios

### 🚀 Fast Finalization (Quick Turn-Taking)
```bash
--vad-threshold 0.5 \
--silence-threshold 0.4 \     # ⚡ Key: Lower = faster finalization
--min-speech-duration 0.1 \
--chunk-size-sec 0.5
```

### 🔇 Filter Background Noise
```bash
--vad-threshold 0.7 \          # 🔑 Key: Higher = more filtering
--silence-threshold 0.8 \
--min-speech-duration 0.3
```

### 🎯 Balanced (Recommended for Most Cases)
```bash
--vad-threshold 0.6 \
--silence-threshold 0.6 \
--min-speech-duration 0.2 \
--chunk-size-sec 0.8
```

---

## Detailed Settings Explanation

### 1. `--vad-threshold` (Speech Detection Sensitivity)

**What it does:** Controls how confident the VAD must be to classify audio as "speech"

**Range:** 0.0 to 1.0 (probability)

**How it works:**
```
Audio → VAD → Speech Probability
         ↓
    Is prob >= threshold?
         ↓
    YES: Mark as speech
    NO:  Mark as silence
```

#### Values & Effects:

| Value | Effect | Use Case | Noise Handling |
|-------|--------|----------|----------------|
| **0.3** | Very sensitive | Clean studio audio | ❌ Picks up all noise |
| **0.5** | Balanced (default) | Normal office | ✅ Good balance |
| **0.6** | Conservative | Noisy office | ✅ Filters some noise |
| **0.7** | Strict | Call center | ✅ Filters most noise |
| **0.8** | Very strict | Very noisy | ⚠️ May miss soft speech |

#### Examples:

**Too Low (0.3):**
```
[PROBLEM] Transcribes background chatter, keyboard clicks, door slams
User: "Hello"
Output: "[Background: someone talking] Hello [keyboard noise]"
```

**Too High (0.8):**
```
[PROBLEM] Misses soft-spoken words, cuts off sentences
User: "Hello, I want to buy a car" (speaking softly)
Output: "want to buy a car" (missed "Hello")
```

**Just Right (0.6):**
```
User: "Hello, I want to buy a car" (with background noise)
Output: "Hello, I want to buy a car" (clean)
```

#### How to Tune:
1. Start with **0.5**
2. If transcribing too much background noise → **increase to 0.6-0.7**
3. If missing words → **decrease to 0.4**
4. Check server logs: `Speech prob: 0.XX` to see what VAD detects

---

### 2. `--silence-threshold` (Finalization Speed)

**What it does:** How many seconds of silence before marking speech as "final"

**Range:** 0.1 to 2.0 seconds (or more)

**How it works:**
```
Speech → Silence detected → Counter starts
           ↓
    Count >= threshold?
           ↓
       Finalize & send
```

#### Values & Effects:

| Value | Effect | Turn-Taking | Use Case |
|-------|--------|-------------|----------|
| **0.3s** | Very fast | ⚡ Instant | Quick Q&A bots |
| **0.4-0.5s** | Fast | ⚡ Quick | Voice bots |
| **0.6-0.8s** | Balanced | ✅ Natural | Phone calls |
| **1.0-1.5s** | Patient | 🐌 Slow | Transcription |
| **2.0s+** | Very patient | 🐌 Very slow | Careful speech |

#### Examples:

**Too Low (0.3s):**
```
[PROBLEM] Cuts off mid-sentence when user pauses to think
User: "I want to buy a... [thinking]... Honda City"
       ↓ (0.3s pause detected)
Output 1: "I want to buy a" [FINAL] ❌
Output 2: "Honda City" [FINAL]
```

**Too High (2.0s):**
```
[PROBLEM] Takes forever to finalize, user waits too long
User: "Hello, I want to buy a car." [done speaking]
       ↓ (waits 2 full seconds)
       ↓ (still waiting...)
       ↓ (finally after 2s)
Output: "Hello, I want to buy a car" [FINAL] 🐌
```

**Just Right (0.6s):**
```
User: "Hello, I want to buy a car." [natural pause]
       ↓ (0.6s pause)
Output: "Hello, I want to buy a car" [FINAL] ✅
```

#### How to Tune:
1. Start with **0.6s**
2. For faster bot responses → **decrease to 0.4-0.5s**
3. If cutting off sentences → **increase to 0.8-1.0s**
4. For people who speak slowly → **increase to 1.0-1.5s**

---

### 3. `--min-speech-duration` (Start Processing Delay)

**What it does:** Minimum speech before starting ASR processing

**Range:** 0.1 to 1.0 seconds

**How it works:**
```
Speech detected → Accumulate X seconds → Start ASR
```

**⚠️ NOTE:** In the latest version, this is largely **ignored** - we now process immediately to avoid missing initial words!

#### Values & Effects:

| Value | Effect | Latency | Use Case |
|-------|--------|---------|----------|
| **0.1s** | Very fast | ⚡ 100ms | Voice bots (recommended) |
| **0.2s** | Fast | ⚡ 200ms | Phone calls |
| **0.3s** | Balanced | 300ms | Default |
| **0.5s** | Slow | 🐌 500ms | Not recommended |

#### Why Lower is Better:
```
Old behavior (0.5s):
User: "Hello" → Wait 0.5s → Start ASR → Miss "Hell", get "lo"

New behavior (0.1s):  
User: "Hello" → Wait 0.1s → Start ASR → Get "Hello" ✅
```

#### Recommendation:
**Use 0.1-0.2s** - The latest code processes immediately anyway, so this mainly acts as a debounce to avoid processing single noise spikes.

---

### 4. `--chunk-size-sec` (ASR Processing Window)

**What it does:** How much audio to accumulate before sending to ASR model

**Range:** 0.5 to 2.0 seconds

**How it works:**
```
Audio stream → Accumulate X seconds → Process with ASR model
```

#### Values & Effects:

| Value | Effect | Latency | Accuracy | GPU Load |
|-------|--------|---------|----------|----------|
| **0.5s** | Small chunks | ⚡ Low | Good | 🔥 High |
| **0.8s** | Medium | ⚡ Medium | Better | 🔥 Medium |
| **1.0s** | Standard | Medium | Best | 🔥 Low |
| **2.0s** | Large | 🐌 High | Best | 🔥 Very low |

#### Trade-offs:

**Small Chunks (0.5s):**
```
Pros:
✅ Lower latency (faster updates)
✅ More responsive

Cons:
❌ Less context for model
❌ More GPU calls (higher load)
❌ May be less accurate
```

**Large Chunks (2.0s):**
```
Pros:
✅ More context (better accuracy)
✅ Fewer GPU calls (efficient)

Cons:
❌ Higher latency
❌ Slower updates
```

#### Recommendation:
- **Voice bots:** 0.8s (good balance)
- **Transcription:** 1.0-1.5s (accuracy focus)
- **High load:** 1.5-2.0s (reduce GPU usage)

---

### 5. `--default-language` (Language Hint)

**What it does:** Tells the model which language to expect

**Options:** "English", "Hindi", "Spanish", etc., or `None` for auto-detect

**How it works:**
```
With language hint: Model focuses on that language → Better accuracy
Without hint: Model auto-detects → May be slower/less accurate
```

#### When to Use:

| Scenario | Setting | Effect |
|----------|---------|--------|
| Pure Hindi | `"Hindi"` | ✅ Best accuracy |
| Pure English | `"English"` | ✅ Best accuracy |
| Code-mixed | `"Hindi"` or `"English"` | ✅ Works well |
| Unknown | `None` | ⚠️ Auto-detect |

#### Example:
```bash
# Hindi-English code-mixing (common in India)
--default-language "Hindi"

# This handles:
"Main ek Swift kharidna chahta hoon" ✅
"I want to buy a car" ✅
"Mujhe automatic transmission chahiye" ✅
```

---

### 6. `--default-prompt` (Context Hint)

**What it does:** Gives the model context about the conversation

**Effect:** Helps model:
- Focus on primary speaker
- Understand domain (cars, medical, tech)
- Handle jargon better
- Filter out irrelevant speakers

#### Examples:

**Generic (No Prompt):**
```
Output: "someone talking in background hello yes I want something car"
```

**With Good Prompt:**
```
Prompt: "Transcribe customer service call for Spinny used cars. Primary speaker only."
Output: "hello yes I want to buy a used car"
```

**Domain-Specific:**
```
Prompt: "Medical consultation. Doctor speaking. Use medical terminology."
Output: "Patient presents with acute myocardial infarction"
vs without: "patient has heart attack problem"
```

---

## Real-World Tuning Scenarios

### Scenario 1: Call Center (Noisy Background)

**Problem:** Too much background chatter being transcribed

**Solution:**
```bash
--vad-threshold 0.7 \           # 🔑 Higher to filter noise
--silence-threshold 0.8 \       # Patient (people speak louder in noisy places)
--min-speech-duration 0.3 \     # Avoid noise spikes
--default-prompt "Call center customer service. Primary speaker only. Ignore background voices."
```

**Why:**
- 0.7 VAD filters out most background noise
- 0.8s silence accounts for raised voices (people pause less when shouting)
- Prompt helps focus on main speaker

---

### Scenario 2: Quick Voice Bot (WhatsApp Bot)

**Problem:** Need instant responses, finalization takes too long

**Solution:**
```bash
--vad-threshold 0.5 \           # Normal detection
--silence-threshold 0.4 \       # 🔑 Fast finalization (400ms)
--min-speech-duration 0.1 \     # Process immediately
--chunk-size-sec 0.6 \          # Small chunks for speed
```

**Why:**
- 0.4s silence = user gets response in ~400ms after speaking
- Small chunks = faster updates
- Lower min_speech ensures no words missed

---

### Scenario 3: Elderly Users (Slow Speech)

**Problem:** Users speak slowly with long pauses, sentences getting cut

**Solution:**
```bash
--vad-threshold 0.4 \           # Sensitive (catch soft speech)
--silence-threshold 1.5 \       # 🔑 Very patient (1.5s)
--min-speech-duration 0.2 \
--chunk-size-sec 1.0
```

**Why:**
- Low VAD catches soft speech
- 1.5s silence allows long pauses between words
- Larger chunks accumulate more context

---

### Scenario 4: Podcast/Interview Transcription

**Problem:** Multiple speakers, need high accuracy

**Solution:**
```bash
--vad-threshold 0.6 \
--silence-threshold 1.0 \       # Patient
--chunk-size-sec 2.0 \          # 🔑 Large chunks for accuracy
--default-prompt "Podcast interview. Multiple speakers. High accuracy transcription."
```

**Why:**
- Large chunks = more context = better accuracy
- Higher silence threshold = complete sentences
- Prompt helps with speaker awareness

---

### Scenario 5: Mobile App (Battery/Data Conscious)

**Problem:** Need to minimize GPU usage, data transfer

**Solution:**
```bash
--vad-threshold 0.6 \           # Filter silence (less data sent)
--chunk-size-sec 1.5 \          # 🔑 Larger chunks (fewer GPU calls)
--silence-threshold 0.8
```

**Why:**
- Larger chunks = fewer processing calls = less GPU
- Higher VAD = less silence sent over network

---

## Quick Tuning Flowchart

```
START: Having issues?
    ↓
┌─────────────────────────────────────┐
│ What's the problem?                 │
└─────────────────────────────────────┘
    ↓
    ├─→ [Background noise in transcripts]
    │   → Increase --vad-threshold (try 0.7)
    │   → Add prompt: "Primary speaker only"
    │
    ├─→ [Sentences cut off mid-way]
    │   → Increase --silence-threshold (try 1.0)
    │
    ├─→ [Missing first words]
    │   → Decrease --min-speech-duration (try 0.1)
    │   → (Should be fixed in latest version)
    │
    ├─→ [Takes too long to finalize]
    │   → Decrease --silence-threshold (try 0.4)
    │   → Decrease --chunk-size-sec (try 0.6)
    │
    ├─→ [Inaccurate transcriptions]
    │   → Set --default-language
    │   → Add domain-specific --default-prompt
    │   → Increase --chunk-size-sec (try 1.5)
    │
    ├─→ [Too slow, high latency]
    │   → Decrease --chunk-size-sec (try 0.6)
    │   → Decrease --silence-threshold (try 0.5)
    │
    └─→ [Missing soft-spoken words]
        → Decrease --vad-threshold (try 0.4)
```

---

## Testing Your Settings

### 1. Start with Defaults
```bash
qwen-asr-serve-websocket \
    --asr-model-path Qwen/Qwen3-ASR-1.7B \
    --generate-self-signed-cert
```

### 2. Check Server Logs
Look for these indicators:
```
Speech started (session abc123)          ← VAD detected speech
VAD: speech_prob=0.85                    ← Check if too high/low
Speech ended (session abc123)            ← Silence threshold reached
Flushing 1600 remaining samples          ← Audio being processed
```

### 3. Test Phrases
Try:
- **Short:** "Hello"
- **Medium:** "I want to buy a car"
- **Long:** "Hello, my name is John and I'm interested in buying a used Honda City automatic transmission"
- **With pause:** "I want to buy... [pause]... a car"

### 4. Tune Based on Results

| Observation | Action |
|-------------|--------|
| Transcribes "hello [noise] want car" | Increase `--vad-threshold` |
| "I want to buy" [FINAL], then "a car" [FINAL] | Increase `--silence-threshold` |
| Takes 2+ seconds after speaking | Decrease `--silence-threshold` |
| Missing "hello" at start | Should be fixed; check `--min-speech-duration` |
| Wrong language | Set `--default-language` |

---

## Recommended Presets

### ⚡ Speed (Voice Bot)
```bash
--vad-threshold 0.5 \
--silence-threshold 0.4 \
--min-speech-duration 0.1 \
--chunk-size-sec 0.6 \
--default-language "Hindi"
```

### 🎯 Balanced (Phone Calls)
```bash
--vad-threshold 0.6 \
--silence-threshold 0.6 \
--min-speech-duration 0.2 \
--chunk-size-sec 0.8 \
--default-language "Hindi"
```

### 📝 Accuracy (Transcription)
```bash
--vad-threshold 0.6 \
--silence-threshold 1.0 \
--min-speech-duration 0.3 \
--chunk-size-sec 1.5 \
--default-language "Hindi"
```

### 🔇 Noisy (Call Center)
```bash
--vad-threshold 0.7 \
--silence-threshold 0.8 \
--min-speech-duration 0.3 \
--chunk-size-sec 0.8 \
--default-language "Hindi"
```

---

## Advanced: Understanding the Processing Pipeline

```
Audio arrives (from WebSocket)
    ↓
Add to buffer
    ↓
VAD check (every 512 samples = 32ms)
    ↓
Speech prob >= vad_threshold?
    ↓ YES                    ↓ NO
Send to ASR                Silence counter++
    ↓                         ↓
Get partial                Silence >= silence_threshold?
transcript                     ↓ YES
    ↓                      Finalize!
Send to client             Send final to client
    ↓                         ↓
Loop...                    Reset for next utterance
```

---

## Summary Table

| To... | Adjust This | Direction |
|-------|-------------|-----------|
| **Finalize faster** | `--silence-threshold` | ⬇️ Lower (0.4-0.5) |
| **Filter more noise** | `--vad-threshold` | ⬆️ Higher (0.7-0.8) |
| **Reduce latency** | `--chunk-size-sec` | ⬇️ Lower (0.6-0.8) |
| **Improve accuracy** | `--chunk-size-sec` | ⬆️ Higher (1.5-2.0) |
| **Avoid cutoffs** | `--silence-threshold` | ⬆️ Higher (1.0-1.5) |
| **Catch soft speech** | `--vad-threshold` | ⬇️ Lower (0.4-0.5) |
| **Domain accuracy** | `--default-prompt` | Add context |
| **Language accuracy** | `--default-language` | Set explicitly |
