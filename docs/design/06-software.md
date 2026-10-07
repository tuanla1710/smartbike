# 6. Phần mềm V1

Firmware nằm ở `firmware/`. Lõi điều khiển là `components/vehicle/bike_ctrl.c`, cùng luật với `firmware/sim`. Tài liệu này khóa ngôn ngữ, cây source, task và layout byte. Kiến trúc (tầng, chiều phụ thuộc, mặt phẳng) nằm ở [07-software-architecture.md](07-software-architecture.md). Hợp đồng với PCB vẫn nằm ở [04-firmware.md](04-firmware.md). Nếu hai tài liệu lệch nhau về chân hoặc hành vi tải, `04-firmware.md` thắng.

V1 chỉ có phần mềm trên ESP32-S3 và một bộ công cụ trên máy tính để bring-up. Không có app điện thoại, không có cloud, không có OTA trong bản firmware đầu tiên lên mạch.

## 6.1 Ngôn ngữ

| Lớp | Ngôn ngữ | Dùng để |
| --- | --- | --- |
| Firmware trên xe | C11, ESP-IDF 5.3 trở lên | Toàn bộ điều khiển, cảm biến, BLE, ngủ |
| Công cụ máy tính | Python 3.11 | Xem log USB, đối chiếu địa chỉ I2C, ghi `SHUNT_CAL` sau khi đo shunt |
| Build firmware | CMake + Kconfig của ESP-IDF | Biên dịch, partition 8 MB, cờ cấu hình |

Không dùng C++ hay Rust trên mạch. API BMI270 của Bosch và ULD VL53L1X của ST là C; đưa vào ESP-IDF bằng component C thì không phải bọc lại.

Trên mạch không chạy Python, MicroPython, hay Arduino framework. USB Serial/JTAG của ESP32-S3 là cổng nạp và console, không phải một runtime thứ hai.

Wi-Fi của module để tắt trong V1. Radio chỉ bật Bluetooth LE.

## 6.2 Cây source

Repo đặt firmware cạnh `hardware/` và `docs/`, không nhét vào `hardware/kicad/`.

```
firmware/
├── CMakeLists.txt                 project ESP-IDF
├── sdkconfig.defaults             target esp32s3, NimBLE, LEDC, deep sleep
├── partitions_8mb.csv             nvs, otadata, factory, ota_0, ota_1
├── main/
│   ├── CMakeLists.txt
│   ├── Kconfig.projbuild
│   └── app_main.c                 đúng thứ tự mục 4.8
├── components/
│   ├── board/                     GPIO, mức tích cực, địa chỉ I2C
│   │   ├── CMakeLists.txt
│   │   ├── include/board.h
│   │   └── board.c                ghi 0 mọi gate trước khi thành output
│   ├── config/                    hằng hiệu chuẩn và ngưỡng, một nơi
│   │   ├── CMakeLists.txt
│   │   ├── include/bike_config.h
│   │   ├── bike_config.c          NVS, mặc định khi chưa ghi
│   │   └── defaults.h
│   ├── power/
│   │   ├── CMakeLists.txt
│   │   ├── include/ina228.h
│   │   ├── include/power_mode.h
│   │   ├── ina228.c               SHUNT_CAL = 1250, đọc V/I/P/energy
│   │   └── power_mode.c           SLEEP, PARKING, RIDING, ALARM
│   ├── sensors/
│   │   ├── CMakeLists.txt
│   │   ├── include/i2c_bus.h
│   │   ├── include/gps.h
│   │   ├── include/lidar.h
│   │   ├── include/imu.h
│   │   ├── include/light.h
│   │   ├── i2c_bus.c              một mutex, 100 kHz, GPIO8/GPIO9
│   │   ├── gps.c                  UART GPIO17/18, 9600 8N1 lúc mở
│   │   ├── lidar.c                VL53L1X, XSHUT GPIO4
│   │   ├── imu.c                  BMI270, INT1 ra GPIO38
│   │   └── light.c                BH1750
│   ├── vehicle/
│   │   ├── CMakeLists.txt
│   │   ├── include/inputs.h
│   │   ├── include/lighting.h
│   │   ├── include/turn_signal.h
│   │   ├── include/brake.h
│   │   ├── include/horn.h
│   │   ├── inputs.c               debounce, HAZARD = LEFT và RIGHT
│   │   ├── lighting.c             LEDC 1 kHz, 10 bit
│   │   ├── turn_signal.c          1.25 Hz, duty 50%
│   │   ├── brake.c                GPIO mức, không PWM
│   │   └── horn.c                 GPIO mức, không PWM
│   ├── security/
│   │   ├── CMakeLists.txt
│   │   ├── include/motion.h
│   │   ├── include/alarm.h
│   │   ├── motion.c               ngưỡng IMU lấy từ config
│   │   └── alarm.c                nháy đèn, còi theo chu kỳ
│   ├── link/
│   │   ├── CMakeLists.txt
│   │   ├── include/ble_status.h
│   │   ├── include/snapshot.h
│   │   ├── ble_status.c           GATT, NimBLE
│   │   └── snapshot.c             bản sao trạng thái cho BLE
│   ├── console/                   dòng lệnh USB, không ghi GPIO
│   └── third_party/
│       ├── bmi270/                Bosch BMI270 SensorAPI, blob init
│       └── vl53l1x/               ST VL53L1X ULD
└── tools/                         không biên dịch vào firmware
    ├── requirements.txt
    └── bringup_log.py             đọc console USB, in dòng I2C scan
```

