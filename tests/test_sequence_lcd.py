"""LCD transport uses the final prediction, not a rejected classifier candidate."""
import io
import socket
import unittest
from unittest.mock import Mock, patch, call

from SmartSignLanguage import predict_sequence_v2 as app


class SequenceLcdTests(unittest.TestCase):
    def test_wire_mapping_and_unknown_clears_previous_result(self):
        client, device = socket.socketpair()
        self.addCleanup(client.close)
        self.addCleanup(device.close)
        device.settimeout(1)
        for label, expected in (
            ("TRO_TRAI_DUOI", b"SEQ,XIN_CHAO\n"),
            ("GIUA_TRAI_DUOI", b"SEQ,CAM_ON\n"),
            ("TRO_PHAI_DUOI", b"SEQ,TAM_BIET\n"),
            ("NONE", b"SEQ,NONE\n"),
            ("UNKNOWN\nSEQ,XIN_CHAO", b"SEQ,NONE\n"),
        ):
            app.send_lcd_result(client, label)
            self.assertEqual(device.recv(100), expected)

    def test_predict_sends_final_label_after_stop_and_clears_on_exit(self):
        for accepted, packet in (("NONE", b"SEQ,NONE\n"), ("GIUA_TRAI_DUOI", b"SEQ,CAM_ON\n")):
            with self.subTest(accepted=accepted):
                model, stream = Mock(), Mock()
                model.motion_checks = "strict"
                model.manifest = {"evaluation_scope": "session_holdout"}
                model.predict_details.return_value = (accepted, "TRO_TRAI_DUOI", "test reason")
                stream.capture.return_value = []
                with patch.object(app, "SequenceModel", return_value=model), \
                        patch.object(app.socket, "create_connection"), \
                        patch.object(app, "SampleStream", return_value=stream), \
                        patch.object(app, "countdown"), \
                        patch.object(app, "make_imu_reference", return_value={}), \
                        patch("builtins.input", side_effect=["", "", "Q"]), \
                        patch("sys.stdout", new_callable=io.StringIO):
                    self.assertEqual(app.main(["--model", "test-model"]), 0)
                self.assertEqual(stream.sock.sendall.call_args_list,
                                 [call(b"START\n"), call(b"STOP\n"), call(packet), call(b"SEQ,NONE\n")])
                stream.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
