# coding=utf-8
# Copyright 2026 The Alibaba Qwen team.
# SPDX-License-Identifier: Apache-2.0
"""
Python client example for Qwen3-ASR WebSocket streaming server.

This demonstrates how to connect to the WebSocket server and stream audio
from a microphone or audio file.
"""
import argparse
import asyncio
import json
import logging
import sys
import wave
from pathlib import Path

import numpy as np
import soundfile as sf

try:
    import websockets
except ImportError:
    print("Please install websockets: pip install websockets")
    sys.exit(1)

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    print("Warning: PyAudio not available. Microphone streaming disabled.")
    print("Install with: pip install pyaudio")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ASRWebSocketClient:
    """Client for streaming audio to Qwen3-ASR WebSocket server."""
    
    def __init__(
        self,
        server_url: str,
        context: str = "",
        language: str = None,
        unfixed_chunk_num: int = 4,
        unfixed_token_num: int = 5,
        chunk_size_sec: float = 1.0,
    ):
        self.server_url = server_url
        self.context = context
        self.language = language
        self.unfixed_chunk_num = unfixed_chunk_num
        self.unfixed_token_num = unfixed_token_num
        self.chunk_size_sec = chunk_size_sec
        
        self.websocket = None
        self.session_id = None
        self.running = False
    
    async def connect(self):
        """Connect to the WebSocket server."""
        logger.info(f"Connecting to {self.server_url}")
        self.websocket = await websockets.connect(self.server_url)
        
        # Send config
        config = {
            "type": "config",
            "context": self.context,
            "language": self.language,
            "unfixed_chunk_num": self.unfixed_chunk_num,
            "unfixed_token_num": self.unfixed_token_num,
            "chunk_size_sec": self.chunk_size_sec,
        }
        
        await self.websocket.send(json.dumps(config))
        
        # Wait for session_created
        response = await self.websocket.recv()
        data = json.loads(response)
        
        if data.get("type") == "session_created":
            self.session_id = data.get("session_id")
            logger.info(f"Session created: {self.session_id}")
            self.running = True
        else:
            raise Exception(f"Unexpected response: {data}")
    
    async def send_audio(self, audio: np.ndarray):
        """Send audio chunk to server."""
        if not self.running or not self.websocket:
            return
        
        # Ensure float32
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        
        await self.websocket.send(audio.tobytes())
    
    async def receive_results(self):
        """Receive and print transcription results."""
        try:
            while self.running:
                response = await self.websocket.recv()
                data = json.loads(response)
                
                if data.get("type") == "partial":
                    print(f"\r[PARTIAL] {data.get('text', '')}", end='', flush=True)
                
                elif data.get("type") == "final":
                    print(f"\n[FINAL] Language: {data.get('language', 'unknown')}")
                    print(f"        Text: {data.get('text', '')}")
                    print(f"        Speech ended: {data.get('is_speech_final', False)}")
                    print()
                
                elif data.get("type") == "error":
                    logger.error(f"Server error: {data.get('message')}")
                    self.running = False
        
        except websockets.exceptions.ConnectionClosed:
            logger.info("Connection closed")
            self.running = False
    
    async def finalize(self):
        """Finalize the session."""
        if self.websocket:
            await self.websocket.send(json.dumps({"type": "finalize"}))
            
            # Wait for final response
            try:
                response = await asyncio.wait_for(self.websocket.recv(), timeout=5.0)
                data = json.loads(response)
                
                if data.get("type") == "final":
                    print(f"\n[FINAL TRANSCRIPT]")
                    print(f"Language: {data.get('language', 'unknown')}")
                    print(f"Text: {data.get('text', '')}")
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for final response")
    
    async def close(self):
        """Close the connection."""
        self.running = False
        
        if self.websocket:
            await self.websocket.close()
            self.websocket = None


