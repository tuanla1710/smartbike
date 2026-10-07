# Smart Bike Controller V1

Firmware điều khiển xe đạp điện trên ESP32-S3-WROOM-1-N8 (flash 8 MB). Bản thiết kế nằm ở [docs/design/README.md](docs/design/README.md).

Build ảnh firmware chạy trên máy Linux và không cần mạch. Mạch chỉ cần khi nạp và mở console USB.

## Yêu cầu

| Thành phần | Ghi chú |
| --- | --- |
| Linux | Host đã dùng để cài ESP-IDF |
| Python 3 | Lệnh là `python3` |
| GCC | Dùng cho bộ đối chiếu luật điều khiển trên host |
| ESP-IDF v5.5.5 | Nằm ở `sources/esp-idf` |
| CMake và Ninja | ESP-IDF trên Linux không tự tải hai công cụ này |

## Cài ESP-IDF lần đầu

Từ thư mục gốc của repo:

```bash
git clone --depth 1 --branch v5.5.5 --recurse-submodules --shallow-submodules \
  https://github.com/espressif/esp-idf.git sources/esp-idf
cd sources/esp-idf
./install.sh esp32s3
python3 tools/idf_tools.py install cmake ninja
cd ../..
```

`install.sh` tải toolchain Xtensa và Python vào `~/.espressif`. Lệnh `idf_tools.py` tải CMake và Ninja vào cùng chỗ khi máy chưa có hai gói đó.

Mỗi terminal mới phải nạp môi trường trước khi gọi `idf.py`:

```bash
. sources/esp-idf/export.sh
```

Dấu chấm đầu dòng là bắt buộc. Sau khi nạp, `idf.py --version` in `ESP-IDF v5.5.5`.

## Kiểm tra luật điều khiển trên host

Bước này biên dịch lõi C bằng GCC của máy và so với giả lập Python. Chạy trước khi nạp mạch:

```bash
make -C firmware/host
cd firmware
python3 host/diff_oracle.py
python3 -m unittest sim.test_sim
```

Kết quả đúng là `ok files=8 cases=14` và unittest OK. REPL giả lập:

```bash
cd firmware
python3 -m sim
```

## Build firmware

```bash
. sources/esp-idf/export.sh
cd firmware
idf.py set-target esp32s3
idf.py build
```

`set-target` chỉ cần lần đầu, khi chưa có `firmware/sdkconfig`. Các lần sau chỉ cần `idf.py build`.

Ảnh nạp: `firmware/build/smartbike.bin`. Phân vùng ứng dụng là 2 MB (`firmware/partitions_8mb.csv`).

## Nạp và mở console

Cắm cáp USB vào cổng USB của module. Cổng thường là `/dev/ttyACM0`. Kiểm tra bằng `ls /dev/ttyACM*`.

Trong thư mục `firmware/`, shell đã nạp `export.sh`:

```bash
idf.py -p /dev/ttyACM0 flash monitor
```

Dòng đầu console là `ok boot`. Thoát màn hình log bằng Ctrl+].

Nạp lại mà không mở log:

```bash
idf.py -p /dev/ttyACM0 flash
```

Console đi qua USB Serial/JTAG. Lệnh debug nằm ở [docs/design/09-debug-commands.md](docs/design/09-debug-commands.md).

Chạy kịch bản portable trên mạch đã nạp (cần `pyserial`):

```bash
python3 -m pip install -r tools/requirements.txt
python3 -m sim.runner --port /dev/ttyACM0 scenarios/portable/boot.txt
```

Lệnh `hw` và `tick` chỉ có trên giả lập. Trên mạch, `hw` trả `err sim-only`.
