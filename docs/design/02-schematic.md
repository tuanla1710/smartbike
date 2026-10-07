# 2. Schematic V1 — hợp đồng cho KiCad

Mỗi mục dưới đây là một sheet. Tên net viết hoa, dùng đúng chuỗi này trên mọi sheet. KiCad cần `PWR_FLAG` trên `+5V_IN` và `GND`.

Quy tắc chung:

- Tụ gốm, điện áp ghi là điện áp định mức, không phải điện áp làm việc.
- Điện trở 1% 0603 trừ khi ghi khác.
- Cổng MOSFET đèn có series 100 Ω và pull-down 100 kΩ xuống `GND`. Pull-down giữ tải tắt trong lúc ESP32 còn đang reset.
- Firmware phải ghi mức thấp ra mọi chân gate trước khi đổi chân đó sang output.

## 2.1 Sheet `power`

### Chuỗi nguồn xe

```
J1-1 +5V_IN
  │
 F1 3A
  │
 +5V_FUSED ──── Q1 source (DMG2305UX)
                 Q1 drain  ──── +5V_PROT
                 Q1 gate   ── R1 100k ── GND
                 D1 BZT52C5V6: cathode = source, anode = gate

D2 SMAJ5.0A: cathode = +5V_PROT, anode = GND

+5V_PROT ── D3 SS54 anode→cathode ── +5V_MERGED
```

`Q1` là P-MOSFET high-side. **Source ở `+5V_FUSED`, drain ở `+5V_PROT`.** Đảo hai chân này thì cắm đúng cực cũng không nuôi được mạch. Chân SOT-23 của DMG2305UX: 1 = Gate, 2 = Source, 3 = Drain. Đối chiếu lại footprint KiCad với datasheet Diodes trước khi xuất gerber.

Zener `D1` kẹp `VGS` khoảng −5.6 V. Điện áp làm việc chỉ khoảng −5 V; zener là lớp chặn khi có xung.

`D2` đặt sau MOSFET chống đảo cực. Chiều TVS một chiều: cathode lên rail, anode xuống mass. SMAJ5.0A có điện áp standoff 5.0 V, đánh thủng khoảng 6.4 V, kẹp khoảng 9.2 V ở dòng xung danh định. TPS62162-Q1 chịu được tới 17 V. Tải đèn trong xung đó có thể thấy quá 5 V cho tới khi `F1` đứt; đây là đặc điểm của TVS này, chấp nhận cho V1.

### Cộng nguồn với USB, không back-feed

```
+5V_PROT ── D3 SS54 ──┐
                      ├── +5V_MERGED
USB_VBUS ── F2 ── D4 SS34 ──┘
```

`D3` và `D4` là diode Schottky, anode phía nguồn, cathode phía `+5V_MERGED`.

Khi chỉ cắm USB, `+5V_SYS` thấp hơn VBUS khoảng điện áp rơi của `D4` (khoảng 0.3–0.4 V). Khi chỉ có nguồn xe, sụt nằm trên `D3`. Hai nguồn không được cấp ngược cho nhau.

`F2` là PTC 1.1 A hold trên đường USB. Đường USB không được phép nuôi còi hay cả cụm đèn.

### Đo công suất

```
+5V_MERGED ── R2 10 mΩ 2512 ── +5V_SYS

U1 INA228
  IN+  = +5V_MERGED     (phía nguồn của shunt)
  IN−  = +5V_SYS        (phía tải của shunt)
  VBUS = +5V_SYS
  VS   = +3V3
  GND  = GND
  A1   = GND
  A0   = GND
  SCL  = I2C_SCL
  SDA  = I2C_SDA
  ALERT = ALERT, R3 10k lên +3V3
```

Địa chỉ I2C: **0x40**.

Đi dây sense: hai đường `IN+` và `IN−` tách từ mép trong của hai pad shunt, không đi chung với đồng dòng mạnh. Đây là kết nối Kelvin.

`C1` 100 nF từ `VS` xuống `GND`, sát U1.

`C2` 22 µF 10 V X5R từ `+5V_SYS` xuống `GND`, đặt gần cụm MOSFET.

