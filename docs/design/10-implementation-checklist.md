# 10. Phase và checklist triển khai phần mềm

Làm đúng thứ tự phase firmware. Phase sau mở khi mọi ô firmware của phase trước đã pass. Ô còn trống là việc C trên ESP-IDF chưa làm. Ô đã tick ở mục Oracle là giả lập đã chạy, không viết lại.

Mỗi phase firmware có một kịch bản đối chiếu. Trước khi gắn mạch, `evt` của firmware phải trùng giả lập trên các file `portable/`. Lệnh `hw` chỉ có trên giả lập. Cách chạy nằm ở [11-automation-test.md](11-automation-test.md).

Chân và mức tích cực: [04-firmware.md](04-firmware.md). Cây file và byte BLE: [06-software.md](06-software.md). Tầng: [07-software-architecture.md](07-software-architecture.md). Thuật toán: [08-control-algorithms.md](08-control-algorithms.md). Console: [09-debug-commands.md](09-debug-commands.md).

Bốn điều kiện đi theo mọi phase:

- Số GPIO chỉ có trong `components/board/include/board.h`.
- Nhịp 10 ms không ghi NVS, không gọi I2C, không `printf`, không cấp phát.
- Task `console` không ghi GPIO và không ghi LEDC.
- `gates` in `want_*` trước ống cổng ra và `out_*` sau ống.

| Phase | Firmware phải có | Đối chiếu giả lập | Pass trên mạch |
| --- | --- | --- | --- |
| 0 | Project ESP-IDF dịch được | Không | Nạp USB-C, console in dòng boot |
| 1 | Gate an toàn, LEDC duty 0 | Không thay đo điện | Mọi gate 0 V |
| 2 | Thời gian, NVS, arm RTC | `plant/arm_reset.txt` | Reset thường xóa arm |
| 3 | Console đọc | `portable/boot.txt` | `status` lúc chưa arm |
| 4 | I2C và INA228 | `plant/power_dead.txt` | Bốn địa chỉ, áp khoảng 4,6–4,8 V |
| 5 | Debounce và hazard | `plant/debounce.txt` | `inputs` tách raw và stable |
| 6 | Chính sách thuần | `portable/headlight.txt` | Đèn pha đổi theo lux thật |
| 7 | Nhịp 10 ms, queue, failsafe | `portable/queue.txt` | Gate về 0 khi vòng bị chặn |
| 8 | Ống cổng ra, `hold`, `arm` | `portable/horn_budget.txt` | Đo từng tải trên J1 |
| 9 | IMU, lux, LiDAR, GPS | unittest GPS và LiDAR | Cờ vật cản không đụng phanh |
| 10 | Mode, báo động, ngủ | `portable/alarm_reject.txt` | Thức bằng GPIO38, arm còn nếu CRC đúng |
| 11 | BLE 32 byte | hex `snapshot` của giả lập | Notify khớp lệnh `snapshot` |
| 12 | Runner trên USB | `python3 -m sim.runner --port` | Cả thư mục `portable/` |
| 13 | Ký mục 8.17 | Ca logic đã ký trong sim | Ca điện ký bằng đo và log |

Kích thước stack là điểm bắt đầu, chỉnh sau khi xem high-water. `vehicle` 4096, `sensors` 8192, `gps` 4096, `console` 4096 byte. Ưu tiên: `vehicle` cao hơn `sensors`, `sensors` cao hơn `gps`, `gps` cao hơn `console`. NimBLE giữ ưu tiên của ESP-IDF.

Oracle chạy từ thư mục `firmware/`:

```text
python3 -m unittest sim.test_sim
python3 -m sim.runner
```

Lệch `evt` giữa firmware và file kịch bản là lỗi của firmware. Giả lập không được sửa cho khớp mạch nếu mạch sai hợp đồng mục 8.

## Oracle — đã có

