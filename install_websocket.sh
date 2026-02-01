#!/bin/bash
# Install WebSocket streaming dependencies for Qwen3-ASR

echo "Installing WebSocket streaming dependencies..."

# Install base dependencies
pip install -U fastapi uvicorn[standard] websockets

# Try to install PyAudio (optional, for client microphone support)
echo ""
echo "Installing PyAudio (optional, for microphone support)..."
if pip install pyaudio; then
    echo "✓ PyAudio installed successfully"
else
    echo "⚠ PyAudio installation failed. This is optional."
    echo "  You can still use file-based streaming."
    echo ""
    echo "  To install PyAudio manually:"
    echo "  - macOS: brew install portaudio && pip install pyaudio"
    echo "  - Ubuntu: sudo apt-get install portaudio19-dev && pip install pyaudio"
    echo "  - Windows: pip install pyaudio (or download wheel from unofficial builds)"
fi

# Try to download Silero VAD (optional, but recommended)
echo ""
echo "Pre-downloading Silero VAD model..."
python3 -c "
import torch
try:
    model, utils = torch.hub.load(
        repo_or_dir='snakers4/silero-vad',
        model='silero_vad',
        force_reload=False,
        onnx=False
    )
    print('✓ Silero VAD downloaded successfully')
except Exception as e:
    print(f'⚠ Failed to download Silero VAD: {e}')
    print('  VAD will be downloaded on first use.')
"

echo ""
echo "Installation complete!"
echo ""
echo "To start the WebSocket server:"
echo "  qwen-asr-serve-websocket --asr-model-path Qwen/Qwen3-ASR-1.7B"
echo ""
echo "For more information, see WEBSOCKET_STREAMING.md"
