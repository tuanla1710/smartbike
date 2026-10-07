# 11. Test tự động và giả lập phần cứng

Firmware C chưa cần có mạch mới chạy được các ca ở [08-control-algorithms.md](08-control-algorithms.md). Bộ giả lập trong `firmware/sim/` đóng vai phần cứng và chạy đúng luật điều khiển đã khóa. Cùng một kịch bản console sẽ chạy lại trên mạch thật khi firmware đã nạp, vì dòng lệnh giống [09-debug-commands.md](09-debug-commands.md).

Giả lập là mô hình để soi logic. Nó không thay đo gate trên PCB, không thay quét I2C bốn địa chỉ, và không thay một lần ngủ thật bằng GPIO38.

## 11.1 Hai đích

| Đích | Khi dùng | Thời gian | Lệnh `hw` |
| --- | --- | --- | --- |
| `sim` | Đang viết luật, chưa có mạch hoặc chưa nạp được | `tick` nhảy đồng hồ giả | Có |
| `serial` | Firmware đã chạy trên ESP32-S3 | `tick` là ngủ thật từng mili giây | Không. Runner trả `err sim-only` |

Lệnh console (`status`, `arm`, `inject`, `hold`, `config`, …) giống nhau ở cả hai đích. Kịch bản chỉ dùng các lệnh đó thì chạy được trên sim hôm nay và trên USB ngày mạch sống.

`hw` là mặt bàn thử: bấm công tắc, đặt lux, kéo SDA chết, đổi điện áp bus, kẹt chân IMU. Phần cứng thật làm những việc đó bằng tay hoặc bằng đồ gá. Không đưa `hw` vào kịch bản sẽ chạy trên serial.

## 11.2 Những gì giả lập tính

Mỗi `tick 10` là một nhịp 10 ms.

- Sáu công tắc active-low, debounce, hazard khi trái và phải cùng thấp. `hw press hazard` kéo cả hai dây, đúng diode trên PCB.
- Bốn địa chỉ I2C. Rút một địa chỉ thì mẫu đó già đi rồi hết hạn.
- INA228: điện áp do `hw power` đặt, dòng là tổng tải của các chân `out_*`. Duty LEDC nhân theo 0..1023. Mất cảm biến quá 200 ms thì `inhibit=power`.
- BH1750, VL53L1X, xung IMU giữ mức 250 ms, GPS nhận hoặc loại câu 0,0 và câu hỏng.
- Ống cổng ra: arm, khóa lỗi, UVLO, quá dòng, luật còi, `hold` 30 s.
- Mode, báo động, ngủ. Ngủ ghi CRC arm rồi boot lại. `hw reset power` và `hw reset wdt` xóa arm. `hw reset deepsleep` giữ arm nếu CRC còn.
- Queue bốn lệnh. `inject` không sửa áp và dòng.
- Gói `snapshot` 32 byte.

Failsafe được giả bằng `hw stall`: các nhịp sau không xoa bộ đếm, quá 50 ms thì kéo `out_*` về 0 và tăng `failsafe_count`.

Không giả lập sóng BLE, thời gian LEDC trong một chu kỳ 1 kHz, hay sụt áp do điện trở dây. Muốn sụt áp thì `hw power <mV>`.

## 11.3 Cách nói chuyện

Chạy từ thư mục `firmware/`:

```text
python3 -m sim
```

Dòng `hw ...` và `tick <ms>` do giả lập xử lý. Dòng còn lại là console firmware. Trạng thái tải chỉ đổi sau `tick`, vì lệnh điều khiển vào queue và chờ nhịp 10 ms. Lệnh xem trả lời ngay.

```text
hw help
status
arm
tick 10
gates
hw press left
tick 40
inputs
debug on
inject lux 99
tick 10
gates
```

`tick 40` là bốn nhịp. Debounce 30 ms nên sau 40 ms công tắc đã stable.

| Lệnh hw | Tác dụng |
| --- | --- |
| `hw press <left\|right\|horn\|light\|brake\|hazard>` | Kéo dây xuống thấp |
| `hw release <cùng tên>` | Thả dây |
| `hw lux <0..65535>` | Lux BH1750 |
| `hw range <0..65534>` | Khoảng cách hợp lệ |
| `hw range none` | Mất mẫu LiDAR |
| `hw motion on\|off` | Nguồn xung IMU. `off` vẫn còn mức thêm 250 ms |
| `hw pin high\|low` | Mức GPIO38 thật. `inject pin` không sửa chân này |
| `hw power <mV>\|dead\|auto` | Áp bus, hoặc ngừng mẫu INA228, hoặc trả về 4700 mV |
| `hw load <kênh> <mA>` | Dòng khi kênh đó mở hết. Kênh: head, tail, left, right, brake, horn, aux |
| `hw i2c <40\|23\|29\|68> on\|off` | Có hoặc mất địa chỉ |
| `hw gps <vĩ> <kinh>` | Câu fix hợp lệ, độ thập phân |
| `hw gps bad` | Câu bị loại, giữ tọa độ cũ |
| `hw gps none` | Hết câu mới, quá 5 s thì hạ fix |
| `hw stall on\|off` | Ngừng xoa failsafe |
| `hw reset power\|wdt\|deepsleep` | Boot lại theo lý do reset |
| `hw wake` | Kéo GPIO38 cao để thức nếu đang ngủ |
| `hw status` | Số của bàn thử, không phải snapshot firmware |

## 11.4 Kịch bản

Một file văn bản, một dòng một bước. Dòng `#` bỏ qua.

| Dòng | Việc |
| --- | --- |
| lệnh console hoặc `hw` hoặc `tick` | Thực hiện |
| `expect <chuỗi>` | Chuỗi đó phải nằm trong các dòng vừa in ra từ bước liền trước |

`expect` không gửi xuống firmware. Một bước được nhiều `expect`.

```text
debug on
expect ok
inject lux 99
expect ok
arm
expect ok queued
tick 10
expect evt arm=1
gates
expect out_head=1023
```

Thư mục:

| Đường | Đích |
| --- | --- |
| `firmware/sim/scenarios/portable/` | Sim và sau này là serial |
| `firmware/sim/scenarios/plant/` | Chỉ sim, vì có `hw` |

Chạy hết:

```text
cd firmware
python3 -m unittest sim.test_sim
python3 -m sim.runner
python3 -m sim.runner scenarios/portable/headlight.txt
python3 -m sim.runner --port /dev/ttyACM0 scenarios/portable/headlight.txt
```

`--port` cần gói `pyserial`. Sau mỗi lệnh console, runner đọc dòng trả lời rồi chờ thêm tối đa 200 ms để lấy `evt` do nhịp 10 ms in ra. `tick 1000` trên serial ngủ 1 s, không tua đồng hồ.

Ca ở mục 8.17 mà chỉ cần lux, mode, còi, hàng lệnh thì để trong `portable/` và dùng `inject` cùng `config set`. Ca cần dây công tắc, mất INA228, kẹt chân, reset watchdog thì để trong `plant/`.

Khi viết firmware C, luật thuần ở phase 6 của checklist vẫn có assert host riêng. Giả lập này là lớp trên đó: queue, ống cổng ra, và bàn thử. Lệch giữa `evt` của giả lập và `evt` của mạch, với cùng file kịch bản, là lỗi cần sửa trước khi ký phase 13.