`main/app_main.c` chỉ gọi init rồi tạo task. Không đặt logic đèn hay INA228 trong `main`.

`board.h` là nơi duy nhất ghi số GPIO. Module khác include `board.h`, không gõ số chân rải rác.

`config/defaults.h` là nơi duy nhất ghi `Rshunt`, `SHUNT_CAL`, `CURRENT_LSB`, ngưỡng lux, tần số xi-nhan, và cờ “đã biết dòng còi”. Sửa shunt thì sửa một file này rồi ghi lại NVS.

## 6.3 Partition flash 8 MB

Module là N8, không PSRAM. Bảng partition chừa chỗ OTA dù bản đầu chưa nạp qua không khí.

| Tên | Kiểu | Kích thước | V1 dùng |
| --- | --- | --- | --- |
| `nvs` | data | 24 KB | config, cờ arm output |
| `otadata` | data | 8 KB | để trống cho bản sau |
| `phy_init` | data | 4 KB | calibration radio |
| `factory` | app | 2 MB | firmware đang chạy |
| `ota_0` | app | 2 MB | chưa ghi |
| `ota_1` | app | 2 MB | chưa ghi |

Phần còn lại của 8 MB để trống. Không bật app rollback ở bản đầu.

## 6.4 Task

Ba task của ứng dụng, cộng task NimBLE do stack tạo. Không tạo task theo từng cảm biến.

| Task | Chu kỳ | Việc được phép |
| --- | --- | --- |
| `vehicle` | 10 ms | Đọc công tắc, debounce, state machine, ghi gate và PWM |
| `sensors` | 50 ms | Mọi giao dịch I2C: INA228, BMI270, BH1750, VL53L1X |
| `gps` | theo byte UART | Đọc dòng NMEA, cập nhật tọa độ |
| NimBLE | do stack | Đọc snapshot, nhận lệnh viết |
| `console` | khi có dòng, hoặc theo `watch` | Đọc USB, in trạng thái. Không ghi GPIO |

`vehicle` không gọi I2C và không ghi NVS. `sensors` không ghi GPIO tải. Hai bên trao đổi qua `snapshot` và một queue lệnh tĩnh dài 4.

Mutex:

- `i2c_bus` — chỉ task `sensors` giữ khi đang giao dịch. Init cũng chạy trên task này sau khi tạo, trước vòng lặp.
- `snapshot` — người ghi là `sensors`, `gps`, `vehicle`. Người đọc là NimBLE.

Sau `app_main`, không cấp phát heap trên đường 10 ms của `vehicle`. Buffer NMEA (128 byte) và buffer BLE cấp một lần lúc init.

## 6.5 Thứ tự trong `app_main`

Giữ nguyên mục 4.8 của hợp đồng phần cứng:

1. `board_outputs_safe()` — ghi 0 vào GPIO6, GPIO7, GPIO10, GPIO11, GPIO12, GPIO13, GPIO41, rồi mới đặt output.
2. NVS và `bike_config_load()`.
3. Tạo task `sensors`. Task này mở I2C 100 kHz, quét đủ `0x40`, `0x23`, `0x29`, `0x68` khi `XSHUT` cao, ghi `SHUNT_CAL`, init BMI270, BH1750, VL53L1X.
4. Tạo task `gps`. UART 9600 8N1, RX GPIO17, TX GPIO18.
5. Tạo task `vehicle`, trạng thái đầu là `PARKING`.
6. Bật NimBLE.

Nếu quét I2C thiếu địa chỉ, `sensors` ghi lỗi vào snapshot và nháy `STATUS_LED`. Các gate vẫn thấp. Không reset vòng lặp để cố quét lại vô hạn trong `app_main`; task `sensors` thử lại mỗi 1 s.

`LIDAR_XSHUT` giữ thấp cho tới khi task `sensors` sẵn sàng đưa VL53L1X ra khỏi shutdown.

## 6.6 Nhận biết nguồn USB

PCB không có GPIO tách VBUS khỏi `+5V_SYS`. Sau diode, USB và nguồn xe đều để `+5V_SYS` khoảng 4.6–4.8 V. Firmware không kết luận “chỉ có USB” từ điện áp INA228.

Quy tắc V1: mọi gate tải mặc định tắt cho tới khi có lệnh `arm_outputs`. `vehicle` vẫn tính đèn, còi, xi-nhan; ống cổng ra giữ GPIO thấp khi chưa arm.

Cờ arm nằm trong RAM RTC, kèm magic và CRC. Chỉ khôi phục sau deep sleep khi CRC khớp. Cấp nguồn, nạp USB, watchdog và brownout đều bắt đầu với arm tắt. Bring-up bằng USB vì vậy không bật tải, đúng bước 7 của [05-bom-and-bringup.md](05-bom-and-bringup.md).

`INA228` vẫn đọc được trên USB. Snapshot vẫn báo điện áp bus để máy tính thấy mạch sống.

## 6.7 State machine

```
SLEEP
  │  GPIO38 (IMU_INT) đánh thức
  ▼
PARKING
  │  ride_start
  ▼
RIDING
  │  ride_stop, hoặc đứng yên quá stop_idle_s
  ▼
PARKING
  │  không chuyển động trong sleep_after_s
  ▼
SLEEP

PARKING
  │  chuyển động vượt ngưỡng
  ▼
ALARM
  │  hết alarm_s, hoặc lệnh dismiss
  ▼
PARKING
```

| Chuyển | Điều kiện mặc định | Khóa trong |
| --- | --- | --- |
| vào `RIDING` | Lệnh BLE `ride_start` | `config` |
| ra `RIDING` | Lệnh BLE `ride_stop`, hoặc IMU dưới ngưỡng liên tục `stop_idle_s` (180 s) | `config` |
| `PARKING` → `ALARM` | Gia tốc vượt `alarm_mg` trong `alarm_motion_ms` | `config` |
| `ALARM` → `PARKING` | Hết `alarm_s` (30 s), hoặc BLE `dismiss` | `config` |
| `PARKING` → `SLEEP` | Không vượt ngưỡng trong `sleep_after_s` (600 s) | `config` |
| `SLEEP` → `PARKING` | Wake ext0 trên GPIO38, mức cao | `imu.c` |