- [x] `firmware/sim/` : bàn thử `hw`, luật điều khiển, console mục 9.
- [x] `python3 -m sim` để gõ tay khi đang viết.
- [x] `scenarios/portable/` : boot, đèn pha, queue, từ chối `ride start` trong báo động, luật còi.
- [x] `scenarios/plant/` : debounce, mất INA228, reset xóa arm.
- [x] Unittest: hậu chỉ khi `RIDING`, chuyển động lúc đi không báo động, LiDAR không đụng phanh, snapshot 32 byte, khóa còi, quá dòng, ba lần UVLO, hủy ngủ, deep sleep giữ arm, GPS 0,0, failsafe, `inject` không sửa áp.
- [x] Firmware C nằm ở `firmware/`. Lõi `components/vehicle/bike_ctrl.c` khớp oracle trên host: từ thư mục `firmware`, `make -C host && python3 host/diff_oracle.py`. Các ô phase bên dưới vẫn mở cho đến khi `idf.py build` và đo trên mạch.

## Phase 0 — Khung dịch

File: `firmware/CMakeLists.txt`, `sdkconfig.defaults`, `partitions_8mb.csv`, `firmware/main/CMakeLists.txt`, `firmware/main/app_main.c`.

- [ ] ESP-IDF 5.3 trở lên, target `esp32s3`.
- [ ] Partition: `nvs` 24 KB, `otadata` 8 KB, `phy_init` 4 KB, `factory` 2 MB, `ota_0` 2 MB, `ota_1` 2 MB. Không bật rollback.
- [ ] Không PSRAM. Wi-Fi tắt. NimBLE bật. Console là USB Serial/JTAG.
- [ ] `app_main` chưa chứa luật đèn hay thanh ghi INA228.
- [ ] Thư mục component đúng mục 6.2, kể cả `console/` và `third_party/bmi270`, `third_party/vl53l1x`. Hai gói thứ ba chưa bị gọi.

Pass: `idf.py build` sạch, nạp được, cổng serial mở được. Chưa có kịch bản giả lập cho phase này.

## Phase 1 — Chân an toàn

File: `components/board/include/board.h`, `components/board/board.c`, `components/board/CMakeLists.txt`.

`board.h` khai báo đủ chân mục 1.8 của tài liệu kiến trúc phần cứng: gate, công tắc, I2C, UART GPS, `XSHUT`, `IMU_INT`, `STATUS_LED`. GPIO19 và GPIO20 không cấu hình lại. GPIO0 chỉ thuộc nút BOOT trên PCB. Các chân strapping để hở không bị kéo trong firmware.

- [ ] `board_outputs_safe()` ghi mức thấp ra GPIO6, GPIO7, GPIO10, GPIO11, GPIO12, GPIO13, GPIO41, rồi mới đặt các chân đó thành output.
- [ ] LEDC một timer, 1 kHz, 10 bit, bốn kênh pha, hậu, trái, phải. Duty khởi tạo 0.
- [ ] Phanh, còi, AUX là GPIO mức, không vào LEDC.
- [ ] `STATUS_LED` GPIO42 active-high. Lúc này chỉ nhịp đỗ xe: 50 ms sáng mỗi 2 s.
- [ ] `LIDAR_XSHUT` là output và đang thấp.
- [ ] UART GPS: RX GPIO17, TX GPIO18, 9600 8N1. Không dùng mapping UART1 mặc định của module.

Pass: reset, đo bảy gate 0 V. LED nhấp ngắn. `XSHUT` đo thấp. Giả lập không thay bước đo này.

## Phase 2 — Thời gian, cấu hình, kiểu

File: `components/config/defaults.h`, `bike_config.h`, `bike_config.c`, `components/link/include/snapshot.h`, `components/vehicle/include/bike_types.h`.

- [ ] `now_ms` là `esp_timer_get_time() / 1000` trong `uint32_t`. Phép trừ không dấu. So sánh bằng `elapsed >= limit`.
- [ ] `defaults.h` có đủ tên và số mục 8.2. Mỗi hằng là một từ căn chỉnh để task console ghi từng từ mà nhịp 10 ms đọc không rách.
- [ ] `bike_config_load()` đọc NVS đúng một lần lúc boot. Chưa có khóa thì dùng mặc định.
- [ ] Struct `perception_t`, `actuation_t`, `command_t`, `mode_step_result_t`, `bike_inputs_t`, `bike_mode_t` đúng mục 7.6. `actuation_t` có `left_lit`, `right_lit`, `horn_from_alarm`.
- [ ] Snapshot có một mutex. Người ghi từng nhóm trường đúng bảng mục 7.5. Mutex chỉ được giữ trong lúc chép struct.
- [ ] Arm là struct trong `RTC_DATA_ATTR`: magic, cờ, CRC8. Khôi phục chỉ khi `esp_reset_reason()` là deep sleep và CRC khớp. Mọi reset khác ghi arm tắt và CRC mới.
- [ ] Buffer NMEA 128 byte và buffer BLE 32 byte cấp một lần lúc init.

