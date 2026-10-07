#!/usr/bin/env python3
"""Local capture worker. No shell interpolation; only this worker's child is stopped."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import select
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

import xorg

RUNTIME = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'vicinae-screen-capture'


class Cancelled(Exception):
    pass


def call(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs).stdout.strip()


def notify(title, message):
    subprocess.Popen(['notify-send', '-a', 'Screen Capture', title, message], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def request(command):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(2)
        try:
            client.connect(str(RUNTIME / 'control.sock'))
        except (FileNotFoundError, ConnectionRefusedError):
            return {}
        client.sendall(command.encode())
        return json.loads(client.recv(4096))


def output_directory(kind):
    try:
        parent = Path(call(['xdg-user-dir', kind]))
    except (OSError, subprocess.CalledProcessError):
        parent = Path.home() / ('Pictures' if kind == 'PICTURES' else 'Videos')
    folder = parent / ('Screenshots' if kind == 'PICTURES' else 'Screencasts')
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def filename(kind, suffix):
    return output_directory(kind) / (time.strftime('%Y-%m-%d_%H-%M-%S') + f'_{time.time_ns() % 1000000000:09d}' + suffix)



def session_type(environ=None):
    env = os.environ if environ is None else environ
    kind = env.get('XDG_SESSION_TYPE', '').lower()
    if kind == 'wayland':
        return 'wayland'
    if kind in ('x11', 'xorg'):
        return 'x11'
    if env.get('WAYLAND_DISPLAY'):
        return 'wayland'
    if env.get('DISPLAY'):
        return 'x11'
    raise RuntimeError('No Wayland or Xorg graphical session detected')


def required_tools(session, mode, target, destination, audio):
    required = ['notify-send']
    if session == 'wayland':
        required += ['swaymsg']
        if mode == 'screenshot':
            required += ['grimshot', 'grim', 'jq']
            if destination != 'save':
                required += ['wl-copy']
        else:
            required += ['wf-recorder', 'ffmpeg']
        if target in ('area', 'window'):
            required += ['slurp']
    else:
        required += ['xwininfo']
        if mode == 'screenshot':
            required += ['maim']
            if destination != 'save':
                required += ['xclip']
        else:
            required += ['ffmpeg']
        if target in ('area', 'window'):
            required += ['slop']
        if target in ('active', 'output'):
            required += ['xdotool']
        if target == 'output':
            required += ['xrandr']
    if mode == 'record' and audio != 'none' and not (shutil.which('pactl') or shutil.which('wpctl')):
        required += ['pactl (pulseaudio-utils) or wpctl (wireplumber)']
    return required


def wait_selection(command):
    result = subprocess.run(command, capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr


def screenshot(args):
    session = session_type()
    if session == 'wayland':
        # grimshot's argument parser splits paths on spaces. Pipe PNG data instead.
        command = ['grimshot']
        if args.delay:
            command += ['--wait', str(args.delay)]
        command += ['save', args.target, '-']
    else:
        rect = xorg.select_rect(args.target, wait_selection, Cancelled)
        time.sleep(args.delay + 0.15)  # Let the selection outline disappear.
        command = xorg.screenshot_command(rect)
    with tempfile.TemporaryFile() as image:
        result = subprocess.run(command, stdout=image, stderr=subprocess.PIPE)
        image.seek(0)
        signature = image.read(8)
        if signature != b'\x89PNG\r\n\x1a\n':
            if session == 'wayland' and result.returncode == 1 and args.target in ('area', 'window'):
                return
            raise RuntimeError(result.stderr.decode(errors='replace') or 'Screenshot failed; no PNG was produced.')
        # grimshot prints a trailing filename on stdout; retain exactly the PNG.
        while True:
            header = image.read(8)
            if len(header) != 8:
                raise RuntimeError('Incomplete PNG from grimshot')
            length = int.from_bytes(header[:4], 'big')
            image.seek(length + 4, 1)
            if header[4:] == b'IEND':
                break
        size = image.tell()
        image.seek(0)
        data = image.read(size)
        saved = None
        if args.destination != 'copy':
            saved = filename('PICTURES', '.png')
            saved.write_bytes(data)
        if args.destination != 'save':
            clipboard = ['wl-copy', '--type', 'image/png'] if session == 'wayland' else ['xclip', '-selection', 'clipboard', '-t', 'image/png']
            # xclip's background clipboard owner must not inherit a captured pipe.
            with tempfile.TemporaryFile() as errors:
                result = subprocess.run(clipboard, input=data, stdout=subprocess.DEVNULL, stderr=errors)
            if result.returncode:
                raise RuntimeError(f'Clipboard failed. Saved file: {saved or "none"}')
        notify('Screenshot captured', (str(saved) if saved else 'Copied to clipboard') + (' · copied to clipboard' if saved and args.destination == 'savecopy' else ''))


def geometry(rect):
    return f'{rect["x"]},{rect["y"]} {rect["width"]}x{rect["height"]}'


def walk(node):
    yield node
    for child in node.get('nodes', []) + node.get('floating_nodes', []):
        yield from walk(child)


def audio_device(mode):
    if mode == 'none':
        return None
    if shutil.which('pactl'):
        name = call(['pactl', 'get-default-sink' if mode == 'system' else 'get-default-source'])
    else:
        symbol = '@DEFAULT_AUDIO_SINK@' if mode == 'system' else '@DEFAULT_AUDIO_SOURCE@'
        info = call(['wpctl', 'inspect', symbol])
        match = re.search(r'node.name = "([^"]+)"', info)
        if not match:
            raise RuntimeError('No default audio device found')
        name = match[1]
    if not name:
        raise RuntimeError('No default audio device found')
    return name + ('.monitor' if mode == 'system' else '')


def audio_source(mode):
    device = audio_device(mode)
    return ['--audio-backend=pulse', '--audio=' + device, '-C', 'aac'] if device else []


def recording_command(output, geom, path, audio):
    command = ['wf-recorder', '-o', output, '-f', str(path), '-c', 'libx264', '-x', 'yuv420p',
               '-F', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-r', '30']
    if geom:
        command += ['-g', geom]
    return command + audio_source(audio)



def wayland_selection(target, wait_child):
    outputs = json.loads(call(['swaymsg', '-t', 'get_outputs', '-r']))
    outputs = [o for o in outputs if o.get('active')]
    output = next((o for o in outputs if o.get('focused')), outputs[0])
    geom = None
    if target in ('active', 'window'):
        nodes = list(walk(json.loads(call(['swaymsg', '-t', 'get_tree', '-r']))))
        if target == 'active':
            node = next((n for n in nodes if n.get('focused') and (n.get('app_id') or n.get('window'))), None)
            if not node:
                raise RuntimeError('No active window')
            geom = geometry(node['rect'])
        else:
            boxes = '\n'.join(geometry(n['rect']) for n in nodes if n.get('pid') and n.get('visible'))
            if not boxes:
                raise RuntimeError('No visible windows')
            with tempfile.TemporaryFile(mode='w+') as boxes_file:
                boxes_file.write(boxes + '\n'); boxes_file.seek(0)
                code, geom, _ = wait_child(['slurp', '-r'], stdin=boxes_file)
            if code or not geom:
                raise Cancelled()
    elif target == 'area':
        code, geom, _ = wait_child(['slurp', '-d'])
        if code or not geom:
            raise Cancelled()
    if geom:
        match = re.fullmatch(r'(-?\d+),(-?\d+) (\d+)x(\d+)', geom)
        if not match:
            raise RuntimeError('Invalid capture rectangle')
        x, y, w, h = map(int, match.groups())
        output = next((o for o in outputs if x >= o['rect']['x'] and y >= o['rect']['y'] and x+w <= o['rect']['x']+o['rect']['width'] and y+h <= o['rect']['y']+o['rect']['height']), None)
        if not output:
            raise RuntimeError('Video selection must fit within one monitor')
    return output['name'], geom


def record(args):
    RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (RUNTIME / 'lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('A capture or GIF export is already running')
        control = RUNTIME / 'control.sock'
        control.unlink(missing_ok=True)
        child = None
        phase = 'Selecting'
        started = time.monotonic()
        stop = False
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(control))
            server.listen(4)

            def events():
                nonlocal stop
                if select.select([server], [], [], 0)[0]:
                    conn, _ = server.accept()
                    with conn:
                        conn.settimeout(1)
                        try:
                            message = conn.recv(32).decode()
                            if message == 'stop' and phase != 'Exporting GIF':
                                stop = True
                            conn.sendall(json.dumps({'phase': phase, 'elapsed': int(time.monotonic() - started)}).encode())
                        except (OSError, UnicodeError):
                            pass

            def wait_child(cmd, **kwargs):
                nonlocal child
                with tempfile.TemporaryFile(mode='w+') as stdout, tempfile.TemporaryFile(mode='w+') as stderr:
                    child = subprocess.Popen(cmd, stdout=stdout, stderr=stderr, **kwargs)
                    while child.poll() is None:
                        events()
                        if stop:
                            child.terminate()
                            try:
                                child.wait(timeout=3)
                            except subprocess.TimeoutExpired:
                                child.kill()
                                child.wait()
                            raise Cancelled()
                        time.sleep(0.05)
                    stdout.seek(0); stderr.seek(0)
                    out, err, code = stdout.read(), stderr.read(), child.returncode
                    child = None
                    return code, out.strip(), err

            def pause(seconds):
                end = time.monotonic() + seconds
                while time.monotonic() < end:
                    events()
                    if stop:
                        raise Cancelled()
                    time.sleep(0.05)

            try:
                session = session_type()
                if session == 'wayland':
                    output, geom = wayland_selection(args.target, wait_child)
                else:
                    rect = xorg.select_rect(args.target, wait_child, Cancelled)
                phase = 'Starting'
                if args.delay:
                    notify('Recording countdown', f'Starts in {args.delay} seconds. Ctrl+Shift+Print cancels.')
                pause(args.delay + 0.3)
                path = filename('VIDEOS', '.mp4')
                command = (recording_command(output, geom, path, args.audio) if session == 'wayland'
                           else xorg.recording_command(rect, path, audio_device(args.audio)))
                with (RUNTIME / 'recorder.log').open('w') as log:
                    child = subprocess.Popen(command, stdout=log, stderr=log)
                    phase = 'Recording'; started = time.monotonic()
                    notify('Recording started', 'Ctrl+Shift+Print to stop and save. Open Record Video in Vicinae for recording controls.')
                    while child.poll() is None and not stop:
                        events(); time.sleep(0.1)
                    if child.poll() is None:
                        child.send_signal(signal.SIGINT)
                    phase = 'Saving'
                    end = time.monotonic() + 20
                    while child.poll() is None and time.monotonic() < end:
                        events(); time.sleep(0.1)
                    if child.poll() is None:
                        raise RuntimeError('Recorder did not finish; inspect recorder.log')
                    code = child.returncode; child = None
                success_codes = (0, 130, -signal.SIGINT) + ((255,) if session == 'x11' and stop else ())
                if code not in success_codes or not path.exists() or path.stat().st_size == 0:
                    raise RuntimeError(f'Recording failed. Details: {RUNTIME / "recorder.log"}')
                if not args.gif_only:
                    notify('Recording saved', str(path))
                if args.gif:
                    phase = 'Exporting GIF'; stop = False
                    notify('Exporting GIF', 'GIF export may take a moment.')
                    gif = path.with_suffix('.gif')
                    filters = 'fps=15,scale=min(1280\\,iw):-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse'
                    code, _, err = wait_child(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-filter_complex', filters, '-loop', '0', str(gif)])
                    if code or not gif.exists() or gif.stat().st_size == 0:
                        gif.unlink(missing_ok=True)
                        raise RuntimeError('MP4 saved, but GIF export failed: ' + err[-400:])
                    if args.gif_only:
                        path.unlink()
                    notify('GIF exported', str(gif))
            finally:
                if child and child.poll() is None:
                    child.send_signal(signal.SIGINT)
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill(); child.wait()
                control.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['screenshot', 'record', 'stop', 'status', 'check'])
    parser.add_argument('--mode', choices=['screenshot', 'record'], default='screenshot')
    parser.add_argument('--target', choices=['area', 'window', 'active', 'output', 'screen'], default='area')
    parser.add_argument('--destination', choices=['save', 'copy', 'savecopy'], default='savecopy')
    parser.add_argument('--audio', choices=['none', 'system', 'microphone'], default='none')
    parser.add_argument('--delay', type=int, choices=[0, 3, 5, 10], default=0)
    parser.add_argument('--gif', action='store_true')
    parser.add_argument('--gif-only', action='store_true')
    args = parser.parse_args()
    if args.gif_only:
        args.gif = True
        args.audio = 'none'
    if args.command in ('status', 'stop'):
        state = request(args.command)
        print(json.dumps(state))
        if args.command == 'stop' and not state:
            notify('Screen Capture', 'No recording is running')
        return
    if args.command == 'check':
        session = session_type()
        required = required_tools(session, args.mode, args.target, args.destination, args.audio)
        missing = [name for name in required if not shutil.which(name)]
        if missing:
            raise RuntimeError(f'Missing {session} tools: ' + ', '.join(missing))
        return
    time.sleep(0.5)  # Allow the launcher to disappear and restore focus.
    if args.command == 'screenshot':
        screenshot(args)
    elif args.target == 'screen':
        raise RuntimeError('Video recording supports one monitor at a time')
    else:
        record(args)


if __name__ == '__main__':
    try:
        main()
    except Cancelled:
        pass
    except Exception as error:
        print(str(error), file=sys.stderr)
        if len(sys.argv) > 1 and sys.argv[1] not in ('check', 'status'):
            notify('Screen Capture failed', str(error))
        sys.exit(1)