Ở 3 A, sụt shunt là 30 mV, tán nhiệt khoảng 90 mW. Điện trở shunt: **10 mΩ, 1%, 1 W, 2512**. Dải ADC V1 dùng thang ±163.84 mV (`ADCRANGE = 0`) để dòng xung của còi không bị cắt ngọn. Hằng số hiệu chuẩn nằm ở tài liệu firmware.

`ALERT` không vào GPIO ở V1. Firmware đọc INA228 theo chu kỳ. Chân `ALERT` vẫn có pull-up để không bị nổi.

### Buck 5 V → 3.3 V

`U2` = **TPS62162-Q1**, gói WSON-8 DSG 2 × 2 mm, đầu ra cố định 3.3 V, 1 A. Mã đặt hàng gợi ý: `TPS62162QDSGTQ1`.

| Chân | Tên | Nối |
| --- | --- | --- |
| 1 | PGND | GND, và exposed pad |
| 2 | VIN | `+5V_SYS` |
| 3 | EN | `+5V_SYS` |
| 4 | AGND | GND |
| 5 | FB | AGND (nối mass). Bản 3.3 V cố định; datasheet khuyên nối FB xuống AGND |
| 6 | VOS | `+3V3` |
| 7 | SW | `L1` phía buck |
| 8 | PG | `PGOOD`, kéo lên `+3V3` bằng `R4` 100 kΩ. Không vào MCU |
| EP | thermal | GND, vài via xuống lớp GND |

Phụ kiện, đúng bộ LC khuyến nghị của TI:

| Ref | Giá trị | Việc |
| --- | --- | --- |
| C3 | 10 µF, 25 V, X5R, 0805 | VIN xuống GND, sát chân 2 |
| C4 | 100 nF, 25 V, 0402 | VIN xuống GND, sát hơn C3 |
| L1 | 2.2 µH, Isat ≥ 1.6 A, có vỏ chắn | SW tới `+3V3`. Gợi ý: TDK VLF3012ST-2R2M1R4 hoặc tương đương shielded 3 × 2.8 mm |
| C5 | 22 µF, 10 V, X5R, 0805 | `+3V3` xuống GND, ngay sau cuộn |
| R4 | 100 kΩ | `PGOOD` lên `+3V3` |

Vòng dòng đầu vào: `C3` → VIN → PGND → GND của `C3` phải ngắn. Node `SW` giữ diện tích nhỏ, không kéo xuống dưới anten GPS.

## 2.2 Sheet `usb`

`J8` là USB-C 16 chân, receptacle bảng, ví dụ kiểu `TYPE-C-31-M-12`. Chỉ dùng USB 2.0. Các chân SuperSpeed để hở.

| Chân receptacle | Net |
| --- | --- |
| A4, A9, B4, B9 | `USB_VBUS` |
| A5 | `CC1` |
| B5 | `CC2` |
| A6, B6 | `USB_D_P` |
| A7, B7 | `USB_D_N` |
| A1, A12, B1, B12, shield | `GND` |
| A8, B8 (SBU) | để hở |
| TX/RX SuperSpeed | để hở |

| Ref | Giá trị | Việc |
| --- | --- | --- |
| R5 | 5.1 kΩ | `CC1` xuống `GND` |
| R6 | 5.1 kΩ | `CC2` xuống `GND` |
| U3 | USBLC6-2SC6 | ESD. `VBUS` pin của USBLC6 vào `USB_VBUS`, I/O vào D+ và D− phía connector, GND xuống mass |
| C6 | 100 nF | `USB_VBUS` xuống `GND`, sát J8 |
| R7 | 22 Ω | series trên `USB_D_P`, sát module ESP32 |
| R8 | 22 Ω | series trên `USB_D_N`, sát module ESP32 |
| C7 | DNP, 0402 | từ phía ESP32 của D+ xuống GND, vị trí để sẵn theo hướng dẫn Espressif |
| C8 | DNP, 0402 | tương tự cho D− |

`R7`/`R8` nằm gần module, không nằm gần connector. Cặp D+/D− là differential 90 Ω.

`F2` và `D4` chỉ đặt một lần, trên sheet `power`. Sheet `usb` giao ra net `USB_VBUS`.