Pass host: elapsed đúng khi `now_ms` quấn qua 0. Pass mạch: `config` in đúng mặc định. `arm` rồi nhấn reset thường, `armed=0`. Đối chiếu: `scenarios/plant/arm_reset.txt` trên giả lập. Lệnh `arm` của console có thể chưa có ở phase này; mục mạch pass được bằng hàm ghi RTC tạm, rồi xóa đường tạm trước phase 3.

## Phase 3 — Console đọc

File: `components/console/console.c`.

- [ ] Một task. Đọc stdin từng dòng, tối đa 80 byte, token cách nhau một dấu cách, chữ thường.
- [ ] Trả lời đúng một dòng `ok`, `ok k=v`, hoặc `err syntax|range|debug|queue|nvs`. Dòng `evt` chỉ xuất hiện khi nhịp 10 ms báo trạng thái đổi.
- [ ] Có `help`, `status`, `gates`, `faults`, `config`, `watch <100..5000>`, `watch off`.
- [ ] `watch` do task console in. Nhịp 10 ms không gọi `printf`.
- [ ] Lệnh chưa tới phase của nó trả `err syntax` và không ghi trạng thái.

Pass: sau boot, `status` và `gates` cho `armed=0`, `inhibit=disarmed`, mọi `out_*=0`. `watch 50` trả `err range`. `watch 100` rồi `watch off` dừng in. Đối chiếu: `scenarios/portable/boot.txt`.

## Phase 4 — I2C và INA228

File: `components/sensors/i2c_bus.c`, `include/i2c_bus.h`, `components/power/ina228.c`, `include/ina228.h`. Task `sensors` lúc này chỉ quét bus và đọc INA228.

- [ ] I2C 100 kHz, GPIO8 SDA, GPIO9 SCL. Một mutex. Chỉ task `sensors` lấy mutex đó.
- [ ] Trước khi quét, kéo `XSHUT` cao. Quét xong nếu driver VL53L1X chưa init thì kéo thấp lại.
- [ ] Địa chỉ bắt buộc: `0x40`, `0x23`, `0x29`, `0x68`. Thiếu địa chỉ thì ghi lỗi snapshot và thử lại mỗi 1 s. `app_main` không vòng quét.
- [ ] Lỗi giao dịch: chín xung SCL, STOP, thử lại một lần. Phục hồi bus tối đa một lần mỗi giây, không chen vào giữa một lần đọc đang dở.
- [ ] INA228 `ADCRANGE` 0, `SHUNT_CAL` 1250, `CURRENT_LSB` = 5/2^19. Đọc bus voltage, current, power, energy.
- [ ] Bộ giới hạn coi dòng âm là 0. Snapshot giữ dòng thô.
- [ ] `power_valid` sai khi chưa có mẫu hoặc tuổi mẫu ≥ 200 ms. Khi sai, ống cổng ra cấm tải.
- [ ] Lệnh `i2c`, `power`, `sense`. `i2c` chỉ đặt cờ; task `sensors` quét ở vòng của nó.

Pass trên USB: `i2c` in đủ bốn địa chỉ. `power` khoảng 4600..4800 mV. Kéo SDA xuống quá 200 ms thì `inhibit=power` và `out_*=0`. Đối chiếu logic mất mẫu: `scenarios/plant/power_dead.txt`. Bốn địa chỉ thật không lấy từ giả lập.

## Phase 5 — Công tắc

File: `components/vehicle/inputs.c`, `include/inputs.h`.

- [ ] Sáu chân active-low: GPIO15, GPIO16, GPIO21, GPIO39, GPIO40, và hazard là tổ hợp chứ không phải GPIO riêng.
- [ ] Mỗi kênh có `candidate`, `candidate_since_ms`, `stable`. `stable` bắt đầu false.
- [ ] `raw` đổi thì chỉ cập nhật candidate. `stable` đổi khi cùng mức và elapsed ≥ `debounce_ms`.
- [ ] `hazard = stable.left && stable.right` sau khi cả sáu kênh đã lấy mẫu.
- [ ] Lệnh `inputs` in raw và stable của sáu công tắc, cộng `hazard`.

