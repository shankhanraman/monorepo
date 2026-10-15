"""WHISPER_DEVICE=auto picks the GPU the machine has: Apple (mlx) > NVIDIA (cuda) > cpu."""
import sys
import types

import pytest

from app.services import audio


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.delenv("WHISPER_DEVICE", raising=False)
    audio.backend.cache_clear()
    yield
    audio.backend.cache_clear()


def machine(monkeypatch, os_name, arch, mlx, cuda_devices):
    monkeypatch.setattr(audio.sys, "platform", os_name)
    monkeypatch.setattr(audio.platform, "machine", lambda: arch)
    monkeypatch.setattr(audio.importlib.util, "find_spec", lambda name: object() if mlx and name == "mlx_whisper" else None)
    monkeypatch.setitem(sys.modules, "ctranslate2", types.SimpleNamespace(get_cuda_device_count=lambda: cuda_devices))


def test_apple_silicon_with_mlx_uses_the_gpu(monkeypatch):
    machine(monkeypatch, "darwin", "arm64", mlx=True, cuda_devices=0)
    assert audio.backend() == "mlx"


def test_mac_without_mlx_installed_falls_back_to_cpu(monkeypatch):
    machine(monkeypatch, "darwin", "arm64", mlx=False, cuda_devices=0)
    assert audio.backend() == "cpu"


def test_nvidia_gpu_uses_cuda(monkeypatch):
    machine(monkeypatch, "linux", "x86_64", mlx=False, cuda_devices=1)
    assert audio.backend() == "cuda"


def test_no_gpu_uses_cpu(monkeypatch):
    machine(monkeypatch, "linux", "x86_64", mlx=False, cuda_devices=0)
    assert audio.backend() == "cpu"


def test_env_forces_a_backend(monkeypatch):
    machine(monkeypatch, "linux", "x86_64", mlx=False, cuda_devices=1)
    monkeypatch.setenv("WHISPER_DEVICE", "CPU")
    assert audio.backend() == "cpu"


def test_unknown_device_is_rejected(monkeypatch):
    monkeypatch.setenv("WHISPER_DEVICE", "gpu")
    with pytest.raises(ValueError, match="WHISPER_DEVICE"):
        audio.backend()
