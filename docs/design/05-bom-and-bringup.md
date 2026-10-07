# 5. BOM và bring-up

Giá mục tiêu, chưa gồm đèn, còi, dây và vỏ:

| Số lượng | Mục tiêu |
| --- | --- |
| 1 board prototype | khoảng 120–180 nghìn won |
| 10–20 board | khoảng 80–120 nghìn won mỗi board |

Bảng dưới là danh sách lắp. MPN là gợi ý để tìm symbol và footprint; được thay bằng linh kiện cùng thông số nếu footprint không đổi. Ô để trống là việc còn mở ở [README](README.md).

## 5.1 Nguồn

| Ref | Giá trị | Footprint | MPN gợi ý | Ghi chú |
| --- | --- | --- | --- | --- |
| F1 | Cầu chì 3 A, fast | 1206 | Littelfuse 0466003.NR | Một lần, không phải PTC |
| Q1 | P-MOSFET −20 V | SOT-23 | Diodes DMG2305UX | Chân 2 Source = `+5V_FUSED`, chân 3 Drain = `+5V_PROT`. Kiểm tra lại footprint |
| R1 | 100 kΩ | 0603 | | Gate Q1 xuống GND |
| D1 | Zener 5.6 V | SOD-123 | BZT52C5V6 | Cathode tại source Q1 |
| D2 | TVS 5.0 V uni | DO-214AC | SMAJ5.0A | Cathode tại `+5V_PROT` |
| D3 | Schottky 5 A, 40 V | SMC | SS54 | OR nguồn xe |
| F2 | PTC 1.1 A hold | 1812 | Littelfuse 1812L110 | Đường USB |
| D4 | Schottky 3 A, 40 V | SMA | SS34 | OR USB |
| R2 | 10 mΩ, 1%, 1 W | 2512 | | Shunt |
| U1 | INA228 | VSSOP-10 | INA228AIDGSR | |
| C1 | 100 nF, 10 V | 0402 | | VS của U1 |
| R3 | 10 kΩ | 0603 | | ALERT lên 3V3 |
| C2 | 22 µF, 10 V, X5R | 0805 | | Bulk `+5V_SYS` |
| U2 | TPS62162-Q1 | WSON-8 2×2 | TPS62162QDSGTQ1 | Exposed pad xuống GND |
| L1 | 2.2 µH, Isat ≥ 1.6 A | 3.0 × 2.8 mm | TDK VLF3012ST-2R2M1R4 | Shielded |
| C3 | 10 µF, 25 V, X5R | 0805 | | VIN buck |
| C4 | 100 nF, 25 V | 0402 | | VIN buck |
| C5 | 22 µF, 10 V, X5R | 0805 | | VOUT buck |
| R4 | 100 kΩ | 0603 | | PGOOD lên 3V3 |

`Q1` trong SOT-23 tán khoảng 0.5 W ở 3 A liên tục. V1 chấp nhận vì đèn và còi không cùng kéo 3 A mãi. Nếu đo thấy dòng trung bình trên 2 A liên tục, bản sau đổi Q1 sang P-MOSFET gói lớn hơn.

## 5.2 USB và MCU

| Ref | Giá trị | Footprint | MPN gợi ý | Ghi chú |
| --- | --- | --- | --- | --- |
| J8 | USB-C receptacle 16 pin | mid-mount | TYPE-C-31-M-12 hoặc tương đương đã có trong thư viện | USB 2.0 |
| R5, R6 | 5.1 kΩ | 0603 | | CC1, CC2 |
| U3 | USBLC6-2SC6 | SOT-23-6 | ST USBLC6-2SC6 | |
| C6 | 100 nF | 0402 | | VBUS |
| R7, R8 | 22 Ω | 0402 | | Series D+, D− sát ESP32 |
| C7, C8 | DNP | 0402 | | Vị trí dự phòng xuống GND |
| U4 | ESP32-S3-WROOM-1-N8 | module Espressif | ESP32-S3-WROOM-1-N8 | Anten PCB, 8 MB, không PSRAM |
| C9 | 10 µF, 10 V | 0603 | | 3V3 module |
| C10 | 100 nF | 0402 | | 3V3 module |
| R9 | 10 kΩ | 0603 | | EN |
| C11 | 1 µF | 0402 | | EN |
| SW1, SW2 | Nút 6 × 6 mm | through-hole | | Reset, BOOT |
| R10 | 10 kΩ | 0603 | | GPIO0 |
| R11 | 330 Ω | 0603 | | LED |
| D5 | LED xanh | 0603 | | |

## 5.3 Cảm biến và GPS

