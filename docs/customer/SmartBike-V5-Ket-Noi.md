# Smart Bike Controller V1 — Đặc tả kết nối

Tài liệu này dành cho người tích hợp dây, xưởng in mạch và kỹ sư kiểm tra bản **PCB Smart Bike Controller V1**. Bản mạch là 70.00 × 50.00 mm, 4 lớp, dày 1.6 mm, đồng 1 oz. Nguồn vào PCB chỉ có 5 V. Điện 48 V của xe không được đưa vào bất kỳ chân nào trên tấm này.

Ngày phát hành hồ sơ: 2026-10-07. Mã tài liệu: SB-V5-CON-001.

## 1. Hồ sơ để xem và để in

| Việc | File |
| --- | --- |
| Mở thiết kế | `hardware/kicad/kicad.sh` |
| Sơ đồ nguyên lý | `hardware/kicad/smartbike_v5/smartbike_v5.kicad_sch` |
| PCB | `hardware/kicad/smartbike_v5/smartbike_v5.kicad_pcb` |
| PDF sơ đồ nguyên lý | `hardware/kicad/smartbike_v5/fab/schematic.pdf` |
| PDF mạch, tỷ lệ 1:1 trên trang A4 | `hardware/kicad/smartbike_v5/fab/pcb-1to1.pdf` |

ERC của sơ đồ: **0 lỗi, 0 cảnh báo**. DRC đồng: **0 lỗi**, **0 lỗi footprint**. Viền courtyard không chồng lên nhau.

Khi in `pcb-1to1.pdf`, chọn tỷ lệ **100% / Actual size**. Viền mạch trên trang là **70.00 × 50.00 mm**. Sau khi in, đo cạnh ngoài bằng thước.

Còn **71 mối nối chưa khép** trên PCB: `GND` 49, `+3V3` 10, `+5V_SYS` 9, `EN` 2, `BOOT` 1. Vì vậy hồ sơ này chưa kèm gerber. Bản PDF dùng để kiểm tra kích thước và vị trí linh kiện. Đặt mạch sản xuất sau khi 71 mối đó được nối và DRC báo 0 mục chưa nối.

Nhìn từ mặt linh kiện, gốc tọa độ ở góc dưới-trái. Cạnh trước xe là cạnh trên (y = 50 mm): module LiDAR nhìn ra phía đó. Cạnh sau là cạnh dưới (y = 0): hàng giắc tải và USB-C. Anten của module ESP32 hướng ra cạnh phải. Anten GPS nằm phía trước-trái.

Silk mặt trên có dòng `SMART BIKE V5  PCB V1  5V ONLY`.

## 2. Quy ước chân

Mọi giắc ngoài là JST-XH, đực, cắm đứng trên mặt top. **Chân 1 là chân có dấu trên silk** (dấu chấm hoặc pad được đánh dấu của footprint). Đếm dọc theo hàng chân, từ chân 1 đến chân cuối.

Công tắc tay lái là **active low**: nhấn thì nối chân tín hiệu xuống GND. Mỗi ngõ có điện trở kéo lên 10 kΩ về 3.3 V và tụ 100 nF xuống GND trên PCB. Không cấp 5 V vào các chân công tắc.

Tải đèn, còi và AUX là **low-side**. PCB cấp `+5V_SYS` ra một chân của giắc. Chân còn lại về cực drain của MOSFET. Tải nằm giữa hai chân đó. Không nối cực âm của tải thẳng xuống khung xe nếu cực âm đó phải về chân `*_N` của PCB.

## 3. Nguồn

Hai nguồn được diode-OR. Nguồn nào cao hơn thì nuôi mạch. Schottky làm điện áp tải thấp hơn điện áp đầu vào khoảng 0.2–0.4 V.

| Nguồn | Đường vào | Cầu chì | Điôt OR |
| --- | --- | --- | --- |
| Nguồn xe | J1 chân 1, `+5V_IN` | F1, 3 A, một lần | D3 SS54 |
| USB-C | J8 VBUS | F2, PTC giữ 1.1 A | D4 SS34 |

Sau điểm OR là shunt 10 mΩ (R2) và cảm biến INA228. Rail tải tên là `+5V_SYS`. Buck TPS62162-Q1 tạo `+3V3` cho ESP32, cảm biến và GPS. Buck luôn bật khi có 5 V.

Giới hạn dùng khi thiết kế dây:

