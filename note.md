# Nhật ký phát triển — Smart Bike Controller V1

Checklist đầy đủ nằm ở [docs/design/10-implementation-checklist.md](docs/design/10-implementation-checklist.md). File này chỉ ghi việc còn phải làm và log theo ngày.

## Đã có trong repo

- Lõi điều khiển `firmware/components/vehicle/bike_ctrl.c`, khớp giả lập: `make -C firmware/host && python3 host/diff_oracle.py` ra `ok files=8 cases=14`.
- Project ESP-IDF v5.5.5 build ra `firmware/build/smartbike.bin`.
- Khung task: `vehicle` 10 ms, `sensors` 50 ms, `gps`, `bike_console`, NimBLE.
- Driver tự viết: GPIO/LEDC, NVS, INA228, BH1750, parser NMEA, console, gói BLE 32 byte.
- `imu.c` và `lidar.c` chỉ dò chip. Chưa đọc gia tốc và chưa đọc khoảng cách.

## Còn phải viết

1. **BMI270.** Đưa init blob của Bosch vào firmware. Cấu hình INT1 push-pull, active-high, any-motion. `vehicle_task` đã đếm cạnh lên GPIO38 và giữ `motion` 250 ms. Thiếu blob thì chân ngắt không phát xung đúng.
2. **VL53L1X.** Đưa ULD của ST vào, bật continuous sau khi `XSHUT` cao. Ghi `range_mm` vào plant. `obstacle` chỉ là cờ khi mẫu hợp lệ, tuổi dưới 500 ms và khoảng cách dưới 4000 mm. Cờ này không được kéo phanh.
3. **XSHUT khi chưa có driver LiDAR.** Phase 4 giữ `XSHUT` thấp cho đến khi driver VL53L1X init xong. Hiện task `sensors` kéo cao suốt lúc không ngủ.
4. **GPS sau câu hợp lệ đầu.** Parser đã nhận RMC/GGA ở 9600 8N1 và loại checksum sai, câu 0,0, câu ngoài tầm. Phase 9 còn bước nâng baud sau câu hợp lệ đầu tiên.
5. **Thức dậy GPIO38.** Firmware gọi `esp_sleep_enable_ext0_wakeup(GPIO38, 1)` đúng hợp đồng. Trên ESP32-S3, ext0 chỉ nhận GPIO 0–21. GPIO38 không thuộc nhóm đó, silicon từ chối lời gọi. Phase 10 trên mạch cần một quyết định phần cứng trước khi ngủ thật pass được. Giữ nguyên lời gọi cho đến khi quyết định đó được ghi vào tài liệu thiết kế.

## Còn phải làm trên mạch

Code đã có. Các ô dưới đây mở cho đến khi nạp và đo.

| Phase | Việc |
| --- | --- |
| 0 | Nạp USB, console in `ok boot` |
| 1 | Đo bảy gate 0 V, LED đỗ xe nhấp 50 ms mỗi 2 s, `XSHUT` thấp lúc boot |
| 2 | `arm` rồi reset thường: `armed=0`. Deep sleep và CRC đúng mới giữ arm |
| 3 | `status`, `gates`, `watch 100`, `watch off` khớp `scenarios/portable/boot.txt` |
| 4 | `i2c` thấy `0x40`, `0x23`, `0x29`, `0x68`. `power` khoảng 4600–4800 mV. Mất SDA quá 200 ms thì `inhibit=power` |
| 5 | Rung dưới 30 ms không đổi `stable`. Trái và phải cùng thấp thì `hazard=1` |
| 6 | Đèn pha theo lux thật: dưới 100 bật, 100–200 giữ, trên 200 tắt |
| 7 | Chặn task `vehicle` quá 50 ms: bảy gate về 0 V. Reset watchdog xóa arm |
| 8 | `arm`, `debug on`, `hold` từng tải trên J1, đo dòng. Luật còi khớp `horn_budget.txt` |
| 9 | Lux, xung IMU, range LiDAR, câu GPS trên bo thật. `inject` không đổi áp và dòng |
| 10 | `ride start` chỉ từ `PARKING`. `RIDING` không sang `ALARM`. Ngủ và thức theo quyết định GPIO38 ở mục 5 phía trên |
| 11 | Notify BLE 32 byte khớp lệnh `snapshot`. Write `0x01`–`0x07` vào cùng queue với console |
| 12 | `python3 -m pip install -r firmware/tools/requirements.txt` rồi `python3 -m sim.runner --port <cổng> scenarios/portable` |
| 13 | Ký từng ca ở mục 13 của checklist bằng log USB hoặc đo điện |

Ngoài phạm vi bản này: client OTA, Wi-Fi, MQTT, app điện thoại, CAN, camera, màn hình.

## Log

### 2026-10-07

- Cài ESP-IDF v5.5.5 vào `sources/esp-idf`. CMake và Ninja tải thêm vào `~/.espressif` vì máy chưa có sẵn.
- Build ESP32-S3 thành công: `firmware/build/smartbike.bin`, khoảng 562 KB, phân vùng 2 MB còn trống khoảng 73%.
- Sửa để dịch được: `stdbool.h` trong `bike_port.h`, in `energy_mwh` bằng `%u` trên Xtensa, đổi tên component `console` thành `bike_console` để không đè component console của ESP-IDF, bật `CONFIG_ESP_TIMER_SUPPORTS_ISR_DISPATCH_METHOD` cho timer failsafe.
- Đối chiếu host sau các sửa đó vẫn `ok files=8 cases=14`.
- Thêm `README.md` hướng dẫn cài, build và nạp.
- Chưa nạp mạch. BMI270 và VL53L1X vẫn chỉ dò chip.
