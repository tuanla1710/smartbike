# 7. Kiến trúc phần mềm V1

Tài liệu này khóa cấu trúc phần mềm của Smart Bike Controller V1: hệ thống nhìn từ ngoài, các tầng, ba mặt phẳng lúc chạy, và dữ liệu được phép đi qua ranh giới nào. Cây file, ngôn ngữ và layout byte BLE nằm ở [06-software.md](06-software.md). Chân, địa chỉ và hành vi tải nằm ở [04-firmware.md](04-firmware.md).

## 7.1 Động lực kiến trúc

Các yêu cầu sau quyết định cấu trúc, không chỉ quyết định thuật toán.

| Nguồn | Ràng buộc | Hệ quả kiến trúc |
| --- | --- | --- |
| Một MCU, một bus I2C 100 kHz, bốn thiết bị | INA228, BMI270, BH1750, VL53L1X dùng chung SDA/SCL | Một chủ bus. Mọi giao dịch I2C nằm trong một task |
| Đèn, xi-nhan, phanh, còi là an toàn xe | Gate active-high, phải thấp trước khi thành output | Đường ghi tải tách khỏi đường đọc cảm biến, chu kỳ 10 ms, không chờ I2C |
| Hazard là hai diode, không có GPIO riêng | `HAZARD = LEFT ∧ RIGHT` sau debounce | Chính sách đèn đọc công tắc đã lọc, không đọc net `HAZARD_SW` |
| LiDAR khoảng 4 m | Cảnh báo, không có actuator phanh | Khoảng cách là dữ liệu xuất ra BLE, không có đường nối tới `BRAKE_GATE` |
| Không phân biệt được USB và nguồn xe bằng điện áp | Cả hai đều khoảng 4.6–4.8 V trên `+5V_SYS` | Cổng ra có chốt arm trong NVS. Chính sách vẫn tính tải; cổng ra mới quyết định có ghi GPIO hay không |
| Deep sleep, thức bằng `IMU_INT` | Buck luôn bật. `LIDAR_XSHUT` phải thấp trước khi ngủ | Ngủ là một giao dịch giữa hai task, có báo hoàn tất, rồi mới gọi deep sleep |
| Flash 8 MB, không PSRAM | OTA để sau | Bộ nhớ tĩnh sau init. Snapshot và hàng lệnh là struct cố định |
| Điện thoại chỉ nghe BLE | Không có app trong repo V1 | BLE là bộ thích ứng: đọc snapshot, ghi một opcode vào hàng lệnh |

## 7.2 Phong cách

Một tiến trình ESP-IDF. Ba mặt phẳng cùng chạy, trao đổi bằng một bảng đen (`snapshot`) và một hàng lệnh một ô.

Chính sách (đèn theo lux, xi-nhan, chuyển trạng thái) là hàm thuần: cùng đầu vào thì cùng đầu ra, không đụng GPIO, không đụng I2C. Driver và bộ thích ứng BLE nằm ngoài hàm đó.

```
                    người lái                 điện thoại
                    công tắc                  BLE central
                        │                         │
                        ▼                         ▼
                   ┌─────────┐              ┌──────────┐
                   │ inputs  │              │   link   │
                   └────┬────┘              └────┬─────┘
                        │                        │ lệnh 1 byte
                        ▼                        ▼
                   ┌─────────────────────────────────┐
                   │ vehicle: mode + chính sách      │
                   │ chu kỳ 10 ms                    │
                   └────────────┬────────────────────┘
                                │ actuation mong muốn
                                ▼
                   ┌─────────────────────────────────┐
                   │ cổng ra: arm ∧ giới hạn dòng    │
                   └────────────┬────────────────────┘
                                ▼
                          MOSFET / LEDC

        sensors (I2C, 50 ms) ──┐
        gps (UART) ────────────┼──▶ snapshot ◀── vehicle ghi mode, đèn
                               │         │
                               └─────────┴──▶ link đọc, notify 500 ms
```

Chiều phụ thuộc đi xuống: chính sách phụ thuộc kiểu dữ liệu, không phụ thuộc thanh ghi. Driver phụ thuộc `board`. `board` là nơi duy nhất biết số GPIO.

## 7.3 Ngữ cảnh

Phần mềm V1 nằm trọn trên ESP32-S3. Ngoài biên chỉ có năm đối tác.

