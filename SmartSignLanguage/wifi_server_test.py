import socket
import time

ESP32_IP = "192.168.137.115"
PORT = 5000

print("==========================")
print("PYTHON -> ESP32 TCP")
print("==========================")

while True:
    try:
        print()
        print(
            f"Dang ket noi ESP32 "
            f"{ESP32_IP}:{PORT} ..."
        )

        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        sock.settimeout(5)

        sock.connect(
            (ESP32_IP, PORT)
        )

        sock.settimeout(None)

        print("KET NOI ESP32 THANH CONG!")
        break

    except Exception as e:
        print("Chua ket noi duoc:", e)
        print("Thu lai sau 2 giay...")

        try:
            sock.close()
        except:
            pass

        time.sleep(2)


buffer = ""

while True:
    try:
        data = sock.recv(1024)

        if not data:
            print("ESP32 da ngat ket noi.")
            break

        buffer += data.decode(
            "utf-8",
            errors="ignore"
        )

        while "\n" in buffer:
            line, buffer = buffer.split(
                "\n",
                1
            )

            line = line.strip()

            if not line:
                continue

            print("ESP32 GUI ->", line)

            # Gui tra lai ESP32
            reply = "PYTHON_OK\n"

            sock.sendall(
                reply.encode("utf-8")
            )

            print(
                "PYTHON GUI ->",
                reply.strip()
            )

    except KeyboardInterrupt:
        print("\nDung chuong trinh.")
        break

    except Exception as e:
        print("LOI:", e)
        break

sock.close()