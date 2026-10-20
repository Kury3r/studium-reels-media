"""Episode JSON -> finished 1080x1920 MP4 (series «переписки репетитора», style «мятне скло»).

Previews show the Reels/TikTok unsafe zones in red. The rule applies to SUBTITLES ONLY: subtitles must sit fully outside the red areas;
the rest of the picture may use the whole frame.

usage:
  make_reel.py EP.json --design DESIGN --list-voice            # print the line ids and the one-take voice prompt
  make_reel.py EP.json --design DESIGN --split-take take.mp3 --voice-dir DIR   # cut the take into one file per line
  make_reel.py EP.json OUT.png --design DESIGN --preview [--voice-dir DIR]   # 6-frame contact sheet
  make_reel.py EP.json OUT.mp4 --design DESIGN [--voice-dir DIR] [--fps 30]  # final video

--voice-dir holds one audio file per voice line, named <id>.mp3 (or .wav), e.g. intro.mp3, s0.mp3, punch.mp3.
With it, timing follows the real audio and the voice is mixed in; without it, timing is estimated and the reel is silent
except for interface sounds. --style dark uses the old dark Telegram template (no voice support).
Paths in the episode ("photo", "outro.screen") are relative to the design repo, e.g. "screens/14-student-package.png".
"""
import argparse, json, os, pathlib, shutil, subprocess, sys, tempfile, time
import numpy as np
from scipy.io import wavfile

HERE = pathlib.Path(__file__).resolve().parent
ASSETS = HERE.parent / 'assets'
sys.path.insert(0, str(HERE))
import sfx  # noqa: E402

SR = sfx.SR


def find_chrome():
    for c in sorted(pathlib.Path('/opt/pw-browsers').glob('chromium-*/chrome-linux/chrome')):
        return str(c)
    return None


def audio_duration(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def decode(path):
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-ac', '1', '-ar', str(SR), '-f', 's16le', '-'], capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.int16).astype(np.float64) / 32768


SEP = ' [long pause] '


def split_take(take, ids, out_dir):
    """Cut one voice take (all lines joined with [long pause]) into <id>.wav files at the len(ids)-1 longest silences."""
    r = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(take), '-af', 'silencedetect=n=-40dB:d=0.2', '-f', 'null', '-'],
                       capture_output=True, text=True)
    import re
    starts = [float(x) for x in re.findall(r'silence_start: ([0-9.]+)', r.stderr)]
    ends = [float(x) for x in re.findall(r'silence_end: ([0-9.]+)', r.stderr)]
    sil = list(zip(starts, ends))
    total = audio_duration(take)
    need = len(ids) - 1
    inner = [(a, b) for a, b in sil if a > 0.05 and b < total - 0.05]
    gaps = sorted(sorted(inner, key=lambda g: g[1] - g[0], reverse=True)[:need])
    if len(gaps) < need or (need and min(b - a for a, b in gaps) < 0.6):
        sys.exit(f'SPLIT FAILED: found {len(gaps)} long pauses, need {need}. Generate the lines one by one instead.')
    lead = sil[0][1] if sil and sil[0][0] <= 0.05 else 0.0
    tail = sil[-1][0] if sil and sil[-1][1] >= total - 0.05 else total
    bounds = [max(0.0, lead - 0.04)] + [x for a, b in gaps for x in (a + 0.08, b - 0.04)] + [min(total, tail + 0.08)]
    out = pathlib.Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    for i, sid in enumerate(ids):
        a, b = bounds[2 * i], bounds[2 * i + 1]
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(take), '-ss', f'{a:.3f}', '-to', f'{b:.3f}', '-ac', '1', '-ar', '48000',
                        str(out / f'{sid}.wav')], check=True)
    return [(sid, round(bounds[2 * i + 1] - bounds[2 * i], 2)) for i, sid in enumerate(ids)]


def voice_files(voice_dir):
    out = {}
    if voice_dir and pathlib.Path(voice_dir).is_dir():
        for f in pathlib.Path(voice_dir).iterdir():
            if f.suffix.lower() in ('.mp3', '.wav', '.m4a', '.ogg'):
                out[f.stem] = f
    return out


SAFE_OVERLAY = '''<div style="position:absolute;inset:0;pointer-events:none;z-index:9999">
<div style="position:absolute;left:0;right:0;top:0;height:124px;background:rgba(255,0,0,.22)"></div>
<div style="position:absolute;left:0;right:0;top:767px;bottom:0;background:rgba(255,0,0,.22)"></div>
<div style="position:absolute;left:0;width:35px;top:124px;height:643px;background:rgba(255,0,0,.22)"></div>
<div style="position:absolute;left:514px;right:0;top:124px;height:306px;background:rgba(255,0,0,.22)"></div>
<div style="position:absolute;left:444px;right:0;top:430px;height:337px;background:rgba(255,0,0,.22)"></div>
</div>'''