| Hạng mục | Giá trị |
| --- | --- |
| Điện áp danh định J1 | 5 V. Không đưa 48 V vào J1 |
| Trần dòng của F1 | 3 A. Đây là trần cứng của cả tấm |
| Dòng USB | mức mặc định của cổng USB, vì CC1/CC2 kéo 5.1 kΩ. USB không dùng để nuôi đèn và còi |
| Điện áp trên tải | khoảng 4.6–4.8 V khi nguồn vào là 5 V |
| Kênh đèn và AUX | Si2302CDS, chỉ lắp khi dòng liên tục của kênh dưới 1 A |
| Kênh còi | Q8A và Q8B đều để trống cho tới khi đo được dòng còi. Chỉ hàn một trong hai |

Q1 (DMG2305UX) chống đảo cực ở ngõ J1. Cắm ngược J1 thì mạch không được cấp nguồn. USB không bị nguồn xe đẩy ngược, và J1 không bị USB đẩy ngược.

## 4. Giắc nguồn và USB

### J1 — POWER, JST-XH 2 chân

| Chân | Tín hiệu | Hướng | Ghi chú |
| --- | --- | --- | --- |
| 1 | `+5V_IN` | vào | 5 V từ nguồn xe, sau cầu chì xe nếu có |
| 2 | GND | — | Mass nguồn. Nối về mass của nguồn 5 V |

### J8 — USB-C 16 chân

Dùng để nạp firmware và để nuôi mạch khi chưa cắm J1. D+/D− vào USBLC6-2SC6 rồi qua 22 Ω tới USB Serial/JTAG của ESP32-S3.

| Chân USB-C | Mạng |
| --- | --- |
| A6, B6 | D+ |
| A7, B7 | D− |
| A5 | CC1, 5.1 kΩ xuống GND |
| B5 | CC2, 5.1 kΩ xuống GND |
| A4, A9, B4, B9, vỏ | GND |
| A1, A12, B1, B12 | không dùng |
| VBUS | qua F2 và D4 |

Nếu cổng không vào chế độ nạp: giữ SW2 (BOOT) rồi nhấn SW1 (RESET).

## 5. Giắc tải

Tất cả chân `+5V_SYS` nối chung rail sau shunt. Chân `*_N` là cực kéo xuống mass, không phải mass lúc MOSFET tắt.

### J3 — HEADLIGHT, đèn pha, 2 chân

| Chân | Tín hiệu | GPIO điều khiển |
| --- | --- | --- |
| 1 | `+5V_SYS` | — |
| 2 | `HEADLIGHT_N` | GPIO7, qua R18 100 Ω tới Q2 |

### J4 — REAR, đèn hậu và đèn phanh, 3 chân

| Chân | Tín hiệu | GPIO |
| --- | --- | --- |
| 1 | `+5V_SYS` | — |
| 2 | `TAIL_N` | GPIO12, Q3 |
| 3 | `BRAKE_N` | GPIO13, Q4 |

### J5 — TURN, xi-nhan, 3 chân

| Chân | Tín hiệu | GPIO |
| --- | --- | --- |
| 1 | `+5V_SYS` | — |
| 2 | `LEFT_N` | GPIO10, Q5 |
| 3 | `RIGHT_N` | GPIO11, Q6 |

Không có ngõ hazard riêng trên J5. Hazard được tạo từ công tắc tay lái, xem J2.

### J6 — HORN, còi, 2 chân

| Chân | Tín hiệu | GPIO |
| --- | --- | --- |
| 1 | `+5V_SYS` | — |
| 2 | `HORN_N` | GPIO6, Q8A hoặc Q8B |

### J7 — AUX, 2 chân

| Chân | Tín hiệu | GPIO |
| --- | --- | --- |
| 1 | `+5V_SYS` | — |
| 2 | `AUX_N` | GPIO41, Q7 |

Mỗi kênh có diode flyback trên PCB: cathode ở `+5V_SYS`, anode ở cực drain. Đèn và AUX dùng SS14. Còi dùng SS34.

## 6. J2 — HANDLEBAR, tay lái, JST-XH 8 chân