ESP32-S3 không đàm phán USB-PD. Hai điện trở 5.1 kΩ chỉ xin dòng USB mặc định (tối đa khoảng 500 mA ở host tuân thủ). Đủ để nạp firmware và chạy MCU cùng cảm biến.

## 2.3 Sheet `mcu`

`U4` = **ESP32-S3-WROOM-1-N8**. Anten PCB in trên module. Không dùng bản WROOM-1U.

Chân nguồn và điều khiển:

| Chân module | Tên | Nối |
| --- | --- | --- |
| 1 | GND | `GND` |
| 2 | 3V3 | `+3V3` |
| 3 | EN | `EN` |
| 40 | GND | `GND` |
| 41 | EPAD | `GND` |

| Ref | Giá trị | Việc |
| --- | --- | --- |
| C9 | 10 µF, 10 V, 0603 | `+3V3` xuống GND, sát chân 2 |
| C10 | 100 nF, 10 V, 0402 | `+3V3` xuống GND, sát chân 2 |
| R9 | 10 kΩ | `EN` lên `+3V3`. Chân EN không được để nổi |
| C11 | 1 µF | `EN` xuống `GND`, tạo trễ bật |
| SW1 | nút nhấn 6 × 6 mm | `EN` xuống `GND`, reset |
| R10 | 10 kΩ | `GPIO0` lên `+3V3` |
| SW2 | nút nhấn 6 × 6 mm | `GPIO0` xuống `GND`, BOOT |

LED trạng thái, active-high:

```
GPIO42 ── R11 330 Ω ── D5 anode
D5 cathode ── GND
```

`D5` là LED xanh 0603. Dòng khoảng 4 mA.

`GPIO19` nối net `USB_D_N` sau `R8`. `GPIO20` nối net `USB_D_P` sau `R7`.

Các GPIO chức năng nối đúng bảng ở [01-architecture.md](01-architecture.md). Không nối gì vào GPIO45 và GPIO46.

UART GPS không dùng chân mặc định của UART1 trên module (`IO17` mặc định là `U1TXD`, `IO18` mặc định là `U1RXD`). Firmware phải gán qua GPIO matrix: RX = GPIO17, TX = GPIO18.

## 2.4 Sheet `sensors`

Một cặp pull-up cho cả bus. Nếu module VL53L1X đã có pull-up riêng, gỡ pull-up trên module hoặc không lắp `R13`/`R14`, chỉ để lại một cặp.

| Ref | Giá trị | Việc |
| --- | --- | --- |
| R13 | 4.7 kΩ | `I2C_SDA` lên `+3V3` |
| R14 | 4.7 kΩ | `I2C_SCL` lên `+3V3` |

### U1 INA228

Đã nối ở sheet power. Trên sheet này chỉ là các net `I2C_SDA`, `I2C_SCL`, `ALERT`.

### U5 BMI270

Gói LGA-14, 2.5 × 3.0 mm. I2C vì `CSB` nối `+3V3`.

| Chân | Tên | Nối |
| --- | --- | --- |
| 1 | SDO | `GND` → địa chỉ **0x68** |
| 2 | ASDX | để hở |
| 3 | ASCX | để hở |
| 4 | INT1 | `IMU_INT` = GPIO38 |
| 5 | VDDIO | `+3V3` |
| 6 | GNDIO | `GND` |
| 7 | GND | `GND` |
| 8 | VDD | `+3V3` |
| 9 | INT2 | để hở |
| 10 | OCSB | để hở |
| 11 | OSDO | để hở |
| 12 | CSB | `+3V3` |
| 13 | SCx | `I2C_SCL` |
| 14 | SDx | `I2C_SDA` |

| Ref | Giá trị | Việc |
| --- | --- | --- |
| C13 | 100 nF | VDD xuống GND, trong vòng 1 mm |
| C14 | 100 nF | VDDIO xuống GND, trong vòng 1 mm |

Đặt BMI270 xa vùng đồng chịu lực cơ khí lớn (góc lỗ vít, mép kẹp vỏ) để giảm lệch offset do strain.

Firmware phải nạp file init của Bosch trước khi đọc gia tốc và con quay.

### U6 BH1750FVI

