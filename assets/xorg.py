"""Xorg capture helpers; selection uses root coordinates shared by maim and FFmpeg."""
import os
import re
import subprocess


def call(args):
    return subprocess.run(args, check=True, capture_output=True, text=True,
                          env={**os.environ, 'LC_ALL': 'C'}).stdout.strip()


def parse_geometry(text):
    match = re.fullmatch(r'(-?\d+),(-?\d+) (\d+)x(\d+)', text)
    if not match:
        raise RuntimeError('Invalid capture rectangle')
    x, y, width, height = map(int, match.groups())
    if width <= 0 or height <= 0:
        raise RuntimeError('Capture rectangle has no area')
    return x, y, width, height


def geometry(rect):
    x, y, width, height = rect
    return f'{x},{y} {width}x{height}'


def desktop_rect():
    text = call(['xwininfo', '-root'])
    width = re.search(r'^\s*Width:\s*(\d+)', text, re.M)
    height = re.search(r'^\s*Height:\s*(\d+)', text, re.M)
    if not width or not height:
        raise RuntimeError('Cannot read the Xorg desktop dimensions')
    return 0, 0, int(width[1]), int(height[1])


def clip(rect, desktop):
    x, y, w, h = rect
    dx, dy, dw, dh = desktop
    left, top = max(x, dx), max(y, dy)
    right, bottom = min(x + w, dx + dw), min(y + h, dy + dh)
    if right <= left or bottom <= top:
        raise RuntimeError('The selected window or region is outside the desktop')
    return left, top, right - left, bottom - top


def fields(text):
    return dict(line.split('=', 1) for line in text.splitlines() if '=' in line)


def active_rect():
    window = call(['xdotool', 'getactivewindow'])
    if not window.isdecimal() or int(window) == 0:
        raise RuntimeError('No active Xorg window')
    info = fields(call(['xdotool', 'getwindowgeometry', '--shell', window]))
    try:
        return tuple(int(info[name]) for name in ('X', 'Y', 'WIDTH', 'HEIGHT'))
    except (KeyError, ValueError) as error:
        raise RuntimeError('Cannot read active window geometry') from error


def monitors(text=None):
    if text is None:
        text = call(['xrandr', '--listactivemonitors'])
    rectangles = []
    for line in text.splitlines():
        match = re.search(r'(\d+)/\d+x(\d+)/\d+([+-]\d+)([+-]\d+)', line)
        if match:
            w, h, x, y = map(int, match.groups())
            rectangles.append((x, y, w, h))
    if not rectangles:
        raise RuntimeError('No active Xorg monitors found')
    return rectangles


def current_monitor():
    rectangles = monitors()
    try:
        x, y, w, h = active_rect()
        point = (x + w // 2, y + h // 2)
    except (RuntimeError, subprocess.CalledProcessError):
        info = fields(call(['xdotool', 'getmouselocation', '--shell']))
        point = (int(info['X']), int(info['Y']))
    return next((r for r in rectangles if r[0] <= point[0] < r[0]+r[2]
                 and r[1] <= point[1] < r[1]+r[3]), rectangles[0])


def select_rect(target, wait_child, cancelled):
    if target in ('area', 'window'):
        code, output, error = wait_child(['slop', '--noopengl', '--tolerance',
                                        '0' if target == 'area' else '9999999',
                                        '--format', '%x,%y %wx%h'])
        if code or not output:
            if not error.strip() or re.search(r'cancel|abort', error, re.I):
                raise cancelled()
            raise RuntimeError('Xorg selection failed: ' + error.strip())
        rect = parse_geometry(output)
    elif target == 'active':
        rect = active_rect()
    elif target == 'output':
        rect = current_monitor()
    elif target == 'screen':
        rect = desktop_rect()
    else:
        raise RuntimeError('Unknown capture target')
    return clip(rect, desktop_rect())


def screenshot_command(rect):
    x, y, w, h = rect
    return ['maim', '--hidecursor', '--format', 'png', '--geometry', f'{w}x{h}{x:+d}{y:+d}']


def recording_command(rect, path, audio_device=None):
    x, y, w, h = rect
    display = os.environ.get('DISPLAY')
    if not display:
        raise RuntimeError('Xorg capture requires DISPLAY')
    command = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'warning',
               '-f', 'x11grab', '-framerate', '30', '-video_size', f'{w}x{h}',
               '-grab_x', str(x), '-grab_y', str(y), '-i', display]
    if audio_device:
        command += ['-thread_queue_size', '512', '-f', 'pulse', '-i', audio_device]
    command += ['-map', '0:v:0']
    if audio_device:
        command += ['-map', '1:a:0', '-c:a', 'aac']
    command += ['-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p',
                '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-movflags', '+faststart', str(path)]
    return command