| Chân | Tín hiệu | GPIO | Việc của công tắc |
| --- | --- | --- | --- |
| 1 | `+3V3` | — | Nguồn kéo lên. Không lấy dòng tải từ chân này |
| 2 | GND | — | Mass công tắc |
| 3 | `LEFT_SW` | GPIO15 | Xi-nhan trái, active low |
| 4 | `RIGHT_SW` | GPIO16 | Xi-nhan phải, active low |
| 5 | `HORN_SW` | GPIO21 | Còi, active low |
| 6 | `LIGHT_SW` | GPIO39 | Đèn, active low |
| 7 | `HAZARD_SW` | không vào GPIO | Nút hazard, active low |
| 8 | `BRAKE_SW` | GPIO40 | Phanh, active low |

Chân 7 không đi thẳng vào ESP32. Khi nút hazard kéo `HAZARD_SW` xuống GND, D13 và D14 (BAT54) kéo `LEFT_SW` và `RIGHT_SW` xuống theo. Firmware coi là hazard khi GPIO15 và GPIO16 cùng thấp.

Công tắc xi-nhan thường không làm chân 7 xuống thấp. Chỉ nút hazard mới kéo chân 7.

## 7. MOD1 — LiDAR VL53L1X, JST-XH 6 chân

Module nhìn ra cạnh trước. Thứ tự chân dưới đây là hợp đồng của PCB. **Đối chiếu với module mua về trước khi cắm.** Nếu module đảo chân, không cắm, mà sửa dây hoặc sửa bản mạch.

| Chân | Tín hiệu | Ghi chú |
| --- | --- | --- |
| 1 | `+3V3` | Nguồn module |
| 2 | GND | |
| 3 | `I2C_SDA` | GPIO8, kéo lên 4.7 kΩ trên PCB |
| 4 | `I2C_SCL` | GPIO9, kéo lên 4.7 kΩ trên PCB |
| 5 | `LIDAR_XSHUT` | GPIO4, kéo lên 10 kΩ. Active low để tắt module |
| 6 | `LIDAR_INT` | GPIO5, kéo lên 10 kΩ |

Địa chỉ I2C của VL53L1X trên bus này là 0x29. Nếu module đã có điện trở kéo I2C riêng, chỉ để một cặp kéo trên toàn bus: cặp trên PCB là R13/R14.

## 8. Bus I2C và UART GPS

I2C 100 kHz, một bus duy nhất.

| Thiết bị | Địa chỉ | Chân cấu hình |
| --- | --- | --- |
| INA228 | 0x40 | A0 = A1 = GND |
| BH1750FVI | 0x23 | ADDR = GND |
| VL53L1X | 0x29 | trên MOD1 |
| BMI270 | 0x68 | SDO = GND, CSB = 3.3 V |

GPS là UART, không nằm trên I2C. Chân SDA/SCL của MAX-M10S để hở.

| Tín hiệu trên PCB | Chiều | GPIO ESP32-S3 |
| --- | --- | --- |
| `GPS_TXD` | module GPS phát, ESP nhận | GPIO17 |
| `GPS_RXD` | ESP phát, module GPS nhận | GPIO18 |

GPIO17 trên module là chân U1TXD, nhưng firmware phải đưa UART RX vào GPIO17 qua GPIO matrix. GPIO18 nhận UART TX. Cắm ngược TX/RX thì không có NMEA.

`V_BCKP` của GPS nối 3.3 V. Không có pin backup. Chân 15 `VIO_SEL` để hở (hở = I/O 3.3 V). Không được nối chân đó xuống GND.

Anten chip GPS nối qua R17. Bản V1 để R17 = 0 Ω, C20 và C21 không lắp, cho tới khi chốt mã anten và mạng phối hợp.

## 9. GPIO còn lại

| GPIO | Tín hiệu | Mức chủ động |
| --- | --- | --- |
| 0 | BOOT, SW2 | thấp khi giữ để vào download |
| 4 | LiDAR XSHUT | thấp = tắt module |
| 5 | LiDAR INT | theo module |
| 6 | Cổng MOSFET còi | cao = mở MOSFET |
| 7 | Đèn pha | cao = bật |
| 8 | I2C SDA | open-drain |
| 9 | I2C SCL | open-drain |
| 10 | Xi-nhan trái | cao = bật |
| 11 | Xi-nhan phải | cao = bật |
| 12 | Đèn hậu | cao = bật |
| 13 | Đèn phanh | cao = bật |
| 15 | Công tắc trái | thấp = nhấn |
| 16 | Công tắc phải | thấp = nhấn |
| 17 | Nhận UART từ GPS | — |
| 18 | Phát UART tới GPS | — |
| 19 | USB D− | — |
| 20 | USB D+ | — |
| 21 | Công tắc còi | thấp = nhấn |
| 38 | IMU INT | đánh thức |
| 39 | Công tắc đèn | thấp = nhấn |
| 40 | Công tắc phanh | thấp = nhấn |
| 41 | AUX | cao = bật |
| 42 | LED trạng thái trên PCB | qua R11 330 Ω |
| EN | Reset, SW1 kéo xuống GND | kéo lên 10 kΩ |

