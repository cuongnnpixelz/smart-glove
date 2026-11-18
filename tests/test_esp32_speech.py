import io
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import zlib

from SmartSignLanguage.collect_v2 import SampleStream
from SmartSignLanguage.esp32_speech import ESP32Speaker, SpeechSynthesizer


class SpeechTests(unittest.TestCase):
    def test_binary_audio_and_fragmented_ack_do_not_pollute_sensor_stream(self):
        client, device = socket.socketpair()
        device.settimeout(2)
        stream = SampleStream(client, flex_count=5, sample_ms=10)
        received, failures = [], []
        # Includes line breaks, control-command bytes and all 256 byte values.
        audio = bytes(range(256)) * 9 + b'PING\nSTART\n\xff'

        def firmware():
            pending = b''
            timestamp = 0

            def line():
                nonlocal pending
                while b'\n' not in pending:
                    pending += device.recv(2048)
                value, pending = pending.split(b'\n', 1)
                return value.decode('ascii')

            def reply(text):
                nonlocal timestamp
                timestamp += 10
                sensor = f'RAW5_100,{timestamp},1000,1100,1200,1300,1400,0,0,9.81,0,0,0\n'
                device.sendall(sensor.encode() + text[:5].encode())
                device.sendall((text[5:] + '\n').encode())

            try:
                self.assertEqual(line(), 'RAW5_100')
                self.assertEqual(line(), 'AUDIO_HELLO')
                reply('AUDIO_READY,1,16000,1024')
                begin = line().split(',')
                self.assertEqual(begin[0], 'AUDIO_BEGIN')
                job = begin[1]
                reply(f'AUDIO_STARTED,{job}')
                sequence = 0
                while True:
                    fields = line().split(',')
                    if fields[0] == 'AUDIO_END':
                        self.assertEqual(fields, ['AUDIO_END', job, str(sequence)])
                        reply(f'AUDIO_DONE,{job}')
                        break
                    self.assertEqual(fields[:3], ['AUDIO_DATA', job, str(sequence)])
                    size = int(fields[3])
                    while len(pending) < size:
                        pending += device.recv(2048)
                    block, pending = pending[:size], pending[size:]
                    self.assertEqual(zlib.crc32(block), int(fields[4], 16))
                    received.append(block)
                    reply(f'AUDIO_ACK,{job},{sequence}')
                    sequence += 1
            except BaseException as error:
                failures.append(error)

        thread = threading.Thread(target=firmware, daemon=True)
        thread.start()
        try:
            speaker = ESP32Speaker(stream)
            speaker.check_ready()
            speaker.play(audio)
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(failures, [])
            self.assertEqual(b''.join(received), audio)
            self.assertIsNone(stream.error)
            self.assertEqual(stream.serial, 6)
            self.assertTrue(all(row['flex_1'] == 1000 for _, row in stream.rows))
        finally:
            stream.close()
            device.close()

    def test_audio_error_aborts_without_retry(self):
        stream = Mock()
        stream.wait_audio.side_effect = [None, ValueError('AUDIO_ERROR,1,CRC')]
        with patch('SmartSignLanguage.esp32_speech.secrets.randbelow', return_value=0):
            with self.assertRaisesRegex(ValueError, 'CRC'):
                ESP32Speaker(stream).play(b'\xff'*1200)
        calls = [c.args[0] for c in stream.sock.sendall.call_args_list]
        self.assertEqual(calls[-1], b'AUDIO_ABORT,1\n')
        self.assertEqual(sum(c.startswith(b'AUDIO_DATA') for c in calls), 1)
        self.assertFalse(any(c.startswith(b'AUDIO_END') for c in calls))

    def test_empty_result_is_silent_and_only_final_text_is_synthesized(self):
        speaker = ESP32Speaker(Mock())
        speaker.synthesizer = Mock()
        speaker.play = Mock()
        self.assertFalse(speaker.speak_result('(no words)', []))
        speaker.synthesizer.prepare.assert_not_called()
        with patch('sys.stdout', new_callable=io.StringIO):
            self.assertTrue(speaker.speak_result('TÔI CẢM ƠN BẠN', ['TOI', 'CAM_ON', 'BAN']))
        speaker.synthesizer.prepare.assert_called_once_with('TÔI CẢM ƠN BẠN')
        speaker.play.assert_called_once()

    def test_cache_reuses_audio_without_calling_network(self):
        async def save(path):
            Path(path).write_bytes(b'mp3')
        with tempfile.TemporaryDirectory() as folder, \
                patch('edge_tts.Communicate') as tts, \
                patch('SmartSignLanguage.esp32_speech.encode_audio', return_value=b'\xff'*32):
            tts.return_value.save.side_effect = save
            synth = SpeechSynthesizer(voice='vi-VN-HoaiMyNeural', cache=folder)
            first = synth.prepare('Xin chào')
            second = synth.prepare('Xin chào')
            self.assertEqual(first, second)
            tts.assert_called_once()

    def test_volume_cannot_bypass_firmware_cap(self):
        for volume in (0, -1, 1.1):
            with self.assertRaises(ValueError):
                SpeechSynthesizer(volume=volume)