| Ref | Giá trị | Footprint | MPN gợi ý | Ghi chú |
| --- | --- | --- | --- | --- |
| U5 | BMI270 | LGA-14 2.5 × 3.0 | Bosch BMI270 | |
| C13, C14 | 100 nF | 0402 | | VDD và VDDIO |
| U6 | BH1750FVI | WSOF6 1.6 × 1.6 | ROHM BH1750FVI-TR | |
| C15, C16 | 100 nF | 0402 | | VCC và DVI |
| R12 | 10 kΩ | 0603 | | DVI |
| R13, R14 | 4.7 kΩ | 0603 | | I2C pull-up, một cặp cho cả bus |
| MOD1 | Module VL53L1X | header 1 × 6, 2.54 mm | Module có đúng thứ tự chân trong schematic | Đối chiếu silk trước khi route |
| R15, R16 | 10 kΩ | 0603 | | XSHUT, INT |
| C17 | 100 nF | 0402 | | Tại header |
| U7 | MAX-M10S | u-blox MAX | MAX-M10S | Chân 15 để hở |
| C18 | 1 µF | 0402 | | VCC GPS |
| C19 | 100 nF | 0402 | | VCC GPS |
| AE1 | Anten chip GPS L1 | theo MPN | chưa chốt | |
| R17 | 0 Ω cho tới khi có match | 0402 | | Series RF |
| C20, C21 | DNP cho tới khi có match | 0402 | | Shunt RF |

## 5.4 Tải và tay lái

| Ref | Giá trị | Footprint | MPN gợi ý | Ghi chú |
| --- | --- | --- | --- | --- |
| Q2–Q7 | N-MOSFET logic-level | SOT-23 | Vishay Si2302CDS | Sáu kênh đèn và AUX |
| Q8A | Si2302CDS | SOT-23 | | DNP cho tới khi đo còi. Loại trừ Q8B |
| Q8B | N-MOSFET công suất, logic-level | TO-252 | chưa chốt | DNP cho tới khi đo còi. Loại trừ Q8A |
| R18–R24 | 100 Ω | 0603 | | Series gate, R24 dùng chung cho Q8A/Q8B |
| R25–R31 | 100 kΩ | 0603 | | Gate xuống GND |
| D6–D11 | Schottky 1 A | SMA | SS14 | Flyback đèn và AUX |
| D12 | Schottky 3 A | SMA | SS34 | Flyback còi |
| J1 | 2 pin | JST-XH | | `+5V_IN`, GND |
| J2 | 8 pin | JST-XH | | Tay lái |
| J3 | 2 pin | JST-XH | | Đèn pha |
| J4 | 3 pin | JST-XH | | Hậu + phanh |
| J5 | 3 pin | JST-XH | | Trái + phải |
| J6 | 2 pin | JST-XH | | Còi |
| J7 | 2 pin | JST-XH | | AUX |
| R32–R37 | 10 kΩ | 0603 | | Pull-up công tắc |
| C22–C27 | 100 nF | 0402 | | Lọc công tắc |
| D13, D14 | Schottky nhỏ | SOD-123 | BAT54 | Hazard |
| TP1–TP14 | Pad 1.5 mm | | | Đúng bảng schematic |

## 5.5 Bring-up

Chưa cắm đèn, chưa cắm còi.

1. Nhìn mắt thường và đo thông mạch: `+5V_IN`, `+5V_SYS`, `+3V3` không chạm `GND`.
2. Cắm **chỉ USB**. `TP2` (`+5V_SYS`) khoảng 4.6–4.8 V. `TP3` là 3.3 V. `TP1` không được có 5 V — nếu có, diode OR đang ngược hoặc chập.
3. Rút USB. Cấp 5 V vào J1 qua hạn dòng 100 mA. `TP2` khoảng 4.6–4.8 V vì có sụt trên `D3`. `TP3` là 3.3 V. VBUS của J8 không được sống.
4. Cả hai nguồn cùng lúc: J1 không bị USB đẩy ngược, VBUS không bị nguồn xe đẩy ngược.
5. Nạp firmware qua USB-C. Nếu cổng không vào download, giữ SW2 (BOOT) rồi bấm SW1 (RESET).
6. Quét I2C: 0x40, 0x23, 0x29, 0x68.
7. Đo mọi gate ở TP11–TP14 và các gate còn lại: phải là 0 V khi firmware vừa boot.
8. Gắn từng tải một, đo dòng, ghi vào `config`. Kênh nào trên 1 A thì không được để `Si2302CDS`.
9. Đo dòng còi riêng, rồi mới hàn `Q8A` hoặc `Q8B`.

GPS: ra trời thoáng, chờ fix. Nếu không có tín hiệu, việc đầu tiên là kiểm tra mạng phối hợp anten và vùng cấm đồng, không phải firmware NMEA.

LiDAR: vật cản trong 4 m phải đổi số đọc. Cửa sổ module phải nhìn ra mép trước, không nhìn vào vỏ.