GPIO45 và GPIO46 để nổi. Không rút dây ra ngoài.

## 10. Điểm đo

| Điểm | Mạng | Kỳ vọng khi chỉ cắm USB hoặc chỉ cắm J1 5 V |
| --- | --- | --- |
| TP1 | `+5V_IN` | Có 5 V khi cắm J1. Phải không có 5 V khi chỉ cắm USB |
| TP2 | `+5V_SYS` | Khoảng 4.6–4.8 V |
| TP3 | `+3V3` | 3.3 V |
| TP4 | GND | 0 V |
| TP5 | USB D+ | chỉ đo khi debug USB |
| TP6 | USB D− | chỉ đo khi debug USB |
| TP7 | `GPS_TXD` | UART từ GPS |
| TP8 | `GPS_RXD` | UART tới GPS |
| TP9 | I2C SDA | |
| TP10 | I2C SCL | |
| TP11 | cổng đèn pha, phía GPIO | 0 V ngay sau khi boot, trước khi firmware bật đèn |
| TP12 | cổng còi, phía GPIO | 0 V ngay sau khi boot |
| TP13 | cổng xi-nhan trái | 0 V ngay sau khi boot |
| TP14 | cổng xi-nhan phải | 0 V ngay sau khi boot |

Thứ tự cấp nguồn lần đầu, khi chưa cắm đèn và chưa cắm còi, nằm trong tài liệu thiết kế `docs/design/05-bom-and-bringup.md`.

## 11. Việc phải chốt trước khi sản xuất hàng loạt

Bản này đủ để xem, in thử 1:1 và làm mạch mẫu. Bốn việc sau vẫn mở, vì chúng phụ thuộc linh kiện mua về chứ không phụ thuộc sơ đồ nối:

1. Đo dòng còi, rồi hàn **một** trong hai vị trí Q8A (SOT-23) hoặc Q8B (TO-252). Vị trí còn lại để trống.
2. Đo dòng từng đèn. Kênh nào từ 1 A liên tục trở lên thì không được gắn Si2302CDS.
3. Chốt mã anten GPS và điền giá trị R17, C20, C21 theo datasheet anten đó.
4. Đối chiếu thứ tự chân MOD1 với module VL53L1X thực tế.

Land pattern của BH1750 trên PCB là mẫu cho gói WSOF6, pad 0.28 × 0.22 mm, pitch 0.5 mm, không có exposed pad. Đối chiếu lại với land của ROHM trước khi đặt panel lớn.

## 12. Thông số sẽ gửi xưởng, sau khi DRC sạch

Chưa xuất gerber. Khi DRC còn 0 mục chưa nối, hồ sơ xưởng dùng các giá trị sau.

| Hạng mục | Giá trị |
| --- | --- |
| Kích thước | 70.00 × 50.00 mm |
| Số lớp | 4. L1 tín hiệu, L2 GND, L3 nguồn, L4 tín hiệu |
| Độ dày | 1.6 mm |
| Đồng | 1 oz cả bốn lớp |
| Khoan nhỏ nhất | 0.20 mm (via nhiệt của module ESP32). Via tín hiệu khoan 0.30 mm, pad 0.60 mm |
| Khoảng cách đồng tới mép trong file | 0.25 mm. Đồng thực tế gần nhất đang cách mép khoảng 0.37 mm, tại hàng chân USB |
| Khoảng cách lỗ tối thiểu trong file | 0.15 mm |
| Hoàn thiện | HASL hoặc ENIG |
| Màu | theo xưởng. Silk trắng, mặt top phải đọc được J1–J8 và MOD1 |
| Vùng cấm đồng | mép phải, x > 66.5 mm và 28 mm < y < 48 mm (anten ESP32). Mép trước-trái, x < 6 mm và y > 42 mm (anten GPS) |

Không có lớp 48 V, không có relay, không có giắc CAN.