Pass: `watch 100`. Rung nhanh hơn 30 ms không đổi `stable`. Giữ trái và phải thì `hazard=1`. Chỉ trái thì `hazard=0` và `stable_right=0`. Dây hở đọc như không bấm. Đối chiếu: `scenarios/plant/debounce.txt`.

## Phase 6 — Chính sách thuần

File: `components/vehicle/lighting.c`, `turn_signal.c`, `brake.c`, `horn.c`. Oracle biên lux, pha và còi là `sim.test_sim`, không viết một bảng số thứ hai.

Các hàm này không include GPIO, I2C, NimBLE, hay `esp_deep_sleep.h`.

- [ ] Đèn pha. Lux hợp lệ và lux < 100 thì `head_on = true`. Lux > 200 thì `head_on = false`. Lux từ 100 đến 200, kể cả hai đầu, giữ nguyên. Tuổi lux ≥ 1000 ms thì giữ `head_on`. `LIGHT_SW` trả duty 1023 và không sửa `head_on`. Chưa có mẫu và không bấm công tắc thì duty 0.
- [ ] Đèn hậu duty 1023 chỉ khi mode là `RIDING`, ngược lại 0.
- [ ] Phanh bằng `stable.brake` trong `PARKING` và `RIDING`.
- [ ] `phase_on = (now_ms % 800) < 400`. Hazard thì cả hai `lit` true và cùng duty. Một phía thì phía kia duty 0. Đổi phía không reset `now_ms`. `left_lit` vẫn true ở nửa kỳ duty 0.
- [ ] Còi người lái tắt ngay khi `stable` hết. Mốc 30 s chạy từ lúc `stable` thành true, kể cả chưa arm. Hết 30 s thì khóa đến khi stable cao. Hàm này đặt `horn_from_alarm = false`.
- [ ] `ride_policy` không đọc `obstacle`.

Pass: `scenarios/portable/headlight.txt` trên giả lập vẫn xanh, và firmware cho cùng `out_head` với lux 99, 150, 201. Pha 0 và 399 ms bật, 400 và 799 ms tắt. Còi khóa ở 30000 ms rồi mở lại sau một lần thả. `python3 -m unittest sim.test_sim` không được sửa cho đỏ rồi đổi oracle.

## Phase 7 — Nhịp 10 ms

File: `components/vehicle/vehicle.c`, `components/power/power_mode.c` có thể chưa chuyển mode thật. `app_main` tạo task theo mục 6.5 và tạo thêm task `console`.

- [ ] `vTaskDelayUntil` chu kỳ 10 ms.
- [ ] Queue tĩnh dài 4. Gửi và nhận timeout 0. Đầy thì bỏ lệnh mới, tăng `cmd_dropped`, giữ lệnh cũ.
- [ ] Một nhịp lấy tối đa một lệnh.
- [ ] Đầu nhịp: lấy mẫu công tắc, lấy lệnh, chép perception, thả mutex, rồi mới gọi chính sách.
- [ ] Cuối nhịp xoa failsafe và watchdog task. Failsafe 50 ms, trong ISR chỉ đưa duty LEDC về 0 và bảy gate về thấp, không lấy mutex.
- [ ] Watchdog: `vehicle` 200 ms, `sensors` 2 s, `gps` 5 s. Task GPS xoa watchdog cả khi UART im.
- [ ] Vòng dưới 2 ms khi không có bus. Không có log trong vòng.

Pass: `status` tiếp tục in. Chặn `vehicle` quá 50 ms thì bảy gate đo 0 V. Reset do watchdog cho `armed=0`. Đối chiếu queue: `scenarios/portable/queue.txt`. Failsafe trên giả lập là `test_failsafe_stall`; trên mạch là đo gate.

## Phase 8 — Ống cổng ra

File: `board.c` thêm `outputs_apply`. Console thêm `arm`, `disarm`, `debug`, `hold`, `config set`, `config save`.

Thứ tự trong một nhịp, sau chính sách: gắn `aux_latch` nếu kênh AUX không bị `hold`, trộn `hold`, luật dòng còi, rồi cấm tải, rồi ghi LEDC và GPIO.

