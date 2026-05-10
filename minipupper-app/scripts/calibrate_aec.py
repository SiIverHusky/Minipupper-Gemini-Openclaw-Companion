#!/usr/bin/env python3
"""Calibrate in-app AEC settings for barge-in on a specific device.

This script plays a probe signal on the speaker while recording the mic,
then estimates echo delay, gain, and frame-level similarity statistics.

Output: recommended `barge_in` settings for config/config.yaml.
"""

import argparse
import os
from pathlib import Path

import numpy as np
import sounddevice as sd
import yaml
from scipy.signal import correlate, correlation_lags


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_yaml(path: Path, content: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(content, f, sort_keys=False)


def _generate_probe(sample_rate: int, duration_s: float, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(sample_rate * duration_s)
    t = np.linspace(0.0, duration_s, n, endpoint=False, dtype=np.float32)

    f0, f1 = 250.0, 3800.0
    k = (f1 - f0) / max(duration_s, 1e-6)
    sweep = np.sin(2.0 * np.pi * (f0 * t + 0.5 * k * t * t)).astype(np.float32)
    noise = rng.normal(0.0, 1.0, n).astype(np.float32)

    signal = 0.7 * sweep + 0.3 * noise

    fade_len = max(1, int(0.05 * sample_rate))
    fade = np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
    signal[:fade_len] *= fade
    signal[-fade_len:] *= fade[::-1]

    peak = float(np.max(np.abs(signal))) + 1e-9
    signal = 0.35 * (signal / peak)
    return signal.astype(np.float32)


def _rms(x: np.ndarray) -> float:
    if x.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(x * x)))


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 1e-9:
        return 0.0
    return float(np.dot(a, b) / denom)


def _estimate_delay_samples(
    mic: np.ndarray,
    playback: np.ndarray,
    max_delay_samples: int,
) -> int:
    corr = correlate(mic, playback, mode="full", method="fft")
    lags = correlation_lags(mic.size, playback.size, mode="full")

    mask = (lags >= 0) & (lags <= max_delay_samples)
    if not np.any(mask):
        return 0

    idx = int(np.argmax(np.abs(corr[mask])))
    return int(lags[mask][idx])


def _align_with_delay(
    mic: np.ndarray,
    playback: np.ndarray,
    delay_samples: int,
) -> tuple[np.ndarray, np.ndarray]:
    if delay_samples <= 0:
        n = min(mic.size, playback.size)
        return mic[:n], playback[:n]

    if delay_samples >= mic.size:
        return np.array([], dtype=np.float32), np.array([], dtype=np.float32)

    mic_aligned = mic[delay_samples:]
    ref_aligned = playback[: mic_aligned.size]
    n = min(mic_aligned.size, ref_aligned.size)
    return mic_aligned[:n], ref_aligned[:n]


def _estimate_gain(mic: np.ndarray, ref: np.ndarray) -> float:
    denom = float(np.dot(ref, ref)) + 1e-9
    gain = float(np.dot(mic, ref) / denom)
    return max(0.0, gain)


def _frame_metrics(
    mic: np.ndarray,
    ref: np.ndarray,
    sample_rate: int,
    frame_ms: int,
) -> tuple[np.ndarray, np.ndarray]:
    frame_len = int(sample_rate * frame_ms / 1000)
    if frame_len <= 0:
        return np.array([], dtype=np.float32), np.array([], dtype=np.float32)

    sims = []
    ratios = []

    for i in range(0, min(mic.size, ref.size) - frame_len + 1, frame_len):
        m = mic[i : i + frame_len]
        r = ref[i : i + frame_len]

        sims.append(_cosine(m, r))

        rr = _rms(r)
        mr = _rms(m)
        if rr <= 1e-9:
            ratios.append(0.0)
        else:
            ratios.append(float(mr / rr))

    return np.array(sims, dtype=np.float32), np.array(ratios, dtype=np.float32)


