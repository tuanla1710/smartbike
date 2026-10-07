# 4. Firmware V1 — hợp đồng với PCB

Firmware nằm ở `firmware/`. Phần này khóa những gì firmware phải giả định đúng với PCB V1. Ngôn ngữ, cây ESP-IDF, task và hợp đồng BLE nằm ở [06-software.md](06-software.md).

## 4.1 Cây module

Các khối dưới đây là ranh giới module, không phải cây file. Cây file thật nằm ở [06-software.md](06-software.md).

```
smartbike/
├── main/
├── power/
│   ├── power_monitor      INA228
│   └── power_modes        sleep / parking / riding
├── sensors/
│   ├── gps                MAX-M10S, UART
│   ├── lidar              VL53L1X
│   ├── imu                BMI270
│   └── light              BH1750
├── vehicle/
│   ├── lighting           pha, hậu, PWM
│   ├── turn_signal        trái, phải, hazard
│   ├── brake
│   └── horn
├── security/
│   ├── anti_theft
│   └── motion_detect
├── bluetooth/
├── usb/
└── config/
```

## 4.2 Chân và mức tích cực

Tất cả công tắc tay lái là **active-low**, có pull-up trên PCB. Firmware bật pull-up nội bộ là tùy chọn, không bắt buộc.

Tất cả gate MOSFET là **active-high**. Mức thấp nghĩa là tải tắt. Trong `app_main`, trước khi cấu hình thành output, ghi 0 cho GPIO6, GPIO7, GPIO10, GPIO11, GPIO12, GPIO13, GPIO41.

`STATUS_LED` (GPIO42) active-high.

`LIDAR_XSHUT` (GPIO4): mức cao cho sensor chạy, mức thấp để shutdown. Pull-up 10 kΩ trên PCB nên nếu GPIO thả nổi thì sensor bật. Lúc vào sleep, firmware phải chủ động kéo thấp.

`IMU_INT` (GPIO38) là nguồn đánh thức deep sleep.

UART GPS, bắt buộc gán qua GPIO matrix:

| Tín hiệu ESP32 | GPIO | Nối tới |
| --- | --- | --- |
| UART RX | GPIO17 | MAX-M10S TXD |
| UART TX | GPIO18 | MAX-M10S RXD |

Không dùng mapping mặc định UART1 của module, vì mapping đó đảo chiều so với bảng này.

USB để nguyên GPIO19 = D−, GPIO20 = D+.

## 4.3 Bus

| Bus | Cấu hình V1 |
| --- | --- |
| I2C | GPIO8 SDA, GPIO9 SCL, 100 kHz |
| UART GPS | 9600 8N1 lúc mở cổng. Baud cao hơn chỉ sau khi module đã trả lời |

| Thiết bị | Địa chỉ 7-bit |
| --- | --- |
| INA228 | 0x40 |
| BH1750 | 0x23 |
| VL53L1X | 0x29 |
| BMI270 | 0x68 |

Quét I2C lúc bring-up phải thấy đủ bốn địa chỉ khi `XSHUT` đang cao. GPS không xuất hiện trên bus này.

BMI270 cần nạp init blob của Bosch trước khi đọc số liệu.

## 4.4 INA228

| Tham số | Giá trị V1 |
| --- | --- |
| Rshunt | 0.010 Ω |
| Dòng lớn nhất dùng để tính `CURRENT_LSB` | 5.0 A |
| `CURRENT_LSB` | 5 / 2^19 = 9.536743164 µA |
| `SHUNT_CAL` | 1250 |
| `ADCRANGE` | 0, thang vi sai ±163.84 mV |

Công thức TI: `SHUNT_CAL = 13107.2e6 × CURRENT_LSB × Rshunt`. Với hai số trên, kết quả đúng bằng 1250.

`ALERT` không nối GPIO. Đọc voltage, current, power, energy bằng I2C. Energy dùng cho màn hình điện thoại qua BLE.

Nếu shunt thực tế không phải 10 mΩ 1%, đo lại và sửa `SHUNT_CAL`. Không hard-code bù trong nhiều file; để một hằng trong `config`.

## 4.5 Đèn