- [ ] `debug on` / `debug off` chỉ ở RAM. Reset và deep sleep đều tắt phiên và xóa `hold`, `inject`.
- [ ] `hold` khi phiên tắt trả `err debug` và không đổi duty.
- [ ] `hold head|tail on` ép 1023. `hold head|tail <0..1023>` ép đúng số. `off` ép 0.
- [ ] `hold left|right on` đặt `*_lit` và duty vẫn theo pha. Duty số thì không nhấp, `lit` true khi duty khác 0.
- [ ] `hold brake|horn|aux` chỉ `on` hoặc `off`. Thêm số là `err syntax`, không ghi một nửa lệnh.
- [ ] `hold off` xóa mọi ép. Mỗi ép tự hết sau 30 s và in `evt hold=off`.
- [ ] Chưa có `horn_current_ma`: xóa còi người lái khi duty pha khác 0, duty hậu khác 0, và một `*_lit` true. Còi có `horn_from_alarm` không bị xóa bởi luật này.
- [ ] Cấm tải khi chưa arm, hoặc `fault_latch`, hoặc `power_valid` sai, hoặc UVLO, hoặc quá dòng. `STATUS_LED` không đi qua cửa này.
- [ ] Quá dòng: > 2500 mA đủ 100 ms, hoặc ≥ 3000 mA ngay, thì `fault_latch`.
- [ ] UVLO: < 4200 mV đủ 50 ms thì cấm. ≥ 4600 mV đủ 200 ms thì xóa UVLO nếu chưa khóa. Ba lần vào UVLO trong 10 s thì `fault_latch`.
- [ ] `arm` bật cờ, ghi RTC, xóa `fault_latch`, in `evt arm=1`. `disarm` tắt cờ, xóa fault, xóa AUX, xóa khóa còi.
- [ ] `config set` đúng khoảng mục 9.8. Ngoài khoảng thì `err range` và giữ số cũ. `oc_ma` tối đa 2500. Không có khóa `failsafe_ms`.
- [ ] `config save` chỉ với `horn_current_ma` và `shunt_cal`, chạy trên task console. Các hằng thời gian và ngưỡng bảo vệ không save, reset là về mục 8.2.
- [ ] LED trạng thái: `fault_latch` hoặc mất số đo nguồn thì ba nhịp 80 ms sáng / 80 ms tắt rồi nghỉ 800 ms.

Pass trên J1, một tải mỗi lần: `arm`, `debug on`, `hold <kênh> on`, đọc `gates`, đo dòng, `hold off`. Chưa arm thì `want_head` có thể khác 0 và `out_head=0`. Đối chiếu luật còi: `scenarios/portable/horn_budget.txt` phải ra `want_horn=1` và `out_horn=0` ở nửa kỳ trái tắt. `config set oc_ma 100` rồi bật một tải trên 100 mA cho `evt fault=1`. `arm` lại thì tải sáng. Reset thì `oc_ma` về 2500. Ba lần UVLO đã có trong `test_uvlo_three_trips_latch`.

## Phase 9 — Cảm biến còn lại

File: `imu.c`, `light.c`, `lidar.c`, `gps.c`, và phần lịch trong task `sensors`. Console thêm `inject`.

- [ ] BMI270 nhận init blob trước lần đọc đầu. INT1 push-pull, active-high, any-motion. Ngưỡng mg nằm trong cấu hình Bosch, không nằm trong `power_mode`.
- [ ] Xung mới thì `motion_until = now + 250 ms`. Hết hạn thì `motion` false.
- [ ] GPIO38 cao liên tục ≥ 120 s thì `motion_fault`. Cờ này không xóa `motion_since` và không làm mốc yên chạy. Chân xuống thấp thì xóa `motion_fault`.
- [ ] BH1750 một lần đo H-resolution mỗi 500 ms, không mỗi vòng 50 ms.
- [ ] VL53L1X continuous sau khi `XSHUT` cao và driver init xong. `obstacle` khi mẫu hợp lệ, tuổi < 500 ms, và `range_mm < 4000`. Bằng 4000 thì không. Bằng 0 hợp lệ thì có. Hết hạn thì `obstacle` false và `range_mm` là `0xFFFF`.
- [ ] GPS bỏ dòng dài hơn 128 hoặc sai checksum. Nhận RMC và GGA khi cờ fix đúng, vĩ độ trong ±90, kinh độ trong ±180, và không phải 0,0. Câu không hợp lệ hạ `gps_fix` nhưng giữ tọa độ. Tuổi ≥ 5000 ms thì hạ `gps_fix`. Baud trên 9600 chỉ sau khi đã nhận một câu hợp lệ.
- [ ] Lịch task `sensors`: INA228, BMI270, VL53L1X mỗi 50 ms. BH1750 mỗi 500 ms.
- [ ] `inject lux`, `inject motion`, `inject range`, `inject pin`, `inject clear motion`, `inject off` đúng bảng mục 9.7. Bơm không ghi đè `bus_mv`, `current_ma`, hay `power_valid`.
- [ ] `sense` in số của cảm biến và số sau bơm, kèm cờ đang bơm.
- [ ] `inject range 65535` trả `err range`.

