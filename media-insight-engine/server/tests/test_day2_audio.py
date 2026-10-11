"""Speech-to-text plumbing: faster-whisper must be able to decode audio with the installed PyAV.

Regression: PyAV 19 dropped av.open(metadata_errors=...), which faster-whisper 1.2.1 passes, so every
podcast failed with "open() got an unexpected keyword argument 'metadata_errors'".
"""
import math
import struct
import wave

import pytest

fw_audio = pytest.importorskip("faster_whisper.audio")


def test_faster_whisper_can_decode_audio(tmp_path):
    path = tmp_path / "tone.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 10))) for i in range(16000)))
    samples = fw_audio.decode_audio(str(path))
    assert len(samples) == 16000          # 1 s at 16 kHz, resampled and decoded through PyAV