`RIDING` không đi thẳng vào `SLEEP`. Phải qua `PARKING`.

Hành vi từng trạng thái giữ bảng ở mục 4.7. LiDAR trong 4 m chỉ đặt cờ cảnh báo trong snapshot. Không có ngõ ra phanh tự động.

Trước khi vào deep sleep, `vehicle` kéo mọi gate xuống thấp, `sensors` kéo `LIDAR_XSHUT` thấp, BMI270 để INT1 ở chế độ chuyển động. `esp_sleep_enable_ext0_wakeup(GPIO38, 1)` rồi `esp_deep_sleep_start()`. Buck không bị tắt.

## 6.8 Công tắc và tải

Đọc công tắc mỗi 10 ms. Coi là nhấn khi thấp liên tục 30 ms, thả khi cao liên tục 30 ms. Hazard không có mẫu riêng: sau debounce, `hazard = left && right`.

| Tải | Cách ghi | Khi nào |
| --- | --- | --- |
| Đèn pha | LEDC, 1 kHz, 10 bit | Lux < 100 bật, lux > 200 tắt, giữa hai mức giữ nguyên. `LIGHT_SW` thấp thì ép bật |
| Đèn hậu | LEDC, cùng timer | Bật trong `RIDING` |
| Xi-nhan | LEDC, cùng timer | 1.25 Hz, 50%. Một phía, hoặc cả hai cùng pha khi hazard |
| Đèn phanh | GPIO cao/thấp | `BRAKE_SW` thấp và đang `RIDING` hoặc `PARKING` |
| Còi | GPIO cao/thấp | `HORN_SW` thấp thì gate cao ngay khi đã arm. Thả là thấp ngay |
| AUX | GPIO | Chỉ theo lệnh BLE `aux_set`. V1 không gán công tắc |
| `STATUS_LED` | GPIO | Theo mục 8.14: lỗi nguồn, rồi `ALARM`, rồi `RIDING`, rồi nhịp ngắn của `PARKING` |

Pha xi-nhan đếm trong task `vehicle` bằng `esp_timer_get_time()`. Không tạo timer LEDC nhấp nháy riêng, để hazard và rẽ dùng cùng một pha.

Còi và phanh không đưa vào LEDC. `horn` chỉ trả mức mong muốn. Ống cổng ra trong [08-control-algorithms.md](08-control-algorithms.md) mới áp arm, còi quá 30 s, luật dòng còi theo cờ xi-nhan đang được yêu cầu, cắt khi mất số đo nguồn, UVLO và quá dòng. Trần phần cứng vẫn là cầu chì 3 A.

## 6.9 Cảm biến

| Thiết bị | Driver | Ghi chú thực thi |
| --- | --- | --- |
| INA228 `0x40` | `ina228.c` tự viết | `ADCRANGE` = 0, `SHUNT_CAL` = 1250, `CURRENT_LSB` = 5/2^19. Đọc bus voltage, current, power, energy |
| BMI270 `0x68` | Bosch SensorAPI trong `third_party/bmi270` | Nạp init blob trước khi đọc. INT1 push-pull, active-high, map sang any-motion |
| BH1750 `0x23` | `light.c` tự viết | One-time H-resolution mỗi 500 ms là đủ cho trễ đèn. Task 50 ms chỉ hỏi chip khi tới hạn |
| VL53L1X `0x29` | ST ULD trong `third_party/vl53l1x` | Continuous, khoảng cách mm. Cờ `obstacle` khi khoảng cách hợp lệ và nhỏ hơn 4000 |
| MAX-M10S | `gps.c` tự viết | Không nằm trên I2C. Parse `RMC` và `GGA`. Baud trên 9600 chỉ sau khi module đã trả lời một câu |

GPS mất fix, sai checksum, hoặc ra 0,0 thì snapshot giữ tọa độ cuối và hạ cờ `gps_fix`. Quá 5 s không có câu hợp lệ thì hạ cờ, vẫn giữ tọa độ.