Pass: `inject lux 99` rồi `150` rồi `201` đúng `portable/headlight.txt`. `inject range 3999` bật cờ, `4000` tắt cờ, `out_brake` không đổi, đúng `test_lidar_does_not_touch_brake`. GPS 0,0 hạ fix và giữ tọa độ, đúng `test_gps_rejects_origin`. `inject off` rồi che cảm biến sáng và đưa vật trong 4 m, `sense` khớp phần cứng. `inject` không làm `v=` đổi.

## Phase 10 — Mode, báo động, ngủ

File: `components/power/power_mode.c`, `components/security/alarm.c`, `motion.c`. Console thêm `ride`, `dismiss`, `aux`, `sleep`.

- [ ] `power_mode_step` cập nhật mốc theo `motion` thô rồi mới xét chuyển. Một nhịp một lần chuyển.
- [ ] Vào `PARKING`: đang chuyển động thì `motion_since = now` và `quiet_since = 0`, ngược lại thì ngược lại. `alarm_ready_at = now + alarm_gap_s` khi vào từ `RIDING` hoặc từ `ALARM`. Boot thì `alarm_ready_at = 0`.
- [ ] `RIDE_START` chỉ khi `PARKING`. `RIDING` hoặc `ALARM` thì `evt reject=ride_start mode` và mode không đổi.
- [ ] `RIDE_STOP` chỉ khi `RIDING`.
- [ ] `RIDING` về `PARKING` khi có `RIDE_STOP` hoặc yên đủ `stop_idle_s`. Không có nhánh `RIDING` sang `ALARM`.
- [ ] `PARKING` sang `ALARM` khi không `motion_fault`, `now_ms` đã tới `alarm_ready_at`, và `motion_since` đã chạy đủ `alarm_motion_ms`.
- [ ] `ALARM` về `PARKING` khi `DISMISS` hoặc đã đủ `alarm_s`.
- [ ] `DISMISS` ngoài `ALARM` chỉ xóa `fault_latch`.
- [ ] `alarm_policy` thay toàn bộ mức đèn và còi của nhịp. `elapsed = (now_ms - alarm_since_ms) % 1000`. Dưới 200 ms thì còi và `horn_from_alarm`. Dưới 500 ms thì bốn đèn duty 1023, hai cờ lit, và phanh. Phần còn lại của giây thì tắt. Công tắc còi và phanh không sửa chu kỳ này.
- [ ] AUX gắn sau chính sách, từ `aux_latch`, trừ khi `hold aux` đang ép.
- [ ] Xin ngủ khi `PARKING`, yên đủ `sleep_after_s`, và vị từ chân IMU thấp. Vị từ là GPIO38 thật, trừ khi `inject pin` đang bật.
- [ ] Giao dịch ngủ: ghi mức toàn 0 qua ống cổng ra kể cả khi đang arm, đặt `sleep_prepare`, thả mutex, chờ từng lát 10 ms, mỗi lát xoa failsafe. Có lệnh trong hàng, có `motion`, hoặc chân cao thì xóa cờ và `evt sleep=abort`.
- [ ] Task `sensors` thấy `sleep_prepare` thì kéo `XSHUT` thấp, giữ INT1, rồi xóa cờ. Hết 200 ms chưa thấy xóa thì `vehicle` tự kéo `XSHUT`.
- [ ] Trước khi ngủ: ghi CRC arm, `esp_sleep_enable_ext0_wakeup(GPIO38, 1)`, `esp_deep_sleep_start()`.
- [ ] `inject pin` không được truyền vào lời gọi ext0.
- [ ] Thức dậy chạy lại `app_main`, mode `PARKING`, AUX tắt, arm theo CRC.
- [ ] LED: sau lỗi nguồn là `ALARM` nhịp 100 ms, rồi mất cả bus I2C cùng nhịp đó, rồi `RIDING` sáng đều, rồi `PARKING` 50 ms mỗi 2 s. `motion_fault` dùng kiểu ba nhịp của lỗi nguồn.

