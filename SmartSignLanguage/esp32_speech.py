"""Vietnamese TTS on the PC, acknowledged audio playback on ESP32/MAX98357A."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import unicodedata
import zlib


SAMPLE_RATE = 16000
CHUNK_SIZE = 1024
DEFAULT_VOICE = 'google-vi'
CACHE = Path(__file__).resolve().parents[1] / '.runtime' / 'speech_cache'


def add_speech_arguments(parser):
    parser.add_argument('--speak', action='store_true', help='Read final result on ESP32/MAX98357A')
    parser.add_argument('--speech-voice', default=DEFAULT_VOICE)
    parser.add_argument('--speech-volume', type=float, default=0.7,
                        help='0..1 relative to the firmware low-volume cap (default 0.7)')


def encode_audio(source, volume=0.7):
    """16 kHz mu-law needs 16 kB/s, fitting the existing 230400-baud COM."""
    if not 0 < volume <= 1:
        raise ValueError('speech-volume phai > 0 va <= 1')
    import imageio_ffmpeg
    command = [imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-hide_banner', '-loglevel', 'error',
               '-i', str(source), '-t', '60', '-vn', '-ac', '1', '-ar', str(SAMPLE_RATE),
               '-af', f'volume={volume}', '-f', 'mulaw', '-acodec', 'pcm_mulaw', 'pipe:1']
    result = subprocess.run(command, capture_output=True, timeout=30,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ValueError('Khong chuyen duoc am thanh: ' + result.stderr.decode(errors='replace')[:250])
    if not result.stdout or len(result.stdout) >= SAMPLE_RATE * 60:
        raise ValueError('Am thanh rong hoac qua dai (gioi han 60 giay); khong phat cau bi cat')
    return result.stdout


class SpeechSynthesizer:
    def __init__(self, voice=DEFAULT_VOICE, volume=0.7, cache=CACHE):
        if not 0 < volume <= 1:
            raise ValueError('speech-volume phai > 0 va <= 1')
        self.voice, self.volume, self.cache = voice, volume, Path(cache)

    def prepare(self, text):
        text = ' '.join(unicodedata.normalize('NFC', text).split())
        if not text or len(text) > 500:
            raise ValueError('Cau doc phai co 1..500 ky tu')
        key = hashlib.sha256(json.dumps([text, self.voice, self.volume, 'mulaw16k-v1'],
                                       ensure_ascii=False).encode('utf-8')).hexdigest()
        self.cache.mkdir(parents=True, exist_ok=True)
        target = self.cache / (key + '.ulaw')
        if target.exists():
            data = target.read_bytes()
            if 0 < len(data) < SAMPLE_RATE * 60:
                return data
        async def generate(path):
            import edge_tts
            await asyncio.wait_for(edge_tts.Communicate(text, self.voice).save(str(path)), 45)

        with tempfile.TemporaryDirectory(prefix='glove-speech-') as folder:
            mp3 = Path(folder) / 'voice.mp3'
            if self.voice == 'google-vi':
                from gtts import gTTS
                gTTS(text=text, lang='vi', lang_check=False, timeout=(5, 20)).save(str(mp3))
            else:
                asyncio.run(generate(mp3))
            data = encode_audio(mp3, self.volume)
        temporary = target.with_suffix('.' + secrets.token_hex(4) + '.tmp')
        try:
            temporary.write_bytes(data)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return data


class ESP32Speaker:
    def __init__(self, stream, voice=DEFAULT_VOICE, volume=0.7):
        self.stream = stream
        self.synthesizer = SpeechSynthesizer(voice, volume)

    def check_ready(self):
        with self.stream.condition:
            self.stream.audio_messages.clear()
        self.stream.sock.sendall(b'AUDIO_HELLO\n')
        self.stream.wait_audio('AUDIO_READY,1,16000,1024')

    def play(self, audio):
        if not audio or len(audio) >= SAMPLE_RATE * 60:
            raise ValueError('Do dai am thanh khong hop le')
        job = secrets.randbelow(0x7ffffffe) + 1
        try:
            self.stream.sock.sendall(f'AUDIO_BEGIN,{job}\n'.encode('ascii'))
            self.stream.wait_audio(f'AUDIO_STARTED,{job}')
            count = 0
            for start in range(0, len(audio), CHUNK_SIZE):
                block = audio[start:start + CHUNK_SIZE]
                crc = zlib.crc32(block)
                header = f'AUDIO_DATA,{job},{count},{len(block)},{crc:08x}\n'.encode('ascii')
                # One atomic write lock covers header AND binary payload; PING
                # heartbeat must never be inserted into an audio frame.
                self.stream.sock.sendall(header + block)
                self.stream.wait_audio(f'AUDIO_ACK,{job},{count}')
                count += 1
            self.stream.sock.sendall(f'AUDIO_END,{job},{count}\n'.encode('ascii'))
            self.stream.wait_audio(f'AUDIO_DONE,{job}', timeout=5)
        except BaseException:
            # Do not retry and accidentally speak a sentence twice.
            try:
                self.stream.sock.sendall(f'AUDIO_ABORT,{job}\n'.encode('ascii'))
            except OSError:
                pass
            raise

    def speak_result(self, text, words):
        if not words or all(word == 'NONE' for word in words):
            return False
        try:
            print('ÂM THANH: đang chuẩn bị; chờ phát xong rồi làm câu tiếp.', flush=True)
            audio = self.synthesizer.prepare(text)
            print('LOA ESP32: ' + text, flush=True)
            self.play(audio)
            print('ĐÃ PHÁT XONG.', flush=True)
            return True
        except Exception as error:
            # An audio problem never changes the prediction or its evaluation.
            print(f'LỖI ÂM THANH: {error}. Kết quả nhận diện vẫn được giữ.', flush=True)
            return False


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial-port', default='COM3')
    parser.add_argument('--text', default='Xin chào. Tôi cảm ơn bạn.')
    parser.add_argument('--audio-file', type=Path, help='Local WAV/MP3 instead of online TTS')
    parser.add_argument('--prepare-only', action='store_true', help='Cache speech without opening COM')
    add_speech_arguments(parser)
    args = parser.parse_args(argv)
    stream = transport = None
    try:
        synthesizer = SpeechSynthesizer(args.speech_voice, args.speech_volume)
        audio = (encode_audio(args.audio_file, args.speech_volume) if args.audio_file
                 else synthesizer.prepare(args.text))
        print(f'ÂM THANH: {len(audio)/SAMPLE_RATE:.2f} giây, 16 kHz.', flush=True)
        if args.prepare_only:
            print('Đã chuẩn bị âm thanh; chưa kết nối/phát trên ESP32.')
            return 0
        from .serial_transport import SerialTransport
        from .collect_v2 import SampleStream
        transport = SerialTransport(args.serial_port)
        stream = SampleStream(transport, flex_count=5, sample_ms=10)
        stream.check_ready()
        speaker = ESP32Speaker(stream)
        speaker.check_ready()
        speaker.play(audio)
        print('ESP32 XÁC NHẬN PHÁT XONG. Kiểm tra tiếng ở loa MAX98357A.')
        return 0
    except (KeyboardInterrupt, EOFError):
        return 0
    except Exception as error:
        print(f'LỖI ÂM THANH: {error}')
        return 1
    finally:
        if stream:
            stream.close()
        elif transport:
            transport.close()


if __name__ == '__main__':
    raise SystemExit(main())