Gói WSOF6. ADDR xuống mass → địa chỉ **0x23**.

| Chân | Tên | Nối |
| --- | --- | --- |
| 1 | VCC | `+3V3` |
| 2 | ADDR | `GND` |
| 3 | GND | `GND` |
| 4 | SDA | `I2C_SDA` |
| 5 | DVI | nút RC bên dưới |
| 6 | SCL | `I2C_SCL` |

`DVI` là chân reset bất đồng bộ và là điện áp tham chiếu I2C. Nó phải ở thấp sau khi VCC đã lên, rồi mới lên cao.

```
+3V3 ── R12 10k ── DVI ── C16 100 nF ── GND
C15 100 nF từ VCC xuống GND
```

Hằng số RC khoảng 1 ms, dài hơn thời gian VCC tăng, nên thỏa điều kiện tối thiểu 1 µs của datasheet ROHM.

Cửa sổ quang của BH1750 phải nhìn ra ngoài vỏ, không bị che bởi pin header hay thành nhôm.

### MOD1 VL53L1X

Module, không vẽ mạch sensor trần. Header 1 × 6, pitch 2.54 mm, net theo thứ tự sau. Silk phải in tên chân. Trước khi khóa footprint, đối chiếu đúng module sẽ mua: nhiều board GY-VL53L1X đảo SDA/SCL.

| Pin header | Net |
| --- | --- |
| 1 | `+3V3` |
| 2 | `GND` |
| 3 | `I2C_SDA` |
| 4 | `I2C_SCL` |
| 5 | `LIDAR_XSHUT` |
| 6 | `LIDAR_INT` |

| Ref | Giá trị | Việc |
| --- | --- | --- |
| R15 | 10 kΩ | `LIDAR_XSHUT` lên `+3V3` |
| R16 | 10 kΩ | `LIDAR_INT` lên `+3V3` |
| C17 | 100 nF | `+3V3` xuống GND tại header |

Địa chỉ mặc định **0x29**. `XSHUT` mức cao thì sensor chạy; GPIO4 kéo thấp để shutdown. Ngắt là open-drain.

Module đặt sát mép trước, cửa sổ laser nhìn về phía trước xe, không bị đồng hay vỏ che.

## 2.5 Sheet `gps`

`U7` = **u-blox MAX-M10S**. Đối chiếu pinout với datasheet UBX-20035208 của đúng lô mua. Các bản khác nhau gọi chân 15 là `Reserved` hoặc `VIO_SEL`. Cả hai trường hợp V1 đều **để hở chân 15**. Không nối chân 15 xuống mass: nếu đó là `VIO_SEL`, mass sẽ chọn IO 1.8 V trong khi bus UART của ESP32 là 3.3 V.

| Chân | Tên | Nối |
| --- | --- | --- |
| 1, 10, 12 | GND | `GND` |
| 2 | TXD | `GPS_TXD` → GPIO17 |
| 3 | RXD | `GPS_RXD` ← GPIO18 |
| 4 | TIMEPULSE | để hở |
| 5 | EXTINT | để hở |
| 6 | V_BCKP | `+3V3` |
| 7 | V_IO | `+3V3` |
| 8 | VCC | `+3V3` |
| 9 | RESET_N | để hở |
| 11 | RF_IN | net `GPS_RF` |
| 13 | LNA_EN | để hở. Không dùng chân này làm GPIO |
| 14 | VCC_RF | để hở khi dùng anten thụ động |
| 15 | Reserved / VIO_SEL | để hở |
| 16 | SDA | để hở. Không nối vào bus I2C của xe |
| 17 | SCL | để hở |
| 18 | SAFEBOOT_N | để hở |

| Ref | Giá trị | Việc |
| --- | --- | --- |
| C18 | 1 µF | VCC xuống GND |
| C19 | 100 nF | VCC xuống GND, sát chân 8 |

UART mặc định của module: 9600 8N1. Firmware được phép nâng baud sau khi đã bắt tay.

### Anten

`AE1` là anten chip GPS L1 1575.42 MHz, đặt ở mép trái PCB. Mạng pi:

