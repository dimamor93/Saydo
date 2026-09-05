from __future__ import annotations


def has_cuda_gpu() -> bool:
    """Return whether Saydo can access a CUDA-capable GPU through PyTorch."""
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False