Pass trên giả lập trước: `scenarios/portable/alarm_reject.txt`, `test_riding_motion_does_not_alarm`, `test_sleep_abort_keeps_queued_arm`, `test_deepsleep_keeps_arm_power_reset_clears_it`. Pass trên mạch sau: trong `debug on`, `config set stop_idle_s 5`, `alarm_s 2`, `alarm_gap_s 5`, `sleep_after_s 5`. `ride start` từ `PARKING` sang `RIDING`. `inject motion on` trong `RIDING` không sang `ALARM`. Ngủ thật bằng GPIO38, CRC đúng thì boot lại vẫn `armed=1` và mode `PARKING`. `inject pin` không đổi chân ext0.

## Phase 11 — BLE

File: `components/link/ble_status.c`, `snapshot.c`.

- [ ] Một service, base UUID `6b690000-0000-4000-8000-00805f9b34fb`. Characteristic `0001` read và notify. `0002` write.
- [ ] Gói 32 byte little-endian đúng bảng mục 6.10. Byte 25..31 bằng 0. `range_mm` không có mẫu là `0xFFFF`.
- [ ] Byte cờ: bit0 fix, bit1 obstacle, bit2 motion, bit3 armed, bit4 bus I2C chết, bit5 `fault_latch`, bit6 tải đang cấm, bit7 `motion_fault`.
- [ ] Byte đèn: bit0 pha, bit1 hậu, bit2 phanh, bit3 trái, bit4 phải, bit5 hazard, bit6 còi, bit7 aux. Các bit này phản ánh `out_*`, tức mức đã qua ống cổng ra.
- [ ] Notify mỗi 500 ms khi có kết nối. Deep sleep không notify.
- [ ] Write một byte. `0x01` đến `0x07` vào cùng queue với console. Byte khác bỏ, không chiếm chỗ queue.
- [ ] Callback BLE chỉ gửi queue timeout 0 rồi trả. Không đổi mode, không ghi GPIO, không ghi NVS.
- [ ] Lệnh `snapshot` in 32 byte hex. Khớp notify vừa đọc bằng nRF Connect hoặc script.

Pass: hex của lệnh `snapshot` trên mạch trùng hex giả lập với cùng mode, cờ và tải. `arm` trên console và write `0x04` từ điện thoại cùng tác động lên một cờ arm. Write `0x03` rồi `0x01` dồn trong một nhịp: nhịp đầu arm, nhịp sau `RIDING`. Write `0x00` không làm `cmd_dropped` tăng nếu hàng còn chỗ. Giả lập không phát sóng BLE.

## Phase 12 — Runner trên mạch

File đã có: `firmware/sim/runner.py`, `SerialSession` trong `firmware/sim/session.py`. Không viết một giao thức thứ hai. `bringup_log.py` nếu thêm thì chỉ gọi runner.

- [ ] Cài `pyserial` trên máy tính.
- [ ] `python3 -m sim.runner --port <cổng> scenarios/portable` trả `ok files=5`.
- [ ] `tick` trên serial là ngủ thật, không tua đồng hồ. File trong `plant/` không đưa vào lệnh này.
- [ ] Mã thoát khác 0 khi một `expect` thiếu. Log giữ dòng `ok`, `err`, `evt`.

Pass: năm file `portable/` xanh trên USB. Bốn địa chỉ I2C và đo gate vẫn thuộc phase 4 và phase 1, không lấy từ runner.

## Phase 13 — Ký bảng trường hợp

Ca logic đã có unittest hoặc file kịch bản thì oracle đã ký. Ô bên dưới vẫn để trống cho đến khi firmware trên mạch, hoặc log `--port`, ra cùng kết quả. Giả lập không ký hộ các ô đo điện, bốn địa chỉ I2C, và thức dậy bằng GPIO38 thật.