def _recommend(
    delay_ms: float,
    gain: float,
    sims: np.ndarray,
    ratios: np.ndarray,
    cleaned_rms: np.ndarray,
    frame_ms: int,
) -> dict:
    sim90 = float(np.percentile(sims, 90)) if sims.size else 0.80
    ratio80 = float(np.percentile(ratios, 80)) if ratios.size else 0.45
    ratio95 = float(np.percentile(ratios, 95)) if ratios.size else 0.9
    cleaned95 = float(np.percentile(cleaned_rms, 95)) if cleaned_rms.size else 250.0

    nearend_min_cleaned = float(np.clip(cleaned95 * 1.35, 120.0, 1200.0))
    nearend_ratio = float(np.clip(ratio95 * 1.08, 1.05, 2.20))
    nearend_frames_required = int(np.clip(np.ceil(120.0 / frame_ms), 3, 7))
    startup_grace_ms = int(np.clip(np.ceil(delay_ms + 180.0), 220, 800))

    return {
        "aec_enabled": True,
        "aec_max_delay_ms": int(np.clip(np.ceil(delay_ms + 60.0), 80, 350)),
        "aec_max_gain": round(float(np.clip(gain * 1.15, 0.8, 1.8)), 3),
        "aec_double_talk_ratio": round(float(np.clip(ratio95 + 0.25, 1.2, 2.2)), 3),
        "echo_suppression_threshold": round(float(np.clip(sim90 + 0.04, 0.70, 0.97)), 3),
        "echo_energy_ratio": round(float(np.clip(ratio80 * 1.1, 0.20, 0.90)), 3),
        "nearend_min_cleaned_rms": round(nearend_min_cleaned, 1),
        "nearend_mic_to_playback_ratio": round(nearend_ratio, 3),
        "nearend_frames_required": nearend_frames_required,
        "startup_grace_ms": startup_grace_ms,
    }


def _frame_rms(x: np.ndarray, sample_rate: int, frame_ms: int) -> np.ndarray:
    frame_len = int(sample_rate * frame_ms / 1000)
    if frame_len <= 0 or x.size < frame_len:
        return np.array([], dtype=np.float32)
    out = []
    for i in range(0, x.size - frame_len + 1, frame_len):
        out.append(_rms(x[i : i + frame_len]))
    return np.array(out, dtype=np.float32)


