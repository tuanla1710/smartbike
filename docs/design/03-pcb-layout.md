# 3. PCB layout V1

Chỉ bắt đầu layout khi ERC của schematic đã sạch.

## 3.1 Tấm mạch

| Hạng mục | Giá trị |
| --- | --- |
| Outline | 70.00 × 50.00 mm |
| Gốc tọa độ | góc dưới-trái |
| Cạnh trước xe | y = 50 mm, mép trên |
| Cạnh sau, phía connector tải | y = 0 |
| Độ dày | 1.6 mm |
| Đồng | 1 oz cả bốn lớp |
| Via tín hiệu | khoan 0.3 mm, pad 0.6 mm |
| Via GND dưới exposed pad | khoan 0.25–0.30 mm, vài via trong pad U2 và U4 |
| Lỗ bắt vít | 4 × M2 (khoan 2.2 mm), tâm lỗ cách mép 3.5 mm, nếu lỗ trước không chạm vùng cấm anten thì giữ; nếu chạm thì bỏ hai lỗ trước |
| Fiducial | 3 fiducial 1.0 mm, cách mép ≥ 5 mm, không nằm trên vùng anten |

Silk mặt trên: `SMART BIKE V5  PCB V1` và `5V ONLY`.

## 3.2 Stackup

| Lớp | Vai trò |
| --- | --- |
| L1 | Linh kiện và tín hiệu |
| L2 | Mặt phẳng GND, liền nhất có thể |
| L3 | Power: polygon `+5V_SYS` và `+3V3` |
| L4 | Tín hiệu |

L2 không bị xẻ dưới đường USB, dưới module ESP32 (trừ vùng anten), hay dưới đường RF của GPS. L3 mang dòng tải; L1 bổ sung polygon ở kênh còi và ở đoạn shunt.

Không đổ `+5V_SYS` trên L2.

## 3.3 Vùng đặt

Nhìn từ phía trước xe, mặt top:

```
y = 50  FRONT
┌────────────────────────────────────────────┐
│ MOD1 VL53L1X          cửa sổ nhìn ra trước │
│                                            │
│ AE1 GPS          U5 BMI270        U4 ESP32 │
│ anten            U6 BH1750     anten module│
│ U7 MAX-M10S                      ở mép phải│
│                                            │
│ U2 buck          U1 INA228    Q2…Q8        │
│ F1 Q1 D2 D3              D6…D12            │
│ J1          J3  J4  J5  J6  J7             │
└────────────────────────────────────────────┘
y = 0   REAR
J2 có thể nằm cạnh trái nếu hàng XH phía sau không còn chỗ.
J8 USB-C nằm cạnh sau hoặc cạnh trái. Anten ESP32 chiếm mép phải, nên USB không đặt ở mép đó.
```

Hai vùng không trộn vào nhau:

- Phía trước và giữa: RF, ESP32, GPS, IMU, ánh sáng, LiDAR.
- Phía sau: cầu chì, buck, shunt, MOSFET, connector tải.

Khoảng cách tối thiểu giữa cuộn `L1` (node SW) và anten GPS: đặt buck ở góc sau, anten GPS ở mép trước-trái. Không đặt còi MOSFET cạnh module GPS.

## 3.4 ESP32

Module nằm mép phải, phần anten của module hướng ra ngoài cạnh phải.

Vùng cấm anten, theo hardware design guidelines của Espressif cho module có anten PCB:

- Không đồng trên **cả bốn lớp** dưới phần anten của module.
- Không linh kiện, không via, không đường mạch trong vùng đó.
- Anten module hướng ra mép mạch, phía ngoài không có đồng.
- USB và UART không đi sát anten.

`C9` và `C10` sát chân 2. Mass của hai tụ xuống L2 bằng via ngay cạnh pad GND.

## 3.5 GPS

- Anten chip ở mép trái, feed hướng vào trong.
- Cắt đồng theo đúng hình keep-out của datasheet anten đã chọn, trên các lớp mà datasheet yêu cầu. Thường là cắt L1 và không đổ đồng đối diện feed.
- Đường `GPS_RF` dài vừa đủ, CPWG 50 Ω, tham chiếu L2 liền, không via.
- `R17`, `C20`, `C21` sát chân `RF_IN`.
- Không cho node `SW`, cổng còi, hay đường `HORN_N` đi dưới module GPS.

## 3.6 Buck

Thứ tự vật lý sát nhau: `C3`/`C4` → `U2` → `L1` → `C5`.

- PGND và AGND gặp nhau tại exposed pad, rồi via xuống L2.
- Node `SW` chỉ là đoạn ngắn từ chân 7 tới `L1`.
- Không biến node `SW` thành test point.

## 3.7 Dòng mạnh

Shunt `R2` hướng sao cho đường dòng đi thẳng từ `+5V_MERGED` sang `+5V_SYS`. Hai đường sense rẽ từ mép pad, cặp với nhau, tới `IN+` và `IN−`.

| Đường | Đồng tối thiểu |
| --- | --- |
| `+5V_IN` tới `F1`, qua `Q1`, tới shunt | polygon, tương đương ≥ 3 mm trên 1 oz, hoặc rộng hơn trên L1 + L3 |
| `+5V_SYS` trục chính tới J3–J7 | polygon L3, và nhánh L1 ngắn tới từng connector |
| `HORN_N` từ J6 tới drain Q8 | polygon ≥ 4 mm, hoặc L1 + L3 nối via dày |
| Các net đèn `*_N` | ≥ 1.0 mm nếu dòng kênh dưới 1 A; tăng theo số đo thực |

MOSFET ngồi cạnh connector của chính nó. Không kéo `HORN_N` vòng lên vùng GPS.

`F1` gần J1. `D2` gần `Q1`, dây mass của TVS ngắn xuống via L2.

## 3.8 Tín hiệu

- I2C đi ngắn giữa ESP32, U1, U5, U6 và MOD1. Kéo xa khỏi node `SW` và khỏi polygon còi.
- Cặp USB 90 Ω ± 10%, cùng dài, cùng lớp, tham chiếu L2. Ít via. Nếu phải via, thêm via mass cạnh đó.
- `GPS_TXD` và `GPS_RXD` là đường chậm, vẫn không luồn dưới anten.
- Cổng MOSFET là tín hiệu số thường. Series 100 Ω đặt gần GPIO của ESP32.

## 3.9 LiDAR và ánh sáng

`MOD1` sát y = 50, thân module có thể nhô khỏi outline nếu datasheet module cần khoảng trống phía trước cửa sổ. Ghi vùng cấm cơ khí trên lớp User: không vít, không gân vỏ, không dây trong hình nón nhìn của VL53L1X.

BH1750 quay cửa sổ lên trên hoặc ra mép, nơi vỏ có lỗ ánh sáng. Không đặt ngay dưới header.

## 3.10 Trước khi xuất gerber

- ERC sạch, DRC sạch.
- Không đồng trong keep-out anten ESP32 và keep-out anten GPS.
- L2 còn liền dưới USB và dưới ESP32 phần không phải anten.
- Đã điền MPN anten và giá trị `R17`/`C20`/`C21`.
- Đã quyết định `Q8A` hoặc `Q8B`, footprint còn lại để DNP và không bị DRC hiểu nhầm là chưa nối. Hai MOSFET song song là cố ý.
- Silk đọc được tên J1–J8 và chiều chân 1.
- Không có net 48 V nào trong schematic.
