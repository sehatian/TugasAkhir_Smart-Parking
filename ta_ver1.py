import requests, cv2, time, re, sys, argparse, os, threading
import serial, serial.tools.list_ports
from pyzbar.pyzbar import decode
from ultralytics import YOLO
from paddleocr import PaddleOCR

CAMERA_PORT_GERBANG_MASUK_QR = 1
CAMERA_PORT_GERBANG_MASUK_PLAT = 2
CAMERA_PORT_GERBANG_KELUAR_QR = 0  # Test ganti 2
CAMERA_PORT_GERBANG_KELUAR_PLAT = 2  # Test ganti 3

license_plate_detector = YOLO(
    os.path.join("C:/Users/Rain/Documents/Tugas Akhir/main_program", "best.pt")
)

ocr = PaddleOCR(use_angle_cls=True, lang="en")


def millis():
    return time.time() * 1000


class ParkingSystem:
    def __init__(self, server_url, camera_port_qr, camera_port_plat, serial_port):
        self.server_url = server_url
        self.camera_port_qr = camera_port_qr
        self.camera_port_plat = camera_port_plat
        self.serial_port = serial_port
        self.running = True
        self.lock = threading.Lock()

    def detect_plate(self, image):
        plates = license_plate_detector(image)[0]
        for plate in plates.boxes.data.tolist():
            img = image.copy()
            x1, y1, x2, y2, confidence, class_id = plate
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            crop_plate = img[int(y1) : int(y2), int(x1) : int(x2), :]
            self.crop_plate_gray = cv2.cvtColor(crop_plate, cv2.COLOR_BGR2GRAY)
            cv2.imwrite(
                f"C:/Users/Rain/Documents/Tugas Akhir/frame_{self.camera_port_qr}_plat.jpg",
                image,
            )
            cv2.imwrite(
                f"C:/Users/Rain/Documents/Tugas Akhir/frame_{self.camera_port_qr}_plat_crop.jpg",
                self.crop_plate_gray,
            )
            return True

    def preprocess_text(self, text):
        cleaned_text = re.sub(r"[^a-zA-Z0-9]", "", text)
        cleaned_text = cleaned_text.upper()
        return cleaned_text

    def read_text(self):
        results = ocr.ocr(self.crop_plate_gray, cls=True)
        best_text = ""
        output_text = ""
        if results[0] is not None:
            for sublist in results:
                for inner_list in sublist:
                    extracted_string = inner_list[1][0]
                    best_text += self.preprocess_text(extracted_string)
                    print(best_text)
                    if 5 < len(best_text) < 11:
                        output_text = best_text
                        break
                    else:
                        output_text = "XXXXXX"
        else:
            output_text = "XXXXXX"
        return output_text

    def read_plat_number(self):
        cap_camera_port_plat = cv2.VideoCapture(self.camera_port_plat)
        while self.running:
            ret, frame = cap_camera_port_plat.read()
            if ret:
                cv2.imwrite(
                    f"C:/Users/Rain/Documents/Tugas Akhir/live_{self.camera_port_plat}_plat.jpg",
                    frame,
                )
                if self.detect_plate(frame):
                    nomorPlat = self.read_text()
                    break
        cap_camera_port_plat.release()
        # cv2.destroyAllWindows()
        return nomorPlat

    def read_qr_code(self):
        last_time = millis()
        scannedQrCode = None
        cap_camera_port_qr = cv2.VideoCapture(self.camera_port_qr)
        while self.running:
            ret, frame = cap_camera_port_qr.read()
            if ret:
                grayQr = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                (thresh, bwQr) = cv2.threshold(grayQr, 120, 255, cv2.THRESH_BINARY)
                decoded_objs = decode(bwQr)
                if decoded_objs:
                    for obj in decoded_objs:
                        scannedQrCode = obj.data.decode("utf-8")
                    break
                cv2.imwrite(
                    f"C:/Users/Rain/Documents/Tugas Akhir/live_{self.camera_port_qr}_qr.jpg",
                    frame,
                )
            if millis() - last_time > 15 * 1000:
                break
        cv2.imwrite(
            f"C:/Users/Rain/Documents/Tugas Akhir/frame_{self.camera_port_qr}_qr.jpg",
            frame,
        )
        cap_camera_port_qr.release()
        # cv2.destroyAllWindows()
        return scannedQrCode

    def send_database_validasi_data_in(self, code, plat_masuk, gambar_in):
        url = self.server_url + "/api/valid-In"
        data = {
            "code": code,
            "plat_masuk": plat_masuk,
        }
        files = {"gambar_in": open(gambar_in, "rb")}
        response = requests.post(url, data=data, files=files)
        if response.status_code == 200:
            json_response = response.json()
            if "success" in json_response["status"]:
                return json_response["message"]
            else:
                return False
        else:
            return False

    def send_database_validasi_data_out(self, code, plat_keluar, gambar_out):
        url = self.server_url + "/api/valid-Out"
        data = {
            "code": code,
            "plat_keluar": plat_keluar,
        }
        files = {"gambar_out": open(gambar_out, "rb")}
        response = requests.post(url, data=data, files=files)
        if response.status_code == 200:
            json_response = response.json()
            if "success" in json_response["status"]:
                return json_response["message"]
            else:
                return False
        else:
            return False

    def get_database_parking_slot(self):
        url = self.server_url + "/api/slot"
        response = requests.get(url)
        if response.status_code == 200:
            json_response = response.json()
            print(json_response)
            return json_response["Jumlah slot tersedia"]
        else:
            return 99

    def send_serial_park_slot_data(self, id_system, park_slot_data):
        with self.lock:
            self.serial_port.write(
                b"\xFA"
                + id_system.to_bytes(1, "big")
                + b"\x1B"
                + park_slot_data.to_bytes(1, "big")
            )

    def send_serial_qr_matched(self, id_system):
        if id_system == 1:
            qr_code = self.read_qr_code()
            print(f"[{id_system}] CODE QR:", qr_code)
            if qr_code:
                self.serial_port.write(b"\xFA\x01\x1C\x01")
                plat_masuk = self.read_plat_number()
                print(f"[{id_system}] NOMOR PLAT:", plat_masuk)
                if plat_masuk:
                    gambar_in = f"C:/Users/Rain/Documents/Tugas Akhir/frame_{self.camera_port_qr}_plat.jpg"
                    if self.send_database_validasi_data_in(
                        qr_code, plat_masuk, gambar_in
                    ):
                        self.serial_port.write(b"\xFA\x01\x1A\x01")
                    else:
                        self.serial_port.write(b"\xFA\x01\x1A\x00")
                else:
                    self.serial_port.write(b"\xFA\x01\x1A\x00")
            else:
                self.serial_port.write(b"\xFA\x01\x1A\x00")

        elif id_system == 2:
            qr_code = self.read_qr_code()
            print(f"[{id_system}] CODE QR:", qr_code)
            if qr_code:
                self.serial_port.write(b"\xFA\x02\x1C\x01")
                plat_keluar = self.read_plat_number()
                print(f"[{id_system}] NOMOR PLAT:", plat_keluar)
                if plat_keluar:
                    gambar_out = f"C:/Users/Rain/Documents/Tugas Akhir/frame_{self.camera_port_qr}_plat.jpg"
                    if self.send_database_validasi_data_out(
                        qr_code, plat_keluar, gambar_out
                    ):
                        self.serial_port.write(b"\xFA\x02\x1A\x01")
                    else:
                        self.serial_port.write(b"\xFA\x02\x1A\x00")
                else:
                    self.serial_port.write(b"\xFA\x02\x1A\x00")
            else:
                self.serial_port.write(b"\xFA\x02\x1A\x00")

    def check_serial_event(self):
        while self.running:
            if self.serial_port.in_waiting > 0:
                try:
                    dataInput = self.serial_port.read(1)
                    if dataInput != b"\xAF":
                        print(dataInput.decode("utf-8"), end="")
                    if dataInput == b"\xAF":
                        dataInput = self.serial_port.read(1)
                        idSystem = int(dataInput.hex(), 16)
                        dataInput = self.serial_port.read(1)
                        if idSystem == 1:
                            if dataInput == b"\x2A":  # Kalau kedeteksi Sensor A
                                print(f"[{idSystem}] Asking for QR data")
                                self.send_serial_qr_matched(idSystem)
                            elif dataInput == b"\x2B":  # Kalau mobil sudah masuk
                                print(f"[{idSystem}] Asking for park slot")
                                self.send_serial_park_slot_data(
                                    idSystem, self.get_database_parking_slot()
                                )
                            self.serial_port.reset_input_buffer()
                        elif idSystem == 2:
                            if dataInput == b"\x2A":  # Kalau kedeteksi Sensor A
                                print(f"[{idSystem}] Asking for QR data")
                                self.send_serial_qr_matched(idSystem)
                            elif dataInput == b"\x2B":  # Kalau mobil sudah masuk
                                print(f"[{idSystem}] Asking for park slot")
                                self.send_serial_park_slot_data(idSystem, 99)
                            self.serial_port.reset_input_buffer()
                except UnicodeDecodeError:
                    print("Unable to decode byte:", dataInput)

    def start(self):
        thread = threading.Thread(target=self.check_serial_event)
        thread.start()

    def stop(self):
        self.running = False
        self.serial_port.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Main program")
    parser.add_argument("--url", required=True, help="Input URL")
    args = parser.parse_args()
    SERVER_URL = args.url

    serial1 = serial.Serial(
        serial.tools.list_ports.comports()[0].device, 115200, timeout=0.1
    )
    serial2 = serial.Serial(
        serial.tools.list_ports.comports()[1].device, 115200, timeout=0.1
    )

    parking_system_masuk = ParkingSystem(
        SERVER_URL,
        CAMERA_PORT_GERBANG_MASUK_QR,
        CAMERA_PORT_GERBANG_MASUK_PLAT,
        serial1,
    )
    parking_system_keluar = ParkingSystem(
        SERVER_URL,
        CAMERA_PORT_GERBANG_KELUAR_QR,
        CAMERA_PORT_GERBANG_KELUAR_PLAT,
        serial2,
    )

    parking_system_masuk.start()
    parking_system_keluar.start()

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        parking_system_masuk.stop()
        parking_system_keluar.stop()