async def stream_from_microphone(client: ASRWebSocketClient, sample_rate: int = 16000, chunk_duration_ms: int = 100):
    """Stream audio from microphone to server."""
    if not PYAUDIO_AVAILABLE:
        logger.error("PyAudio not available. Cannot stream from microphone.")
        return
    
    p = pyaudio.PyAudio()
    
    chunk_size = int(sample_rate * chunk_duration_ms / 1000)
    
    stream = p.open(
        format=pyaudio.paFloat32,
        channels=1,
        rate=sample_rate,
        input=True,
        frames_per_buffer=chunk_size
    )
    
    logger.info("Starting microphone streaming. Press Ctrl+C to stop.")
    
    try:
        while client.running:
            try:
                # Read audio chunk
                data = stream.read(chunk_size, exception_on_overflow=False)
                audio = np.frombuffer(data, dtype=np.float32)
                
                # Send to server
                await client.send_audio(audio)
                
                # Small delay to avoid overwhelming the server
                await asyncio.sleep(0.01)
            
            except Exception as e:
                logger.error(f"Error reading microphone: {e}")
                break
    
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()


async def stream_from_file(client: ASRWebSocketClient, audio_file: str, chunk_duration_ms: int = 100):
    """Stream audio from file to server."""
    logger.info(f"Streaming from file: {audio_file}")
    
    # Load audio file
    try:
        audio, sr = sf.read(audio_file, dtype='float32')
    except Exception as e:
        logger.error(f"Error loading audio file: {e}")
        return
    
    # Convert to mono if stereo
    if len(audio.shape) > 1:
        audio = audio.mean(axis=1)
    
    # Resample to 16kHz if needed
    if sr != 16000:
        logger.info(f"Resampling from {sr}Hz to 16000Hz")
        import scipy.signal
        num_samples = int(len(audio) * 16000 / sr)
        audio = scipy.signal.resample(audio, num_samples)
        sr = 16000
    
    # Stream in chunks
    chunk_size = int(sr * chunk_duration_ms / 1000)
    
    for i in range(0, len(audio), chunk_size):
        if not client.running:
            break
        
        chunk = audio[i:i+chunk_size]
        
        # Pad last chunk if needed
        if len(chunk) < chunk_size:
            chunk = np.pad(chunk, (0, chunk_size - len(chunk)), mode='constant')
        
        await client.send_audio(chunk)
        
        # Simulate real-time streaming
        await asyncio.sleep(chunk_duration_ms / 1000.0)
    
    logger.info("Finished streaming file")


async def main(args):
    """Main entry point."""
    # Build WebSocket URL
    ws_url = f"ws://{args.host}:{args.port}/ws/asr"
    
    # Create client
    client = ASRWebSocketClient(
        server_url=ws_url,
        context=args.context,
        language=args.language,
        unfixed_chunk_num=args.unfixed_chunk_num,
        unfixed_token_num=args.unfixed_token_num,
        chunk_size_sec=args.chunk_size_sec,
    )
    
    try:
        # Connect
        await client.connect()
        
        # Start receiver task
        receiver_task = asyncio.create_task(client.receive_results())
        
        # Stream audio
        if args.audio_file:
            await stream_from_file(client, args.audio_file, chunk_duration_ms=args.chunk_ms)
        else:
            await stream_from_microphone(client, chunk_duration_ms=args.chunk_ms)
        
        # Finalize
        await client.finalize()
        
        # Wait for receiver to finish
        await asyncio.sleep(1.0)
        receiver_task.cancel()
    
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    
    except Exception as e:
        logger.error(f"Error: {e}")
    
    finally:
        await client.close()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Python client for Qwen3-ASR WebSocket streaming server"
    )
    
    # Server connection
    parser.add_argument(
        "--host",
        default="localhost",
        help="Server host"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server port"
    )
    
    # Audio source
    parser.add_argument(
        "--audio-file",
        help="Audio file to stream (if not provided, uses microphone)"
    )
    parser.add_argument(
        "--chunk-ms",
        type=int,
        default=100,
        help="Audio chunk duration in milliseconds"
    )
    
    # ASR configuration
    parser.add_argument(
        "--context",
        default="",
        help="Context string for ASR"
    )
    parser.add_argument(
        "--language",
        help="Force language (e.g., 'English', 'Chinese')"
    )
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


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args))