| Đối tác | Hướng | Hợp đồng |
| --- | --- | --- |
| Tay lái | Vào | Sáu công tắc active-low. Hazard làm cả trái và phải thấp |
| Tải 5 V | Ra | Bảy gate active-high: pha, hậu, phanh, trái, phải, còi, AUX |
| Cảm biến trên PCB | Hai chiều | I2C bốn địa chỉ; UART GPS; `XSHUT` và `IMU_INT` |
| Điện thoại | Hai chiều | Đọc snapshot 32 byte, ghi opcode. Layout ở mục 6.10 |
| Máy tính qua USB | Vào firmware, ra log | Nạp và console. Bộ lệnh test nằm ở [09-debug-commands.md](09-debug-commands.md) |

Không có dịch vụ mạng, không có MCU thứ hai, không có đường điều khiển động cơ.

## 7.4 Tầng

| Tầng | Khối | Việc của tầng |
| --- | --- | --- |
| Thích ứng | `link` | NimBLE, đóng gói snapshot, mở opcode thành `command_t` |
| Ứng dụng | `power_mode`, `alarm` | Trạng thái xe và chuỗi báo động |
| Chính sách | `lighting`, `turn_signal`, `brake`, `horn`, `motion` | Đổi đầu vào đã lọc thành mức tải mong muốn |
| Điều phối | `vehicle` task, `inputs` | Nhịp 10 ms: đọc công tắc, gọi chính sách, gọi cổng ra |
| Tri giác | `sensors`, `gps`, driver INA228 / BMI270 / BH1750 / VL53L1X | Điền snapshot. Không ghi gate tải |
| Nền | `board`, `config`, `i2c_bus`, `snapshot` | Chân, NVS, mutex, bảng đen |
| Nền tảng | ESP-IDF, `third_party` | FreeRTOS, LEDC, UART, NimBLE, API Bosch, ULD ST |

Luật include:

| Khối | Được gọi | Không được gọi |
| --- | --- | --- |
| `lighting`, `turn_signal`, `brake`, `horn`, `motion`, `power_mode` | `bike_types.h`, `bike_config` ở dạng đã nạp | GPIO, I2C, NimBLE, `esp_deep_sleep_start` |
| `vehicle` task | Chính sách, `inputs`, `board` cổng ra, hàng lệnh | Thanh ghi INA228, API Bosch, GATT |
| `sensors`, `gps` | Driver, `i2c_bus`, `board` cho `XSHUT` | `LEDC`, gate tải, NimBLE |
| `link` | `snapshot_read`, hàng lệnh | I2C, GPIO tải, chuyển trạng thái trực tiếp |
| `board` | ESP-IDF GPIO và LEDC | Chính sách đèn, biết lux hay mode |
| `ina228`, `imu`, `light`, `lidar` | `i2c_bus` | Biết xe đang `RIDING` hay không |

`power_mode` trả trạng thái mới. Nó không tự ghi đèn báo động. `alarm` trả một `actuation_t` khi mode là `ALARM`. Task `vehicle` chọn một trong hai: chính sách chạy xe, hoặc chính sách báo động, rồi đưa qua cổng ra.

## 7.5 Ba mặt phẳng

| Mặt phẳng | Task | Chu kỳ | Sở hữu |
| --- | --- | --- | --- |
| Chấp hành | `vehicle` | 10 ms | Công tắc, mode, chính sách, GPIO tải, LED trạng thái, vào deep sleep |
| Tri giác | `sensors` và `gps` | 50 ms và theo byte UART | I2C, `XSHUT`, mẫu IMU, lux, khoảng cách, điện, tọa độ |
| Công bố | NimBLE | Notify 500 ms khi có kết nối | Đọc snapshot, ghi hàng lệnh |

Callback BLE chạy trên task của stack. Callback đó đẩy một opcode vào queue tĩnh dài 4, timeout 0, rồi trả về. Hàng đầy thì bỏ lệnh mới. Đổi mode và ghi GPIO xảy ra ở nhịp 10 ms của `vehicle`. Cờ arm ghi RAM RTC trên nhịp đó, không ghi NVS.

Mỗi nhóm trường snapshot có một người ghi.

| Trường | Người ghi |
| --- | --- |
| `mode`, bit đèn, `outputs_armed` | `vehicle` |
| lux, khoảng cách, `obstacle`, `motion`, điện áp, dòng, công suất, energy, cờ hợp lệ của từng mẫu | `sensors` |
| vĩ độ, kinh độ, `gps_fix` | `gps` |
| queue lệnh | `link` đẩy, `vehicle` lấy một lệnh mỗi nhịp |