```
U7 RF_IN ── R17 ── AE1 feed
             │
            C20 xuống GND (DNP cho tới khi có giá trị datasheet)
AE1 feed ── C21 xuống GND (DNP cho tới khi có giá trị datasheet)
```

`R17` khởi tạo là 0 Ω chỉ để mạch thông. Trước khi xuất gerber, thay `R17`, `C20`, `C21` bằng mạng phối hợp in trong datasheet của đúng MPN anten đã chọn. Đường `GPS_RF` là CPWG 50 Ω trên L1, lớp tham chiếu L2, không via.

MAX-M10S đã có SAW và LNA trong module. Anten thụ động không cần thêm LNA. `VCC_RF` và `LNA_EN` để hở.

## 2.6 Sheet `outputs`

Mọi kênh là low-side:

```
+5V_SYS ── tải ── net *_N ── drain MOSFET
                              source ── GND
GPIO ── 100 Ω ── gate
                 │
               100 kΩ
                 │
                GND

Diode hồi tiếp: cathode = +5V_SYS, anode = net *_N
```

| Kênh | MOSFET | Gate | Net drain | Series | Pull-down | Flyback | Connector |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Đèn pha | Q2 Si2302CDS | `HEADLIGHT_GATE` GPIO7 | `HEADLIGHT_N` | R18 100 | R25 100k | D6 SS14 | J3-2 |
| Đèn hậu | Q3 Si2302CDS | `TAIL_GATE` GPIO12 | `TAIL_N` | R19 100 | R26 100k | D7 SS14 | J4-2 |
| Đèn phanh | Q4 Si2302CDS | `BRAKE_GATE` GPIO13 | `BRAKE_N` | R20 100 | R27 100k | D8 SS14 | J4-3 |
| Trái | Q5 Si2302CDS | `LEFT_GATE` GPIO10 | `LEFT_N` | R21 100 | R28 100k | D9 SS14 | J5-2 |
| Phải | Q6 Si2302CDS | `RIGHT_GATE` GPIO11 | `RIGHT_N` | R22 100 | R29 100k | D10 SS14 | J5-3 |
| AUX | Q7 Si2302CDS | `AUX_GATE` GPIO41 | `AUX_N` | R23 100 | R30 100k | D11 SS14 | J7-2 |
| Còi | Q8A hoặc Q8B | `HORN_GATE` GPIO6 | `HORN_N` | R24 100 | R31 100k | D12 SS34 | J6-2 |

Chân SOT-23 của Si2302CDS: đối chiếu datasheet Vishay khi gán footprint. Thông thường 1 = Gate, 2 = Source, 3 = Drain. Không lấy nhầm footprint P-channel.

`Q8A` là Si2302CDS, SOT-23. `Q8B` là MOSFET logic-level TO-252, MPN để trống. Gate, drain, source của `Q8A` và `Q8B` song song. **Chỉ hàn một trong hai.** Cả hai để DNP trên BOM cho tới khi có số đo dòng còi.

| Dòng còi đo được | Lắp |
| --- | --- |
| Dưới 1 A | Q8A Si2302CDS |
| 1 A đến 3 A | Q8B, MOSFET logic-level, RDS(on) thấp, VGS(th) đủ mở ở 3.3 V. Ứng viên để đánh giá: IRLR8726 hoặc tương đương TO-252. Chốt MPN trong BOM trước khi lắp |
| Trên 3 A | Dừng. Cầu chì, shunt, J1 và J6 của V1 không chịu được. Không vá bằng một MOSFET lớn hơn trên cùng PCB này |

`D12` là SS34 vì năng lượng xung của còi lớn hơn đèn. Sáu diode đèn là SS14.

High-side của mọi tải là cùng net `+5V_SYS`, lấy từ chân 1 của từng connector tải.

## 2.7 Sheet `handlebar`

`J2` JST-XH 8 chân.

| Pin | Net | Trong PCB |
| --- | --- | --- |
| 1 | `+3V3` | nguồn pull-up cho cụm công tắc |
| 2 | `GND` | mass công tắc |
| 3 | `LEFT_SW` | GPIO15 |
| 4 | `RIGHT_SW` | GPIO16 |
| 5 | `HORN_SW` | GPIO21 |
| 6 | `LIGHT_SW` | GPIO39 |
| 7 | `HAZARD_SW` | không vào GPIO |
| 8 | `BRAKE_SW` | GPIO40 |

