# 1. Kiến trúc V1

## 1.1 Mục tiêu

PCB này là bộ điều khiển xe đạp điện V5. Nó lấy duy nhất 5 V từ nguồn ngoài, đo điện áp / dòng / công suất, nuôi ESP32-S3 ở 3.3 V, và đóng các tải 5 V bằng MOSFET kéo xuống mass.

Tải V1:

- đèn pha
- đèn hậu
- đèn phanh
- xi-nhan trái, xi-nhan phải, hazard
- còi
- một kênh AUX

Cảm biến V1:

- GPS để biết vị trí
- LiDAR phía trước, khoảng 4 m, để cảnh báo vật cản
- IMU để chống trộm, phát hiện chuyển động, ngã, va chạm, và đánh thức MCU
- cảm biến ánh sáng để bật đèn pha tự động

Người lái nói chuyện với xe qua công tắc tay lái và Bluetooth. USB-C dùng để nạp firmware và, khi chưa cắm nguồn xe, nuôi mạch ở mức dòng USB mặc định.

## 1.2 Phạm vi không làm trên PCB này

- Không đưa 48 V, pin xe, hay stage công suất động cơ vào PCB.
- Không dùng relay.
- Không thêm Arduino, STM32, hay MCU thứ hai.
- Không thêm 5G, CAN, camera, màn hình, hay sạc pin.
- Không tắt buck bằng GPIO. Ngủ của V1 là deep sleep của ESP32.

## 1.3 Sơ đồ khối nguồn

```
J1 +5V_IN
    │
    F1 3A
    │
    Q1  DMG2305UX          chống đảo cực
    │
    D2  SMAJ5.0A           TVS xuống GND
    │
    +5V_PROT
    │
    D3  SS54               chặn dòng chảy ngược ra J1
    │
    └──────────┬─────────── D4 SS34 ← F2 ← USB VBUS
               │
           +5V_MERGED
               │
           R2 10 mΩ        INA228 đo qua shunt
               │
           +5V_SYS
               │
     ┌─────────┼─────────┬──────────────┐
     │         │         │              │
   đèn       còi       AUX         U2 TPS62162-Q1
 (low-side) (low-side) (low-side)       │
                                         +3V3
                                         │
                              ESP32, cảm biến, GPS, USB I/O
```

Nhánh `5V LIGHTS`, `5V HORN`, `5V AUX` trong sơ đồ khối ban đầu là các MOSFET low-side từng kênh. Không thêm MOSFET high-side theo nhóm.

## 1.4 Sơ đồ khối tín hiệu

```
                         ESP32-S3-WROOM-1
                                │
           ┌────────────────────┼────────────────────┐
           │                    │                    │
         I2C                  UART                 GPIO
           │                    │                    │
     GPIO8 SDA            GPIO17 ← GPS TXD      đèn / còi / AUX
     GPIO9 SCL            GPIO18 → GPS RXD      công tắc tay lái
           │                                      IMU INT, LiDAR
     INA228  0x40
     BMI270  0x68
     BH1750  0x23
     VL53L1X 0x29
```

## 1.5 Quyết định đã khóa

| ID | Quyết định |
| --- | --- |
| QĐ1 | USB VBUS và nguồn J1 gặp nhau sau hai diode Schottky. `Q1` có source phía cầu chì và drain phía `+5V_PROT`. Khi USB kéo `+5V_PROT` lên, diode thân dẫn ngược về J1 và kênh cũng mở vì gate vẫn ở mass. `D3` nằm sau `Q1` để chặn đường đó. |
| QĐ2 | Shunt của INA228 nằm sau điểm cộng nguồn, trên đường vào `+5V_SYS`. Số đo là dòng thực sự nuôi đèn, còi, AUX và buck. |
| QĐ3 | `HAZARD_SW` không có GPIO riêng. Hai diode kéo `LEFT_SW` và `RIGHT_SW` xuống thấp khi bấm hazard. Firmware hiểu hazard khi cả hai chân cùng thấp. |
| QĐ4 | Sáu kênh đèn và AUX dùng `Si2302CDS`. Kênh còi có hai footprint loại trừ nhau. Chỉ hàn một cái sau khi đo dòng còi. |
| QĐ5 | Mỗi kênh tải có diode hồi tiếp. Còi là tải cảm, và dây đèn trên xe đủ dài để tạo xung áp. |
| QĐ6 | LiDAR là module VL53L1X hàn qua header, không phải die trần. |
| QĐ7 | Module MCU là `ESP32-S3-WROOM-1-N8`: flash 8 MB, không PSRAM octal. Đủ chỗ cho OTA hai phân vùng. GPIO35–37 không bị PSRAM chiếm, và V1 cũng không dùng chúng. |
| QĐ8 | Buck luôn bật khi có `+5V_SYS`. `EN` nối thẳng rail 5 V. |
| QĐ9 | I2C V1 chạy 100 kHz. |
| QĐ10 | `V_BCKP` của GPS nối 3.3 V. V1 không có pin backup; mất nguồn là mất hot start. |

