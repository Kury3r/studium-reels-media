"""Synthesize interface sound effects for a reel from a cue list -> 48 kHz stereo WAV.
Cues come from the page as window.SFX: [[time, kind, arg?], ...].
Kinds: buzz, whoosh, msg_in, msg_out, key, del, hit, ding, success.
"""
import numpy as np
from scipy.io import wavfile
from scipy.signal import lfilter

SR = 48000
rng = np.random.default_rng(7)


def _t(d):
    return np.arange(int(d * SR)) / SR


def _env(d, a=0.003, decay=0.08):
    t = _t(d)
    e = np.exp(-t / decay)
    na = max(1, int(a * SR))
    e[:na] *= np.linspace(0, 1, na)
    return e


def _sin(d, f):
    return np.sin(2 * np.pi * f * _t(d))


def _lowpass_noise(d, k):
    n = rng.standard_normal(int(d * SR))
    out = lfilter([k], [1, -(1 - k)], n)  # one-pole lowpass, k in (0,1)
    return out / (np.max(np.abs(out)) + 1e-9)


def buzz(_):
    d = 0.32
    s = np.sign(_sin(d, 150)) * 0.5 + _sin(d, 300) * 0.3
    return s * np.minimum(1, _t(d) / 0.01) * np.exp(-_t(d) / 0.25) * 0.35


def whoosh(_):
    d = 0.55
    x = np.linspace(0, 1, int(d * SR))
    return _lowpass_noise(d, 0.08) * np.sin(np.pi * x) ** 2 * 0.28


def msg_in(_):  # soft two-tone pop
    d = 0.18
    f = 600 + 700 * np.exp(-_t(d) * 30)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * _env(d, 0.002, 0.05) * 0.5


def msg_out(_):  # Telegram-ish swoosh-tick
    d = 0.16
    f = 1400 - 600 * _t(d) / d
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * _env(d, 0.002, 0.04) * 0.35


def key(_):
    d = 0.035
    return (rng.standard_normal(int(d * SR)) * 0.5 + _sin(d, 2600) * 0.5) * _env(d, 0.0005, 0.006) * 0.35


def delete(arg):
    d = max(0.12, float(arg or 0.2))
    n = int(d * SR)
    s = np.zeros(n)
    for k in range(int(d / 0.045)):
        c = key(None)
        i = int(k * 0.045 * SR)
        s[i:i + len(c)] += c[: n - i] * 0.8
    return s


def hit(_):
    d = 0.9
    body = _sin(d, 55) * np.exp(-_t(d) / 0.25)
    click = rng.standard_normal(int(d * SR)) * np.exp(-_t(d) / 0.015)
    return (body * 0.7 + click * 0.3) * 0.6


def ding(_):
    d = 1.4
    return (_sin(d, 1318.5) + 0.5 * _sin(d, 1975.5)) * _env(d, 0.003, 0.35) * 0.22


def success(_):
    d = 1.8
    s = np.zeros(int(d * SR))
    for i, f in enumerate([523.25, 659.25, 783.99, 1046.5]):
        tone = _sin(d - i * 0.07, f) * _env(d - i * 0.07, 0.004, 0.45) / (1 + i * 0.3)
        o = int(i * 0.07 * SR)
        s[o:o + len(tone)] += tone
    return s * 0.2


KINDS = {'buzz': buzz, 'whoosh': whoosh, 'msg_in': msg_in, 'msg_out': msg_out, 'key': key,
         'del': delete, 'hit': hit, 'ding': ding, 'success': success}


def synth(cues, duration, path):
    n = int((duration + 0.5) * SR)
    mix = np.zeros(n)
    for cue in cues:
        at, kind = float(cue[0]), cue[1]
        arg = cue[2] if len(cue) > 2 else None
        fn = KINDS.get(kind)
        if fn is None:
            continue
        s = fn(arg)
        i = int(at * SR)
        if i >= n:
            continue
        mix[i:i + len(s)] += s[: n - i]
    peak = np.max(np.abs(mix)) or 1
    mix = mix * min(1, 0.85 / peak)
    st = np.stack([mix, mix], axis=1)
    wavfile.write(path, SR, (st * 32767).astype(np.int16))
