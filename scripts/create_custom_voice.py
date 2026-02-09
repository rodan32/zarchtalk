#!/usr/bin/env python3
"""
Create custom Kokoro voices by blending .pt voice embeddings.

Run this on the Kokoro server (192.168.0.20) where the voice .pt files live,
or copy voice files locally. Output custom_apollo_voice.pt can be placed in
Kokoro's voices directory if the server supports loading custom .pt files.

For quick blending without pre-creating files, use KOKORO_VOICE=af_heart+am_fenrir
in .env - Kokoro's API supports inline combination.
"""
import argparse
import sys

try:
    import torch
except ImportError:
    print("Install torch: pip install torch")
    sys.exit(1)


def blend_voices(v1_path: str, v2_path: str, output_path: str, ratio: float = 0.5) -> None:
    """
    Blend two voice embeddings. ratio=0.5 gives 50/50.
    ratio=0.7 gives 70% v1, 30% v2.
    """
    v1 = torch.load(v1_path, weights_only=True)
    v2 = torch.load(v2_path, weights_only=True)
    custom = (v1 * ratio + v2 * (1 - ratio))
    torch.save(custom, output_path)
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Blend Kokoro voice .pt files")
    parser.add_argument("v1", help="First voice .pt path (e.g. af_heart.pt)")
    parser.add_argument("v2", help="Second voice .pt path (e.g. am_fenrir.pt)")
    parser.add_argument("-o", "--output", default="custom_apollo_voice.pt", help="Output path")
    parser.add_argument("-r", "--ratio", type=float, default=0.5, help="Weight for v1 (0-1), default 0.5")
    args = parser.parse_args()

    blend_voices(args.v1, args.v2, args.output, args.ratio)


if __name__ == "__main__":
    main()