## 1.6 Ngân sách dòng

Cầu chì `F1` là trần cứng: **3 A** trên đường nguồn xe.

| Nhánh | Trần dùng khi thiết kế |
| --- | --- |
| Toàn bộ `+5V_SYS` | 2.5 A liên tục, để cầu chì 3 A còn dư |
| Mỗi kênh `Si2302CDS` | 1 A liên tục |
| Còi | Chưa biết. Nếu một mình còi đã trên 3 A thì V1 không kéo được; phải đổi cầu chì, shunt, connector và MOSFET |
| USB | CC 5.1 kΩ khai báo thiết bị USB mặc định. Firmware và cảm biến chạy được trên USB. Đèn và còi không được bật khi chỉ có USB |
| `+3V3` | TPS62162-Q1 cấp tối đa 1 A. Đỉnh Wi-Fi của ESP32-S3 nằm trong trần này nếu GPS và LiDAR đang ở dòng bình thường |

Ước lượng 3.3 V khi đang chạy: ESP32 khoảng vài trăm mA lúc phát Wi-Fi, GPS khoảng 30 mA, module VL53L1X vài chục mA, BMI270 / BH1750 / INA228 dưới 2 mA cộng lại.

## 1.7 Ngủ và đánh thức

`U2` không bị cắt điện. Dòng tĩnh của buck khoảng 17 µA, cộng thêm cảm biến nếu firmware không đưa chúng vào standby.

| Mode | Phần cứng |
| --- | --- |
| SLEEP | ESP32 deep sleep. VL53L1X bị kéo `XSHUT` thấp. GPS để firmware đưa vào backup software nếu cần. BMI270 giữ một ngắt chuyển động |
| PARKING / ALARM / RIDING | ESP32 chạy. Chi tiết trạng thái nằm ở tài liệu firmware |

Nguồn đánh thức V1 là `GPIO38` (`IMU_INT`). Không có chân nguồn riêng để bật buck.

## 1.8 Bản đồ GPIO đã chốt

| GPIO | Net | Hướng | Chức năng |
| --- | --- | --- | --- |
| GPIO4 | `LIDAR_XSHUT` | ra | Reset / shutdown VL53L1X, active-low ở phía sensor |
| GPIO5 | `LIDAR_INT` | vào | Ngắt VL53L1X, open-drain, có pull-up |
| GPIO6 | `HORN_GATE` | ra | Cổng MOSFET còi |
| GPIO7 | `HEADLIGHT_GATE` | ra | Cổng MOSFET đèn pha |
| GPIO8 | `I2C_SDA` | hai chiều | I2C data |
| GPIO9 | `I2C_SCL` | ra | I2C clock |
| GPIO10 | `LEFT_GATE` | ra | Xi-nhan trái |
| GPIO11 | `RIGHT_GATE` | ra | Xi-nhan phải |
| GPIO12 | `TAIL_GATE` | ra | Đèn hậu |
| GPIO13 | `BRAKE_GATE` | ra | Đèn phanh |
| GPIO15 | `LEFT_SW` | vào | Công tắc trái, active-low |
| GPIO16 | `RIGHT_SW` | vào | Công tắc phải, active-low |
| GPIO17 | `GPS_TXD` | vào | UART RX của ESP32, nối TXD của MAX-M10S |
| GPIO18 | `GPS_RXD` | ra | UART TX của ESP32, nối RXD của MAX-M10S |
| GPIO19 | `USB_D_N` | USB | D− |
| GPIO20 | `USB_D_P` | USB | D+ |
| GPIO21 | `HORN_SW` | vào | Công tắc còi, active-low |
| GPIO38 | `IMU_INT` | vào | BMI270 INT1, đánh thức |
| GPIO39 | `LIGHT_SW` | vào | Công tắc đèn, active-low |
| GPIO40 | `BRAKE_SW` | vào | Công tắc phanh, active-low |
| GPIO41 | `AUX_GATE` | ra | Cổng MOSFET AUX |
| GPIO42 | `STATUS_LED` | ra | LED trạng thái trên PCB, active-high |

`GPIO0` chỉ phục vụ nút BOOT trên PCB, pull-up 10 kΩ. Không phải chức năng xe.

Các chân không dùng, để hở: `GPIO1`, `GPIO2`, `GPIO3`, `GPIO14`, `GPIO35`, `GPIO36`, `GPIO37`, `GPIO43`, `GPIO44`, `GPIO45`, `GPIO46`, `GPIO47`, `GPIO48`.

`GPIO0`, `GPIO3`, `GPIO45`, `GPIO46` là chân strapping. `GPIO45` và `GPIO46` có pull-down yếu bên trong và phải được thả nổi. `GPIO3` thả nổi. Không kéo `GPIO45` lên cao.
