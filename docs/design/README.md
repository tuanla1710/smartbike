# Smart Bike Controller — PCB V1

Tài liệu này chốt bản thiết kế **PCB Smart Bike Controller V1** cho xe V5.

Sơ đồ nguyên lý KiCad đã có ERC sạch. Bản đặt linh kiện và hồ sơ chân nối cho khách nằm ở [đặc tả kết nối](../customer/SmartBike-V5-Ket-Noi.md). File thiết kế mở bằng `hardware/kicad/kicad.sh`.

Nếu một datasheet của linh kiện mua về khác bảng chân trong tài liệu này, datasheet thắng. Cập nhật lại tài liệu trước khi routing.

## Đọc theo thứ tự

| Tài liệu | Dùng khi |
| --- | --- |
| [01-architecture.md](01-architecture.md) | Nhìn toàn bộ hệ thống, phạm vi V1, các quyết định đã khóa |
| [02-schematic.md](02-schematic.md) | Vẽ từng sheet KiCad: net, chân, R/C, MOSFET, connector |
| [03-pcb-layout.md](03-pcb-layout.md) | Outline 70 × 50 mm, stackup 4 lớp, vùng đặt linh kiện, luật đồng |
| [04-firmware.md](04-firmware.md) | Map GPIO, địa chỉ I2C, state machine, hợp đồng với phần cứng |
| [05-bom-and-bringup.md](05-bom-and-bringup.md) | Designator, footprint, mục BOM, thứ tự cấp nguồn lần đầu |
| [Đặc tả kết nối](../customer/SmartBike-V5-Ket-Noi.md) | Bảng chân J1–J8, MOD1, I2C, UART, điểm đo — bản giao cho người tích hợp dây |
| [06-software.md](06-software.md) | Ngôn ngữ, cây source ESP-IDF, task, BLE, thứ tự viết |
| [07-software-architecture.md](07-software-architecture.md) | Tầng, mặt phẳng, luật phụ thuộc, hợp đồng dữ liệu giữa khối |
| [08-control-algorithms.md](08-control-algorithms.md) | Thuật toán điều khiển và flowchart Mermaid |
| [09-debug-commands.md](09-debug-commands.md) | Lệnh console USB để test và debug thủ công |
| [10-implementation-checklist.md](10-implementation-checklist.md) | Thứ tự viết firmware và điều kiện pass từng bước |
| [11-automation-test.md](11-automation-test.md) | Test tự động và bộ giả lập phần cứng |

## Thông số đã khóa

| Hạng mục | Giá trị |
| --- | --- |
| Tên | Smart Bike Controller V1 |
| Kích thước | 70.00 × 50.00 mm |
| Số lớp | 4 |
| Độ dày | 1.6 mm |
| Nguồn vào PCB | 5 V duy nhất |
| MCU | ESP32-S3-WROOM-1-N8 |
| Đèn, xi-nhan, còi | Low-side MOSFET, không relay |
| GPS | u-blox MAX-M10S + anten chip |
| LiDAR trước | Module VL53L1X, tầm khoảng 4 m |
| IMU | BMI270 |
| Ánh sáng | BH1750 |
| Đo V / I / P / năng lượng | INA228 + shunt 10 mΩ |
| Lập trình | USB-C, USB Serial/JTAG của ESP32-S3 |
| Radio | Wi-Fi và Bluetooth trên module |
| Firmware về sau | OTA trên flash 8 MB |

48 V không vào PCB. V1 không có 5G, CAN, camera, stage nguồn 48 V, hay MCU phụ.

## Việc còn mở trước khi đặt hàng PCB

1. Đo dòng còi V5, rồi chọn một trong hai footprint còi (`Q8A` hoặc `Q8B`).
2. Đo dòng từng đèn. `Si2302CDS` chỉ được gắn cho kênh dưới 1 A liên tục.
3. Chọn MPN anten GPS và chép mạng phối hợp từ datasheet anten vào `R17`, `C20`, `C21`.
4. Đối chiếu thứ tự chân module VL53L1X mua về với header `MOD1` trước khi khóa footprint.