def _quality_label(gain: float, sims: np.ndarray, erle_db: float) -> tuple[str, str]:
    sim95 = float(np.percentile(sims, 95)) if sims.size else 0.0
    if gain < 0.03 or sim95 < 0.25:
        return (
            "low",
            "Weak playback-to-mic coupling detected; calibration may be unreliable. Increase speaker volume or verify correct input/output devices.",
        )
    if erle_db < 2.0:
        return (
            "medium",
            "Echo path detected but cancellation headroom is limited; values are usable but may need manual tightening.",
        )
    return ("high", "Calibration quality looks good.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate in-app AEC settings")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config YAML")
    parser.add_argument("--duration", type=float, default=4.0, help="Probe playback duration (seconds)")
    parser.add_argument("--sample-rate", type=int, default=int(os.getenv("MIC_SAMPLE_RATE", "16000")))
    parser.add_argument("--channels", type=int, default=int(os.getenv("MIC_CHANNELS", "1")))
    parser.add_argument("--input-device", type=int, default=int(os.getenv("MIC_DEVICE_INDEX", os.getenv("AUDIO_DEVICE_INDEX", "-1"))))
    parser.add_argument("--output-device", type=int, default=int(os.getenv("SPEAKER_DEVICE_INDEX", os.getenv("AUDIO_DEVICE_INDEX", "-1"))))
    parser.add_argument("--max-delay-ms", type=int, default=300, help="Max echo delay search window")
    parser.add_argument("--frame-ms", type=int, default=30, choices=[10, 20, 30], help="Frame size for frame metrics")
    parser.add_argument("--write-config", action="store_true", help="Write recommended values back to config YAML")
    args = parser.parse_args()

    cfg_path = Path(args.config)
    cfg = _load_yaml(cfg_path)

    print("Running AEC calibration...")
    print(f"sample_rate={args.sample_rate} channels={args.channels} input_device={args.input_device} output_device={args.output_device}")

    probe = _generate_probe(args.sample_rate, args.duration)
    probe_2d = probe.reshape(-1, 1)

    device = (
        None if args.input_device < 0 else int(args.input_device),
        None if args.output_device < 0 else int(args.output_device),
    )

    recording = sd.playrec(
        probe_2d,
        samplerate=args.sample_rate,
        channels=max(1, args.channels),
        dtype="float32",
        device=device,
        blocking=True,
    )

    if recording.ndim == 2:
        mic = recording[:, 0]
    else:
        mic = recording

    playback = probe.astype(np.float32)
    mic = mic.astype(np.float32)

    max_delay_samples = int(args.sample_rate * args.max_delay_ms / 1000)
    delay_samples = _estimate_delay_samples(mic, playback, max_delay_samples)
    delay_ms = (delay_samples * 1000.0) / args.sample_rate

    mic_aligned, ref_aligned = _align_with_delay(mic, playback, delay_samples)
    if mic_aligned.size == 0 or ref_aligned.size == 0:
        raise RuntimeError("Failed to align mic and playback for calibration")

    gain = _estimate_gain(mic_aligned, ref_aligned)
    residual = mic_aligned - (gain * ref_aligned)

    erle_db = 10.0 * np.log10((np.var(mic_aligned) + 1e-9) / (np.var(residual) + 1e-9))

    sims, ratios = _frame_metrics(mic_aligned, ref_aligned, args.sample_rate, args.frame_ms)
    cleaned_rms = _frame_rms(residual, args.sample_rate, args.frame_ms)
    rec = _recommend(delay_ms, gain, sims, ratios, cleaned_rms, args.frame_ms)
    quality, quality_msg = _quality_label(gain, sims, erle_db)

    print("\nCalibration results:")
    print(f"estimated_delay_ms: {delay_ms:.1f}")
    print(f"estimated_gain: {gain:.3f}")
    print(f"estimated_erle_db: {erle_db:.2f}")
    print(f"calibration_quality: {quality}")
    print(f"quality_note: {quality_msg}")

    print("\nRecommended barge_in settings:")
    print("barge_in:")
    print(f"  aec_enabled: {str(rec['aec_enabled']).lower()}")
    print(f"  aec_max_delay_ms: {rec['aec_max_delay_ms']}")
    print(f"  aec_max_gain: {rec['aec_max_gain']}")
    print(f"  aec_double_talk_ratio: {rec['aec_double_talk_ratio']}")
    print(f"  echo_suppression_threshold: {rec['echo_suppression_threshold']}")
    print(f"  echo_energy_ratio: {rec['echo_energy_ratio']}")
    print(f"  nearend_min_cleaned_rms: {rec['nearend_min_cleaned_rms']}")
    print(f"  nearend_mic_to_playback_ratio: {rec['nearend_mic_to_playback_ratio']}")
    print(f"  nearend_frames_required: {rec['nearend_frames_required']}")
    print(f"  startup_grace_ms: {rec['startup_grace_ms']}")

    current = (cfg.get("barge_in") or {}) if isinstance(cfg, dict) else {}
    if current:
        print("\nCurrent values:")
        for key in [
            "aec_enabled",
            "aec_max_delay_ms",
            "aec_max_gain",
            "aec_double_talk_ratio",
            "echo_suppression_threshold",
            "echo_energy_ratio",
            "nearend_min_cleaned_rms",
            "nearend_mic_to_playback_ratio",
            "nearend_frames_required",
            "startup_grace_ms",
        ]:
            if key in current:
                print(f"  {key}: {current[key]}")

    if args.write_config:
        if not isinstance(cfg, dict):
            cfg = {}
        cfg.setdefault("barge_in", {})
        cfg["barge_in"].update(rec)
        _write_yaml(cfg_path, cfg)
        print(f"\nWrote recommended settings to {cfg_path}")

    print("\nTip: run this while no one is speaking near the mic for best echo profiling.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