## 6.10 BLE

Một service vendor. Điện thoại là trung tâm, xe là ngoại vi. V1 không ghép nối bonding. Mọi opcode đã định nghĩa đều được nhận, đưa vào queue dài 4, và có hiệu lực ở nhịp 10 ms. Ghép nối và mã hóa lệnh là việc của bản sau; bản này không tắt ghi sau khi arm, vì nếu tắt thì không còn đường `ride_start`.

UUID 128-bit, base `6b690000-0000-4000-8000-00805f9b34fb`, hai byte giữa là số characteristic.

| Characteristic | Số | Thuộc tính | Nội dung |
| --- | --- | --- | --- |
| Snapshot | `0001` | Read, Notify | Gói cố định 32 byte, little-endian, bảng dưới |
| Command | `0002` | Write | 1 byte opcode |

Gói snapshot, offset tính bằng byte:

| Offset | Kiểu | Trường |
| --- | --- | --- |
| 0 | u8 | mode: 0 sleep không gửi, 1 parking, 2 riding, 3 alarm |
| 1 | u8 | cờ: bit0 fix GPS, bit1 obstacle, bit2 motion, bit3 outputs armed, bit4 bus I2C chết, bit5 fault_latch, bit6 tải đang bị cấm, bit7 motion_fault |
| 2 | u16 | lux |
| 4 | u16 | khoảng cách LiDAR, mm. `0xFFFF` là chưa có mẫu |
| 6 | i32 | vĩ độ, độ × 1e7 |
| 10 | i32 | kinh độ, độ × 1e7 |
| 14 | u16 | điện áp bus, mV |
| 16 | i16 | dòng, mA |
| 18 | i16 | công suất, 0.1 W |
| 20 | u32 | energy, mWh |
| 24 | u8 | đèn: bit0 pha, bit1 hậu, bit2 phanh, bit3 trái, bit4 phải, bit5 hazard, bit6 còi, bit7 aux |

Byte 25–31 để 0.

Opcode lệnh: `0x01` ride_start, `0x02` ride_stop, `0x03` arm_outputs, `0x04` disarm_outputs, `0x05` dismiss alarm, `0x06` aux on, `0x07` aux off. Byte khác bị bỏ.

Notify mỗi 500 ms khi có kết nối. Không notify trong deep sleep vì radio tắt.

## 6.11 Những gì không viết trong bản đầu

- Client OTA, dù partition đã chừa `ota_0` và `ota_1`.
- Wi-Fi station, MQTT, hay máy chủ.
- App điện thoại. Điện thoại thử bằng nRF Connect hoặc script Python trên máy có BLE, đọc đúng layout mục 6.10.
- Driver CAN, camera, màn hình.
- Phanh theo khoảng cách LiDAR.

## 6.12 Thứ tự viết

1. `board` và `app_main` bước 1: boot xong, mọi gate đo được 0 V, `STATUS_LED` chớp.
2. `i2c_bus` và log bốn địa chỉ.
3. `ina228` — điện áp bus khoảng 4.6–4.8 V trên USB.
4. `inputs` và `horn`/`brake`/`lighting`, vẫn disarmed, log trạng thái công tắc qua USB.
5. Bật tải và đo từng kênh bằng console USB trong [09-debug-commands.md](09-debug-commands.md), nguồn vào từ J1.
6. BMI270, BH1750, VL53L1X, GPS.
7. `power_mode` đủ bốn trạng thái, kể cả deep sleep và thức bằng GPIO38.
8. `ble_status` đúng layout 32 byte.

Mỗi bước phải chạy trên mạch trước khi viết bước sau. Checklist đủ điều kiện pass nằm ở [10-implementation-checklist.md](10-implementation-checklist.md). `firmware/tools/bringup_log.py` nói chuyện với mạch bằng đúng các dòng trong [09-debug-commands.md](09-debug-commands.md).