Mutex `snapshot` chỉ được giữ để chép struct. Mutex `i2c_bus` chỉ task `sensors` lấy.

## 7.6 Hợp đồng dữ liệu

Các struct này là ranh giới kiến trúc. Layout 32 byte trên BLE là phép chiếu từ `snapshot_t`, làm trong `link`, không làm trong chính sách.

```c
typedef enum {
    BIKE_PARKING = 1,
    BIKE_RIDING  = 2,
    BIKE_ALARM   = 3
} bike_mode_t;

typedef struct {
    bool left, right, hazard, horn, light, brake;
} bike_inputs_t;

typedef struct {
    uint16_t lux;
    uint16_t range_mm;      /* 0xFFFF: chưa có mẫu hoặc mẫu hết hạn */
    bool obstacle;          /* mẫu hợp lệ và range_mm < 4000 */
    bool motion;
    bool motion_fault;
    bool lux_valid;
    bool range_valid;
    bool power_valid;
    bool gps_fix;
    int32_t lat_e7, lon_e7; /* lần fix cuối, giữ nguyên khi mất fix */
    uint16_t bus_mv;
    int16_t current_ma;
    int16_t power_dw;       /* 0.1 W */
    uint32_t energy_mwh;
} perception_t;

typedef struct {
    uint16_t head, tail, left, right; /* duty LEDC 0..1023 */
    bool left_lit, right_lit;         /* yêu cầu xi-nhan, kể cả nửa kỳ duty 0 */
    bool brake, horn, aux;
    bool horn_from_alarm;
} actuation_t;

typedef enum {
    CMD_NONE = 0,
    CMD_RIDE_START,
    CMD_RIDE_STOP,
    CMD_ARM,
    CMD_DISARM,
    CMD_DISMISS,
    CMD_AUX_ON,
    CMD_AUX_OFF
} command_t;
```

`bike_mode_t` không có giá trị `SLEEP`. Khi điều kiện ngủ đúng, `vehicle` thực hiện giao dịch ngủ rồi gọi deep sleep. Sau khi thức, `app_main` chạy lại và vào `PARKING`.

Hàm chính sách, cùng chữ ký:

```c
typedef struct {
    bike_mode_t mode;
    bool request_sleep;
} mode_step_result_t;

mode_step_result_t power_mode_step(bike_mode_t mode, command_t cmd,
                                   const perception_t *p, uint32_t now_ms);

actuation_t ride_policy(bike_mode_t mode, const bike_inputs_t *in,
                        const perception_t *p);

actuation_t alarm_policy(uint32_t now_ms);
```

`ride_policy` gộp đèn, xi-nhan, phanh, còi theo mục 4.5 và 4.6. `alarm_policy` thay toàn bộ `actuation_t` khi mode là `ALARM`: nháy đèn và còi theo chu kỳ trong `config`.

Cổng ra:

```c
void outputs_apply(const actuation_t *want);
```

`outputs_apply` nằm trong `board` và là ống cổng ra ở mục 8.12. Thứ tự chốt: luật dòng còi theo `left_lit`/`right_lit`, rồi đến arm, `fault_latch`, mất số đo nguồn, UVLO và quá dòng. Còi báo động không bị luật `horn_current_ma` xóa. `STATUS_LED` không đi qua ống này.

## 7.7 Nhịp 10 ms

Một vòng của task `vehicle`:

1. `inputs_sample()` — debounce 30 ms theo `now_ms`, rồi `hazard = left && right`.
2. `command_take()` — lấy tối đa một lệnh từ queue dài 4.
3. `perception_peek()` — bản sao snapshot, không giữ mutex qua bước sau.
4. Xử lý `ARM`, `DISARM`, `AUX`. Rồi `power_mode_step`.
5. Nếu kết quả xin ngủ, chạy giao dịch mục 7.8 rồi không gọi chính sách đèn.
6. `want = (mode == ALARM) ? alarm_policy : ride_policy`, rồi gắn `aux_latch`.
7. `outputs_apply(&want)` theo ống cổng ra.
8. Ghi `mode`, bit đèn và cờ arm vào snapshot.
9. `STATUS_LED` theo mục 8.14. Cuối vòng xoa failsafe 50 ms và watchdog.