Mỗi công tắc trên tay lái nối giữa chân tín hiệu và `GND`. Mức tác động là thấp.

Với từng net `LEFT_SW`, `RIGHT_SW`, `HORN_SW`, `LIGHT_SW`, `BRAKE_SW`, `HAZARD_SW`:

```
+3V3 ── 10 kΩ ── net ── 100 nF ── GND
                  │
                 J2
```

| Net | Pull-up | Tụ |
| --- | --- | --- |
| `LEFT_SW` | R32 10k | C22 100n |
| `RIGHT_SW` | R33 10k | C23 100n |
| `HORN_SW` | R34 10k | C24 100n |
| `LIGHT_SW` | R35 10k | C25 100n |
| `BRAKE_SW` | R36 10k | C26 100n |
| `HAZARD_SW` | R37 10k | C27 100n |

Tụ 100 nF lắp sẵn. Dây tay lái dài.

Hazard, không tốn GPIO:

```
LEFT_SW  ── D13 anode    D13 cathode ── HAZARD_SW
RIGHT_SW ── D14 anode    D14 cathode ── HAZARD_SW
```

`D13` và `D14` là BAT54. Khi `HAZARD_SW` bị công tắc kéo xuống mass, cả `LEFT_SW` và `RIGHT_SW` xuống khoảng 0.3 V. Khi chỉ bấm trái, diode ngược nên `RIGHT_SW` không bị kéo theo.

Firmware: hazard khi `LEFT_SW` và `RIGHT_SW` cùng thấp.

## 2.8 Connector tải

Tất cả là JST-XH, một loại crimp cho bản prototype. XH chịu khoảng 3 A. Nếu dòng còi đo được buộc phải đổi connector, J1 và J6 chuyển sang JST-VH ở bản sau; V1 vẫn vẽ XH.

| Ref | Pin | Net |
| --- | --- | --- |
| J1 | 1 | `+5V_IN` |
| J1 | 2 | `GND` |
| J3 | 1 | `+5V_SYS` |
| J3 | 2 | `HEADLIGHT_N` |
| J4 | 1 | `+5V_SYS` |
| J4 | 2 | `TAIL_N` |
| J4 | 3 | `BRAKE_N` |
| J5 | 1 | `+5V_SYS` |
| J5 | 2 | `LEFT_N` |
| J5 | 3 | `RIGHT_N` |
| J6 | 1 | `+5V_SYS` |
| J6 | 2 | `HORN_N` |
| J7 | 1 | `+5V_SYS` |
| J7 | 2 | `AUX_N` |

Silk mỗi connector ghi tên và số chân. Không dựa vào trí nhớ khi crimp.

## 2.9 Test point

Pad tròn 1.5 mm, xuyên lỗ hoặc SMD, có silk. Bắt buộc:

| TP | Net |
| --- | --- |
| TP1 | `+5V_IN` |
| TP2 | `+5V_SYS` |
| TP3 | `+3V3` |
| TP4 | `GND` |
| TP5 | `USB_D_P` |
| TP6 | `USB_D_N` |
| TP7 | `GPS_TXD` |
| TP8 | `GPS_RXD` |
| TP9 | `I2C_SDA` |
| TP10 | `I2C_SCL` |
| TP11 | `HEADLIGHT_GATE` |
| TP12 | `HORN_GATE` |
| TP13 | `LEFT_GATE` |
| TP14 | `RIGHT_GATE` |

Không đặt test point trên node `SW` của buck.

## 2.10 Thứ tự vẽ

1. `power` — gồm cả diode USB và shunt, vì các net nguồn sinh ra ở đây.
2. `usb` — J8, CC, ESD, series resistor.
3. `mcu` — module, EN, BOOT, LED.
4. `sensors` — I2C và ba thiết bị.
5. `gps` — UART và anten.
6. `outputs` — bảy kênh.
7. `handlebar` — J2 và hazard.

ERC phải sạch trước khi cập nhật PCB. Mọi chân để hở có chủ đích phải được đánh dấu no-connect, trừ các chân đã nói là để hở ở trên.