| Việc | Hành vi V1 |
| --- | --- |
| Đèn hậu | Bật khi trạng thái là RIDING |
| Đèn phanh | Bật khi `BRAKE_SW` thấp |
| Đèn pha tự động | Lux dưới 100 thì bật. Lux trên 200 thì tắt. Trong khoảng 100–200 giữ nguyên trạng thái |
| `LIGHT_SW` thấp | Ép đèn pha bật, bỏ qua lux |
| `LIGHT_SW` cao | Trở lại chế độ lux |
| Độ sáng | PWM LEDC 1 kHz, 10 bit, trên các chân đèn. Còi và phanh không PWM ở V1 |
| Xi-nhan | Nhấp nháy 1.25 Hz, duty 50%, khi đúng một trong hai công tắc trái/phải đang thấp |
| Hazard | Khi cả `LEFT_SW` và `RIGHT_SW` cùng thấp. Không đọc chân hazard riêng. Hai bên nháy cùng pha |

Hazard bằng phần cứng diode nên firmware chỉ cần quy tắc `HAZARD = LEFT + RIGHT`.

## 4.6 Còi

`HORN_SW` thấp thì `HORN_GATE` cao. Thả công tắc thì gate thấp ngay.

V1 không PWM còi. Nếu dòng còi chưa được ghi vào `config`, firmware không bật còi cùng lúc với toàn bộ đèn. Trần phần cứng là cầu chì 3 A. Giới hạn thời gian giữ còi, cắt khi mất số đo dòng hoặc quá dòng, và cách tính “đang bật” của xi-nhan nằm ở [08-control-algorithms.md](08-control-algorithms.md). Mức tích cực của gate không đổi.

## 4.7 State machine

```
SLEEP
  │  IMU_INT
  ▼
PARKING
  │  người dùng bắt đầu chạy (BLE hoặc điều kiện start trong config)
  ▼
RIDING
  │  dừng
  ▼
PARKING
  │  chuyển động đáng ngờ
  ▼
ALARM
```

| Trạng thái | Việc nhìn thấy được |
| --- | --- |
| SLEEP | Gate đều thấp. `LIDAR_XSHUT` thấp. ESP32 deep sleep, wake trên GPIO38 |
| PARKING | Đèn pha theo lux hoặc theo `LIGHT_SW`. IMU theo dõi. GPS có thể giữ fix chậm |
| RIDING | Đèn hậu bật. Phanh, xi-nhan, còi theo công tắc. LiDAR cảnh báo. GPS cập nhật |
| ALARM | Nháy đèn, bật còi theo chu kỳ, gửi vị trí GPS và sự kiện qua BLE |

Ngưỡng “chuyển động đáng ngờ”, thời gian còi báo động, và cách xác nhận start/stop để trong `config`, không rải trong từng module. Điều kiện biên của từng chuyển trạng thái, khoảng nghỉ giữa hai lần báo động, và hủy ngủ khi có chuyển động mới nằm ở [08-control-algorithms.md](08-control-algorithms.md).

LiDAR khoảng 4 m là cảnh báo, không phải phanh tự động. V1 không có actuator phanh.

BLE V1 mang: trạng thái xe, lux, khoảng cách LiDAR, cờ IMU, tọa độ GPS, và số đọc INA228 (V, I, P, energy). OTA là việc sau, flash 8 MB đã chừa chỗ; bootloader OTA không bắt buộc phải xong trong bản firmware đầu tiên lên mạch.

## 4.8 Thứ tự bật

1. Mọi gate ghi 0, cấu hình output.
2. I2C 100 kHz, quét bus.
3. INA228: ghi `SHUNT_CAL`, kiểm tra điện áp bus khoảng 5 V (hoặc khoảng 4.6 V nếu đang nuôi bằng USB).
4. BMI270 init, bật ngắt chuyển động trên INT1.
5. BH1750, VL53L1X (`XSHUT` cao), UART GPS.
6. Vào PARKING. Chỉ vào RIDING sau điều kiện start.

Nếu chỉ có USB, bước 6 vẫn chạy nhưng các gate đèn và còi giữ thấp.