`obstacle` không xuất hiện trong `ride_policy`. Nó chỉ nằm trong snapshot để BLE công bố. Từng thuật toán của vòng này nằm ở [08-control-algorithms.md](08-control-algorithms.md).

## 7.8 Giao dịch ngủ

`power_mode_step` báo cần ngủ khi đang `PARKING`, IMU dưới ngưỡng suốt `sleep_after_s`, và `GPIO38` đang thấp. Task `vehicle` khi đó chạy giao dịch mục 8.15: kéo gate thấp, chờ `XSHUT` theo lát 10 ms, hủy nếu có lệnh hoặc có chuyển động, rồi mới deep sleep.

Hết hạn 200 ms mà `sensors` chưa xác nhận thì `vehicle` tự kéo `XSHUT` thấp rồi vẫn ngủ. Trong lúc chờ, task này không giữ mutex.

Thức dậy khởi động lại từ `app_main`. Trạng thái đầu vẫn là `PARKING`. Cờ `outputs_armed` chỉ còn khi lý do reset là deep sleep và CRC trong RAM RTC khớp.

`RIDING` về `PARKING` trước đã. Từ `RIDING` không gọi deep sleep.

## 7.9 Xuống cấp

| Sự cố | Hành vi kiến trúc |
| --- | --- |
| Thiếu địa chỉ I2C lúc quét | Bus được phục hồi tối đa một lần mỗi giây, rồi thử lại. Mất số đo nguồn quá 200 ms thì cấm tải |
| Một thiết bị I2C lỗi giữa chừng | Mỗi mẫu có hạn riêng. Lux hết hạn thì giữ `head_on`. Khoảng cách hết hạn thì xóa `obstacle`. Nguồn hết hạn thì cấm tải |
| Mất fix GPS, checksum sai, hoặc 0,0 | `gps_fix = false`, giữ tọa độ cuối |
| Hàng lệnh đầy | Bỏ lệnh mới, giữ lệnh chưa xử lý, tăng `cmd_dropped` |
| Chưa arm, UVLO, quá dòng, hoặc `fault_latch` | Chính sách vẫn chạy. GPIO tải giữ thấp |
| Task `vehicle` không hoàn thành vòng trong 50 ms | Failsafe kéo gate thấp. Watchdog reset thì arm tắt |

## 7.10 Quyết định đã khóa

| ID | Quyết định |
| --- | --- |
| KT1 | Chính sách thuần, cổng ra có chốt. Arm và giới hạn dòng còi không nằm trong `lighting` hay `horn` |
| KT2 | Một chủ I2C. Bốn cảm biến không có task riêng |
| KT3 | BLE không đổi mode trong callback. Mọi lệnh đi qua ô `command_t` và có hiệu lực ở nhịp 10 ms |
| KT4 | `obstacle` là dữ liệu công bố. Không có phụ thuộc từ LiDAR tới `brake` |
| KT5 | Alarm chỉ đi từ `PARKING`. Chuyển động lúc `RIDING` là đi xe |
| KT6 | Ngủ là giao dịch có xác nhận `XSHUT`, thực hiện trên task `vehicle` |
| KT7 | Số GPIO chỉ có trong `board`. Thanh ghi INA228 chỉ có trong `ina228.c`. Layout BLE chỉ có trong `link` |
| KT8 | Nhịp 10 ms không ghi NVS, không chờ I2C. Arm nằm trong RAM RTC và chỉ sống qua deep sleep khi CRC khớp |
| KT9 | Mất số đo nguồn, quá dòng, UVLO lặp, hoặc failsafe thì gate về thấp. Luật này nằm trong ống cổng ra, sau chính sách |

## 7.11 Ánh xạ sang source

| Tầng trong tài liệu này | Component trong [06-software.md](06-software.md) |
| --- | --- |
| Nền chân và cổng ra | `components/board` |
| Nền cấu hình | `components/config` |
| Tri giác | `components/sensors`, `components/power/ina228.c` |
| Chính sách và điều phối | `components/vehicle`, `components/power/power_mode.c` |
| Báo động | `components/security` |
| Công bố | `components/link` |
| Kiểu dùng chung (`bike_types.h`) | `components/link/include` cho snapshot; kiểu đầu vào và actuation đặt ở `components/vehicle/include` nếu `link` chỉ cần bản đã đóng gói |

`app_main` tạo task theo mục 6.5 rồi trả về. Nó không chứa chính sách.