FORMATS = ('chat', 'pov', 'before_after', 'tips', 'demo', 'quiz')


def build_html(ep, design, out_dir, style, voice, overlay=False):
    ep = json.loads(json.dumps(ep))
    def fix(p):
        if not p or not isinstance(p, str) or p.startswith(('emoji:', 'file:', 'http', 'data:')):
            return p
        return (pathlib.Path(design) / p).resolve().as_uri()
    def walk(o):  # every "screen"/"photo" value anywhere in the episode is a design-repo path
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ('screen', 'photo') and isinstance(v, str):
                    o[k] = fix(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(ep)
    if voice:
        ep['voice'] = voice
    if style == 'dark':
        html = (ASSETS / 'chat-template.html').read_text(encoding='utf-8')
    else:
        fmt = ep.get('format', 'chat')
        tpl = ASSETS / 'formats' / f'{fmt}.html'
        if not tpl.exists():
            sys.exit(f'unknown format "{fmt}": no template {tpl}')
        html = tpl.read_text(encoding='utf-8')
        html = html.replace('/*@CORE_CSS*/', (ASSETS / 'core.css').read_text(encoding='utf-8'))
        html = html.replace('<!--@CORE_JS-->', '<script>\n' + (ASSETS / 'core.js').read_text(encoding='utf-8') + '\n</script>')
        theme = ep.get('theme', 'glass')  # visual theme: "glass" (default, мʼятне скло) or a file in assets/themes/
        if theme != 'glass':
            tf = ASSETS / 'themes' / f'{theme}.css'
            if not tf.exists():
                sys.exit(f'unknown theme "{theme}": no file {tf}')
            html = html.replace('</head>', '<style>\n' + tf.read_text(encoding='utf-8') + '\n</style></head>', 1)
    qr_path = pathlib.Path(design) / 'brand' / 'qr-crm-studiumbot.svg'
    qr = qr_path.read_text(encoding='utf-8') if qr_path.exists() else ''
    qr = qr.replace('#f3f0e4', '#ffffff').replace('#F3F0E4', '#ffffff').replace('#0f4a2e', '#0d4d48').replace('#0F4A2E', '#0d4d48')
    html = html.replace('{{QR}}', qr)
    html = html.replace('<body>', '<body><div id="qrsrc" hidden>' + qr + '</div>', 1)
    html = html.replace('<script>\n', '<script>window.EP = ' + json.dumps(ep, ensure_ascii=False) + ';</script>\n<script>\n', 1)
    if overlay and style == 'glass':
        html = html.replace('</body>', SAFE_OVERLAY + '</body>')
    p = pathlib.Path(out_dir) / 'episode.html'
    p.write_text(html, encoding='utf-8')
    return p


def _render_frames(args):
    """Worker: render every frame i with i % n == k to JPEG files (runs in its own process)."""
    page_uri, k, n, total, fps, outdir, vw, vh, scale = args
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        kw = {'args': ['--hide-scrollbars', '--force-color-profile=srgb', '--allow-file-access-from-files']}
        ch = find_chrome()
        if ch: kw['executable_path'] = ch
        b = p.chromium.launch(**kw)
        pg = b.new_page(viewport={'width': vw, 'height': vh}, device_scale_factor=scale)
        pg.goto(page_uri, wait_until='load'); pg.evaluate('document.fonts.ready'); pg.wait_for_timeout(300)
        for i in range(k, total, n):
            pg.evaluate('t => window.render(t)', i / fps)
            pg.screenshot(path=f'{outdir}/f{i:05d}.jpg', type='jpeg', quality=92)
        b.close()
    return k


def mix(cues, segments, files, duration, path):
    n = int((duration + 0.5) * SR)
    fx_path = path + '.fx.wav'
    sfx.synth(cues, duration, fx_path)
    _, fx = wavfile.read(fx_path)
    fx = fx[:, 0].astype(np.float64) / 32768
    mixbuf = np.zeros(n)
    has_voice = False
    for s in segments:
        f = files.get(s['id'])
        if not f:
            continue
        v = decode(f)
        i = int(s['at'] * SR)
        mixbuf[i:i + len(v)] += v[: max(0, n - i)]
        has_voice = True
    fx_gain = 10 ** (-14 / 20) if has_voice else 1.0  # interface sounds sit well under the voice
    m = min(len(fx), n)
    mixbuf[:m] += fx[:m] * fx_gain
    peak = np.max(np.abs(mixbuf)) or 1
    mixbuf *= min(1.0, 0.9 / peak)
    wavfile.write(path, SR, (np.stack([mixbuf, mixbuf], axis=1) * 32767).astype(np.int16))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('episode'); ap.add_argument('out', nargs='?')
    ap.add_argument('--design', required=True)
    ap.add_argument('--fps', type=int, default=30)
    ap.add_argument('--preview', action='store_true')
    ap.add_argument('--list-voice', action='store_true')
    ap.add_argument('--voice-dir')
    ap.add_argument('--split-take', help='one mp3 with every voice line joined by [long pause]; cut into --voice-dir')
    ap.add_argument('--style', choices=['glass', 'dark'], default='glass')
    ap.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2)))
    a = ap.parse_args()
    ep = json.loads(pathlib.Path(a.episode).read_text(encoding='utf-8'))
    files = voice_files(a.voice_dir)
    voice = {k: round(audio_duration(f), 3) for k, f in files.items()}
    scale = 2 if a.style == 'glass' else 1
    vw, vh = (540, 960) if a.style == 'glass' else (1080, 1920)
    from playwright.sync_api import sync_playwright
    work = pathlib.Path(tempfile.mkdtemp(prefix='reel-'))
    page_path = build_html(ep, a.design, work, a.style, voice, overlay=a.preview)
    errors = []
    with sync_playwright() as p:
        kw = {'args': ['--hide-scrollbars', '--force-color-profile=srgb', '--allow-file-access-from-files']}
        ch = find_chrome()
        if ch: kw['executable_path'] = ch
        b = p.chromium.launch(**kw)
        pg = b.new_page(viewport={'width': vw, 'height': vh}, device_scale_factor=scale)
        pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.goto(page_path.as_uri(), wait_until='load')
        pg.evaluate('document.fonts.ready')
        pg.wait_for_timeout(300)
        if errors:
            sys.exit('PAGE ERROR: ' + '; '.join(errors))
        dur = pg.evaluate('window.DURATION')
        cues = pg.evaluate('window.SFX')
        segments = pg.evaluate('window.SEGMENTS || []')
        if a.list_voice or a.split_take:
            empty = [s['id'] for s in segments if not s['sub']]
            if empty:
                sys.exit('ERROR: voice lines without words (only tags) are not allowed: ' + ', '.join(empty))
            b.close()
            if a.split_take:
                if not a.voice_dir:
                    sys.exit('--split-take needs --voice-dir')
                for sid, d in split_take(a.split_take, [s['id'] for s in segments], a.voice_dir):
                    print(f'{sid}: {d}s')
                return
            print('LINES: ' + ', '.join(s['id'] for s in segments))
            print('TAKE: ' + SEP.join(s['text'] for s in segments))
            return
        missing = [s['id'] for s in segments if a.voice_dir and s['id'] not in files]
        if missing:
            print('WARNING: no audio for', ', '.join(missing), file=sys.stderr)
        if a.preview:
            from PIL import Image
            ts = [dur * k for k in (0.05, 0.25, 0.45, 0.62, 0.8, 0.96)]
            frames = []
            for t in ts:
                pg.evaluate('t => window.render(t)', t)
                f = work / f'f{t:.2f}.png'; pg.screenshot(path=str(f))
                frames.append(Image.open(f).resize((270, 480)))
            sheet = Image.new('RGB', (270 * 6 + 40, 480), 'white')
            for i, im in enumerate(frames):
                sheet.paste(im, (i * 278, 0))
            sheet.save(a.out); b.close()
            print(f'preview: {a.out} (duration {dur:.1f}s)'); return
        nfr = int(dur * a.fps + 0.999)
        b.close()
    import multiprocessing as mp
    frames_dir = work / 'frames'; frames_dir.mkdir()
    n = max(1, min(a.workers, nfr))
    t0 = time.time()
    with mp.get_context('spawn').Pool(n) as pool:
        pool.map(_render_frames, [(page_path.as_uri(), k, n, nfr, a.fps, str(frames_dir), vw, vh, scale) for k in range(n)])
    silent = work / 'video.mp4'
    r = subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(a.fps), '-i', str(frames_dir / 'f%05d.jpg'),
                        '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', str(silent)])
    if r.returncode != 0:
        sys.exit('ffmpeg failed')
    wav = str(work / 'mix.wav')
    mix(cues, segments, files, dur, wav)
    r = subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(silent), '-i', wav, '-map', '0:v', '-map', '1:a',
                        '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11', '-ar', '48000',
                        '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', a.out])
    if r.returncode != 0:
        sys.exit('mux failed')
    shutil.rmtree(work, ignore_errors=True)
    print(f'done: {a.out}  {dur:.1f}s  {nfr} frames  render {time.time() - t0:.0f}s  voice lines {len([s for s in segments if s["id"] in files])}/{len(segments)}')


if __name__ == '__main__':
    main()