- [ ] Cấp nguồn, công tắc nhả: `PARKING`, arm tắt, gate thấp, `head_on` false.
- [ ] Deep sleep và CRC đúng: giữ arm, `PARKING`, AUX tắt.
- [ ] Reset watchdog hoặc cấp nguồn lại: arm tắt.
- [ ] Rung dưới 30 ms: `stable` không đổi.
- [ ] Đúng 30 ms cùng mức: `stable` nhận mức đó.
- [ ] Chỉ trái thấp: xi-nhan trái, không hazard.
- [ ] Trái và phải cùng thấp: hazard, hai duty cùng pha.
- [ ] Đổi trái sang phải giữa kỳ: pha không nhảy về 0.
- [ ] Chưa biết dòng còi, pha và hậu đang sáng, xi-nhan ở nửa kỳ tắt: `out_horn=0`.
- [ ] Chỉ đèn pha, chưa biết dòng còi: còi người lái được phép.
- [ ] Giữ còi đủ 30 s: tắt đến khi thả hẳn.
- [ ] Còi kẹt từ lúc boot: sau `arm` vẫn im đến khi có một lần stable cao.
- [ ] Lux 99 / 100 / 200 / 201: bật / giữ / giữ / tắt. Host.
- [ ] Mất lux từ 1 s: giữ `head_on`. `LIGHT_SW` vẫn ép bật và khi thả thì về `head_on` cũ.
- [ ] `PARKING`: hậu tắt. Phanh, xi-nhan, còi theo công tắc khi đã arm và không bị cấm.
- [ ] `RIDING` trong lúc `motion` true: không sang `ALARM`.
- [ ] `RIDING` yên đủ `stop_idle_s`: về `PARKING`.
- [ ] `RIDE_START` trong `ALARM`: reject, mode giữ nguyên.
- [ ] `DISMISS` trong `ALARM`: `PARKING` và `fault_latch` tắt.
- [ ] `DISMISS` khi không báo động: mode giữ, `fault_latch` tắt.
- [ ] Hết báo động mà `motion` vẫn true: lần sau chỉ sau `alarm_gap_s`.
- [ ] GPIO38 cao liên tục 120 s: `motion_fault`, không vào `ALARM`, không xin ngủ.
- [ ] Đã xin ngủ rồi có lệnh hoặc có `motion`: `evt sleep=abort`, nhịp sau chạy chính sách.
- [ ] Chờ `XSHUT` quá 200 ms: `vehicle` tự kéo thấp rồi vẫn ngủ.
- [ ] GPIO38 đang cao và không bơm pin: không có `evt sleep=enter`.
- [ ] Chưa arm: `out_*=0` dù `want_*` khác 0.
- [ ] Mất INA228 từ 200 ms: `inhibit=power`.
- [ ] Dòng trên 2500 mA đủ 100 ms, hoặc từ 3000 mA: `fault_latch`, tải tắt.
- [ ] Áp dưới 4200 mV đủ 50 ms: tắt đến khi áp từ 4600 mV đủ 200 ms.
- [ ] Ba lần sụt áp trong 10 s: `fault_latch` dù áp đã hồi.
- [ ] `arm` trong lúc `fault_latch`: khóa xóa, arm bật.
- [ ] LiDAR 3999 mm / 4000 mm / mất mẫu: cờ bật / tắt / tắt. `out_brake` không theo range.
- [ ] GPS checksum sai hoặc 0,0: giữ tọa độ cũ, `gps_fix=0`.
- [ ] Queue đầy: `err queue`, bốn lệnh cũ vẫn đúng thứ tự.
- [ ] `arm` rồi `ride start`: hai `evt`, không gộp một nhịp.
- [ ] Vòng `vehicle` không xoa failsafe trong 50 ms: gate 0 V.
- [ ] Vật trong 4 m: bit obstacle trong `snapshot`, không có cạnh tới GPIO13.

## Không viết trong bản này

- [ ] Client OTA. Partition `ota_0` và `ota_1` để trống.
- [ ] Wi-Fi, MQTT, socket.
- [ ] App điện thoại trong repo.
- [ ] CAN, camera, màn hình.
- [ ] Gán `obstacle` vào `brake` hoặc vào `BRAKE_GATE`.
- [ ] Bơm `bus_mv` hoặc `current_ma` từ console.
- [ ] Ghi NVS từ nhịp 10 ms.
