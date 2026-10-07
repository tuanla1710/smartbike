#include "bike_ctrl.h"
#include "defaults.h"

#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define CFG_LIST(X) BIKE_CFG_LIST(X)

#define X_ENUM(name, value) CFG_##name,
enum { CFG_LIST(X_ENUM) CFG_COUNT };
#undef X_ENUM

#define X_NAME(name, value) #name,
static const char *const CFG_NAME[CFG_COUNT] = { CFG_LIST(X_NAME) };
#undef X_NAME

#define X_VAL(name, value) value,
static const int CFG_DEFAULT[CFG_COUNT] = { CFG_LIST(X_VAL) };
#undef X_VAL

enum {
    Q_NONE = 0,
    Q_RIDE_START = 1,
    Q_RIDE_STOP = 2,
    Q_ARM = 3,
    Q_DISARM = 4,
    Q_DISMISS = 5,
    Q_AUX_ON = 6,
    Q_AUX_OFF = 7,
    Q_SLEEP = 8
};

enum {
    MODE_PARKING = 0,
    MODE_RIDING,
    MODE_ALARM
};

enum {
    INHIBIT_NONE = 0,
    INHIBIT_DISARMED,
    INHIBIT_POWER,
    INHIBIT_UVLO,
    INHIBIT_OC,
    INHIBIT_FAULT
};

enum { HOLD_ON = 0, HOLD_OFF, HOLD_DUTY };

enum { CH_HEAD = 0, CH_TAIL, CH_LEFT, CH_RIGHT, CH_BRAKE, CH_HORN, CH_AUX, CH_N };

static const char *const MODE_NAME[] = {"parking", "riding", "alarm"};
static const char *const INHIBIT_NAME[] = {
    "none", "disarmed", "power", "uvlo", "oc", "fault"
};
static const uint8_t I2C_ADDR[BIKE_I2C_N] = {0x40, 0x23, 0x29, 0x68};

static const char *const HELP[] = {
    "help", "status", "inputs", "sense", "power", "gates", "faults", "config",
    "snapshot", "watch <ms>", "watch off", "arm", "disarm", "ride start",
    "ride stop", "dismiss", "aux on", "aux off", "debug on", "debug off",
    "hold <kênh> on|off|<duty>", "hold off", "inject lux <n>|off",
    "inject motion on|off", "inject clear motion", "inject range <mm>|off",
    "inject pin low|high|off", "inject off", "config set <tên> <số>",
    "config save horn_current_ma|shunt_cal", "sleep", "i2c"
};

typedef struct {
    bool used;
    int kind;
    int duty;
    uint32_t since;
} hold_t;

typedef struct {
    uint16_t head, tail, left, right;
    bool left_lit, right_lit;
    bool brake, horn, aux;
    bool horn_from_alarm;
} act_t;

typedef struct {
    bool candidate;
    bool stable;
    uint32_t candidate_since;
} sw_t;

static struct {
    bike_plant_t *plant;
    bike_hooks_t hooks;
    bike_emit_fn emit;
    void *emit_ctx;
    int cfg[CFG_COUNT];
    int nvs_horn;
    int nvs_shunt;
    uint32_t now;
    int mode;
    bool armed;
    uint8_t rtc_flag;
    uint8_t rtc_crc;
    bool fault_latch;
    bool debug;
    bool aux_latch;
    bool head_on;
    sw_t sw[5];
    uint8_t queue[4];
    uint8_t q_head;
    uint8_t q_len;
    int cmd_dropped;
    hold_t holds[CH_N];
    bool inj_lux_valid;
    uint16_t inj_lux;
    int8_t inj_motion;
    bool inj_range_valid;
    uint16_t inj_range;
    int8_t inj_pin;
    bool motion_since_valid;
    uint32_t motion_since;
    bool quiet_since_valid;
    uint32_t quiet_since;
    uint32_t alarm_since;
    uint32_t alarm_ready_at;
    bool motion_deadline_valid;
    uint32_t motion_deadline;
    bool pin_high_valid;
    uint32_t pin_high_since;
    bool motion_fault;
    bool horn_lockout;
    bool horn_since_valid;
    uint32_t horn_since;
    bool uvlo;
    bool uvlo_low_valid;
    uint32_t uvlo_low_since;
    bool uvlo_high_valid;
    uint32_t uvlo_high_since;
    uint32_t uvlo_trips[8];
    int uvlo_trip_n;
    int uvlo_count;
    bool oc_since_valid;
    uint32_t oc_since;
    int failsafe_count;
    bool stalled;
    bool failsafe_tripped;
    uint32_t last_kick;
    int sleep_phase;
    uint32_t sleep_since;
    bool xshut_high;
    bool sensors_saw_prepare;
    bool lux_valid;
    uint16_t lux_sample;
    uint32_t lux_ms;
    bool range_sample_valid;
    uint16_t range_sample;
    uint32_t range_ms;
    uint32_t power_ms;
    uint16_t bus_mv;
    int current_ma;
    uint32_t energy_mwh;
    int32_t lat_e7;
    int32_t lon_e7;
    bool gps_fix;
    bool gps_ms_valid;
    uint32_t gps_ms;
    bool scan_pending;
    bool asleep;
    act_t want;
    act_t out;
    int inhibit;
    bool motion;
    bool obstacle;
    uint16_t eff_lux;
    uint16_t eff_range;
    uint32_t watch_ms;
} g;

volatile uint32_t bike_kick_ms;
static atomic_flag q_flag = ATOMIC_FLAG_INIT;

static void q_lock(void)
{
    while (atomic_flag_test_and_set_explicit(&q_flag, memory_order_acquire)) {
    }
}

static void q_unlock(void)
{
    atomic_flag_clear_explicit(&q_flag, memory_order_release);
}

static int reply_room(const bike_reply_t *out)
{
    return out->count < BIKE_REPLY_LINES;
}

static int cfg(int id)
{
    return g.cfg[id];
}

static void say(bike_reply_t *out, const char *line, bool as_event)
{
    if (out != NULL && reply_room(out)) {
        snprintf(out->text[out->count], BIKE_REPLY_LEN, "%s", line);
        out->count++;
    }
    if (as_event && g.emit != NULL) {
        g.emit(line, g.emit_ctx);
    }
}

uint8_t bike_crc8(const uint8_t *data, size_t len)
{
    uint8_t crc = 0;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; bit++) {
            if ((crc & 0x80u) != 0) {
                crc = (uint8_t)((crc << 1) ^ 0x07u);
            } else {
                crc = (uint8_t)(crc << 1);
            }
        }
    }
    return crc;
}

static void store_rtc(void)
{
    uint8_t flag = g.armed ? 1u : 0u;
    g.rtc_flag = flag;
    g.rtc_crc = bike_crc8(&flag, 1);
}

static bool rtc_ok(void)
{
    return g.rtc_crc == bike_crc8(&g.rtc_flag, 1);
}

static act_t blank_act(void)
{
    act_t act;
    memset(&act, 0, sizeof act);
    return act;
}

static bool before_deadline(bool valid, uint32_t deadline, uint32_t span)
{
    if (!valid) {
        return false;
    }
    uint32_t remain = bike_elapsed(deadline, g.now);
    return remain > 0 && remain <= span;
}

static bool enqueue(uint8_t cmd)
{
    bool ok = false;
    q_lock();
    if (g.q_len >= 4) {
        g.cmd_dropped++;
    } else {
        uint8_t tail = (uint8_t)((g.q_head + g.q_len) % 4);
        g.queue[tail] = cmd;
        g.q_len++;
        ok = true;
    }
    q_unlock();
    return ok;
}

static uint8_t dequeue(void)
{
    uint8_t cmd = Q_NONE;
    q_lock();
    if (g.q_len > 0) {
        cmd = g.queue[g.q_head];
        g.q_head = (uint8_t)((g.q_head + 1) % 4);
        g.q_len--;
    }
    q_unlock();
    return cmd;
}

static bool queue_pending(void)
{
    bool pending;
    q_lock();
    pending = g.q_len > 0;
    q_unlock();
    return pending;
}

bool bike_enqueue_opcode(uint8_t opcode)
{
    if (opcode < Q_RIDE_START || opcode > Q_AUX_OFF) {
        return false;
    }
    return enqueue(opcode);
}

static void boot(bool armed)
{
    bike_plant_t *plant = g.plant;
    bike_hooks_t hooks = g.hooks;
    bike_emit_fn emit = g.emit;
    void *ctx = g.emit_ctx;
    int horn = g.nvs_horn;
    int shunt = g.nvs_shunt;
    memset(&g, 0, sizeof g);
    g.plant = plant;
    g.hooks = hooks;
    g.emit = emit;
    g.emit_ctx = ctx;
    g.nvs_horn = horn;
    g.nvs_shunt = shunt;
    for (int i = 0; i < CFG_COUNT; i++) {
        g.cfg[i] = CFG_DEFAULT[i];
    }
    g.cfg[CFG_horn_current_ma] = horn;
    g.cfg[CFG_shunt_cal] = shunt;
    g.mode = MODE_PARKING;
    g.armed = armed;
    store_rtc();
    g.quiet_since_valid = true;
    g.inj_motion = -1;
    g.inj_pin = -1;
    g.lux_valid = true;
    g.lux_sample = 500;
    g.eff_lux = 500;
    g.eff_range = 0xFFFF;
    g.bus_mv = 4700;
    g.inhibit = INHIBIT_DISARMED;
    bike_kick_ms = 0;
}

void bike_plant_init(bike_plant_t *plant)
{
    memset(plant, 0, sizeof *plant);
    plant->lux = 500;
    plant->bus_mv = 4700;
    plant->power_alive = true;
    for (int i = 0; i < BIKE_I2C_N; i++) {
        plant->i2c[i] = true;
    }
    plant->loads_ma[BIKE_LOAD_HEAD] = 200;
    plant->loads_ma[BIKE_LOAD_TAIL] = 80;
    plant->loads_ma[BIKE_LOAD_LEFT] = 80;
    plant->loads_ma[BIKE_LOAD_RIGHT] = 80;
    plant->loads_ma[BIKE_LOAD_BRAKE] = 80;
    plant->loads_ma[BIKE_LOAD_HORN] = 400;
}

void bike_setup(bike_plant_t *plant, bool armed)
{
    memset(&g, 0, sizeof g);
    g.plant = plant;
    g.nvs_horn = 0;
    g.nvs_shunt = 1250;
    boot(armed);
}

void bike_restore_saved(int horn_current_ma, int shunt_cal)
{
    g.nvs_horn = horn_current_ma;
    g.nvs_shunt = shunt_cal;
    g.cfg[CFG_horn_current_ma] = horn_current_ma;
    g.cfg[CFG_shunt_cal] = shunt_cal;
}

int bike_shunt_cal(void)
{
    return g.cfg[CFG_shunt_cal];
}

void bike_set_hooks(const bike_hooks_t *hooks)
{
    if (hooks == NULL) {
        memset(&g.hooks, 0, sizeof g.hooks);
        return;
    }
    g.hooks = *hooks;
}

void bike_set_emit(bike_emit_fn fn, void *ctx)
{
    g.emit = fn;
    g.emit_ctx = ctx;
}

void bike_mark(uint32_t now_ms)
{
    g.now = now_ms;
    g.last_kick = now_ms;
    bike_kick_ms = now_ms;
}

bike_plant_t *bike_plant(void)
{
    return g.plant;
}

bool bike_sleep_pending(void)
{
    return g.sleep_phase == 1;
}

uint32_t bike_watch_period(void)
{
    return g.watch_ms;
}

void bike_export_rtc(uint8_t *armed, uint8_t *crc)
{
    if (armed != NULL) {
        *armed = g.rtc_flag;
    }
    if (crc != NULL) {
        *crc = g.rtc_crc;
    }
}

void bike_stall(bool on)
{
    g.stalled = on;
    if (!on) {
        g.failsafe_tripped = false;
        g.last_kick = g.now;
        bike_kick_ms = g.now;
    }
}

static void set_mode(bike_reply_t *out, int mode)
{
    if (g.mode != mode) {
        g.mode = mode;
        char line[32];
        snprintf(line, sizeof line, "evt mode=%s", MODE_NAME[mode]);
        say(out, line, true);
    } else {
        g.mode = mode;
    }
}

static void set_armed(bike_reply_t *out, bool armed)
{
    if (g.armed != armed) {
        g.armed = armed;
        store_rtc();
        say(out, armed ? "evt arm=1" : "evt arm=0", true);
    } else {
        g.armed = armed;
        store_rtc();
    }
}

static void set_fault(bike_reply_t *out, bool fault)
{
    if (g.fault_latch != fault) {
        g.fault_latch = fault;
        say(out, fault ? "evt fault=1" : "evt fault=0", true);
    } else {
        g.fault_latch = fault;
    }
    if (!fault) {
        g.uvlo_trip_n = 0;
        g.oc_since_valid = false;
    }
}

static void set_inhibit(bike_reply_t *out, int reason)
{
    if (g.inhibit != reason) {
        g.inhibit = reason;
        char line[32];
        snprintf(line, sizeof line, "evt inhibit=%s", INHIBIT_NAME[reason]);
        say(out, line, true);
    } else {
        g.inhibit = reason;
    }
}

static void reject(bike_reply_t *out, const char *name)
{
    char line[48];
    snprintf(line, sizeof line, "evt reject=%s mode", name);
    say(out, line, true);
}

static bool switch_raw(int name)
{
    const bike_plant_t *plant = g.plant;
    if ((name == BIKE_SW_LEFT || name == BIKE_SW_RIGHT) && plant->pressed[BIKE_SW_HAZARD]) {
        return true;
    }
    return plant->pressed[name];
}

static bool power_valid(void)
{
    return bike_elapsed(g.now, g.power_ms) < (uint32_t)cfg(CFG_power_stale_ms);
}

static bool pin_low(void)
{
    if (g.inj_pin >= 0) {
        return g.inj_pin == 0;
    }
    return !g.plant->gpio38;
}

static void sample_gps(void)
{
    const bike_plant_t *plant = g.plant;
    if (plant->gps_mode == BIKE_GPS_FIX) {
        double lat = plant->gps_lat;
        double lon = plant->gps_lon;
        if (fabs(lat) <= 90.0 && fabs(lon) <= 180.0 && !(lat == 0.0 && lon == 0.0)) {
            g.lat_e7 = (int32_t)llround(lat * 1e7);
            g.lon_e7 = (int32_t)llround(lon * 1e7);
            g.gps_fix = true;
            g.gps_ms = g.now;
            g.gps_ms_valid = true;
        } else {
            g.gps_fix = false;
        }
    } else if (plant->gps_mode == BIKE_GPS_BAD) {
        g.gps_fix = false;
    }
    if (!g.gps_ms_valid || bike_elapsed(g.now, g.gps_ms) >= 5000u) {
        g.gps_fix = false;
    }
}

static void sample_world(void)
{
    bike_plant_t *plant = g.plant;
    if (plant->power_alive && plant->i2c[BIKE_I2C_INA]) {
        g.power_ms = g.now;
        g.bus_mv = plant->bus_mv;
    }
    if (plant->i2c[BIKE_I2C_LUX]) {
        g.lux_sample = plant->lux;
        g.lux_ms = g.now;
        g.lux_valid = true;
    }
    if (plant->i2c[BIKE_I2C_LIDAR] && plant->range_valid) {
        g.range_sample = plant->range_mm;
        g.range_ms = g.now;
        g.range_sample_valid = true;
    }
    bool source = plant->motion;
    if (g.inj_motion == 1) {
        source = true;
    } else if (g.inj_motion == 0) {
        source = false;
    }
    if (source) {
        g.motion_deadline = g.now + (uint32_t)cfg(CFG_motion_hold_ms);
        g.motion_deadline_valid = true;
    }
    g.motion = before_deadline(g.motion_deadline_valid, g.motion_deadline,
                               (uint32_t)cfg(CFG_motion_hold_ms));
    if (plant->gpio38) {
        if (!g.pin_high_valid) {
            g.pin_high_since = g.now;
            g.pin_high_valid = true;
        }
        if (bike_elapsed(g.now, g.pin_high_since) >= (uint32_t)cfg(CFG_motion_stuck_s) * 1000u) {
            g.motion_fault = true;
        }
    } else {
        g.pin_high_valid = false;
        g.motion_fault = false;
    }
    sample_gps();
}

static void sample_switches(void)
{
    uint32_t limit = (uint32_t)cfg(CFG_debounce_ms);
    for (int i = 0; i < 5; i++) {
        bool raw = switch_raw(i);
        if (raw != g.sw[i].candidate) {
            g.sw[i].candidate = raw;
            g.sw[i].candidate_since = g.now;
        } else if (bike_elapsed(g.now, g.sw[i].candidate_since) >= limit) {
            g.sw[i].stable = g.sw[i].candidate;
        }
    }
}

static void apply_side(bike_reply_t *out, uint8_t cmd)
{
    if (cmd == Q_ARM) {
        set_armed(out, true);
        set_fault(out, false);
    } else if (cmd == Q_DISARM) {
        set_armed(out, false);
        set_fault(out, false);
        g.aux_latch = false;
        g.horn_lockout = false;
        g.horn_since_valid = false;
    } else if (cmd == Q_AUX_ON) {
        g.aux_latch = true;
    } else if (cmd == Q_AUX_OFF) {
        g.aux_latch = false;
    } else if (cmd == Q_DISMISS && g.mode != MODE_ALARM) {
        set_fault(out, false);
    }
}

static void update_motion_marks(void)
{
    if (g.motion) {
        g.quiet_since_valid = false;
        if (!g.motion_since_valid) {
            g.motion_since = g.now;
            g.motion_since_valid = true;
        }
    } else {
        g.motion_since_valid = false;
        if (!g.quiet_since_valid) {
            g.quiet_since = g.now;
            g.quiet_since_valid = true;
        }
    }
}

static bool mark_age(bool valid, uint32_t mark, uint32_t *age)
{
    if (!valid) {
        return false;
    }
    *age = bike_elapsed(g.now, mark);
    return true;
}

static void enter_parking(bike_reply_t *out)
{
    g.alarm_ready_at = g.now + (uint32_t)cfg(CFG_alarm_gap_s) * 1000u;
    if (g.motion) {
        g.motion_since = g.now;
        g.motion_since_valid = true;
        g.quiet_since_valid = false;
    } else {
        g.motion_since_valid = false;
        g.quiet_since = g.now;
        g.quiet_since_valid = true;
    }
    set_mode(out, MODE_PARKING);
}

static void begin_sleep(bike_reply_t *out)
{
    g.sleep_phase = 1;
    g.sleep_since = g.now;
    g.sensors_saw_prepare = false;
    g.xshut_high = false;
    say(out, "evt sleep=start", true);
}

static void zero_outputs(bike_reply_t *out)
{
    g.want = blank_act();
    g.out = blank_act();
    set_inhibit(out, INHIBIT_NONE);
}

static void drive_xshut(bool high)
{
    g.xshut_high = high;
    if (g.hooks.xshut != NULL) {
        g.hooks.xshut(high);
    }
}

static void drive_outputs(void)
{
    if (g.hooks.apply == NULL) {
        return;
    }
    g.hooks.apply(g.out.head, g.out.tail, g.out.left, g.out.right,
                  g.out.brake, g.out.horn, g.out.aux);
}

static bool led_on(void)
{
    int present = 0;
    for (int i = 0; i < BIKE_I2C_N; i++) {
        if (g.plant->i2c[i]) {
            present++;
        }
    }
    bool fault_pat = g.fault_latch || !power_valid() || g.motion_fault;
    if (fault_pat) {
        uint32_t phase = g.now % 1280u;
        return phase < 480u && (phase % 160u) < 80u;
    }
    if (g.mode == MODE_ALARM || present == 0) {
        return ((g.now / 100u) % 2u) == 0u;
    }
    if (g.mode == MODE_RIDING) {
        return true;
    }
    return (g.now % 2000u) < 50u;
}

static void drive_led(void)
{
    if (g.hooks.led != NULL) {
        g.hooks.led(led_on());
    }
}

static void enter_deep_sleep(bike_reply_t *out, int mark)
{
    bool armed = g.armed;
    drive_xshut(false);
    boot(armed);
    g.asleep = true;
    if (out != NULL) {
        out->count = mark;
    }
    say(out, "evt sleep=enter", true);
    if (g.hooks.deep_sleep != NULL) {
        g.hooks.deep_sleep();
    }
}

static void sleep_slice(bike_reply_t *out, int mark)
{
    sample_switches();
    if (queue_pending() || g.motion || !pin_low()) {
        g.sleep_phase = 0;
        say(out, "evt sleep=abort", true);
        return;
    }
    if (!g.sensors_saw_prepare) {
        g.sensors_saw_prepare = true;
        drive_xshut(false);
    }
    uint32_t age = bike_elapsed(g.now, g.sleep_since);
    if (age >= 10u || age >= (uint32_t)cfg(CFG_sleep_ack_ms)) {
        enter_deep_sleep(out, mark);
    }
}

static void manual_sleep(bike_reply_t *out)
{
    if (g.mode != MODE_PARKING) {
        say(out, "evt sleep=abort mode", true);
        return;
    }
    if (g.motion) {
        say(out, "evt sleep=abort motion", true);
        return;
    }
    if (!pin_low()) {
        say(out, "evt sleep=abort pin", true);
        return;
    }
    begin_sleep(out);
}

static void mode_step(bike_reply_t *out, uint8_t cmd)
{
    update_motion_marks();
    if (cmd == Q_SLEEP) {
        manual_sleep(out);
        if (g.sleep_phase == 1) {
            return;
        }
    }
    if (g.mode == MODE_RIDING) {
        uint32_t quiet = 0;
        bool have = mark_age(g.quiet_since_valid, g.quiet_since, &quiet);
        if (cmd == Q_RIDE_STOP || (have && quiet >= (uint32_t)cfg(CFG_stop_idle_s) * 1000u)) {
            enter_parking(out);
            return;
        }
        if (cmd == Q_RIDE_START) {
            reject(out, "ride_start");
        }
        return;
    }
    if (g.mode == MODE_ALARM) {
        uint32_t age = bike_elapsed(g.now, g.alarm_since);
        if (cmd == Q_DISMISS || age >= (uint32_t)cfg(CFG_alarm_s) * 1000u) {
            set_fault(out, false);
            enter_parking(out);
            return;
        }
        if (cmd == Q_RIDE_START) {
            reject(out, "ride_start");
        }
        if (cmd == Q_RIDE_STOP) {
            reject(out, "ride_stop");
        }
        return;
    }
    if (cmd == Q_RIDE_START) {
        set_mode(out, MODE_RIDING);
        return;
    }
    if (cmd == Q_RIDE_STOP) {
        reject(out, "ride_stop");
        return;
    }
    uint32_t motion_age = 0;
    bool have_motion = mark_age(g.motion_since_valid, g.motion_since, &motion_age);
    if (!g.motion_fault && g.now >= g.alarm_ready_at && have_motion &&
        motion_age >= (uint32_t)cfg(CFG_alarm_motion_ms)) {
        g.alarm_since = g.now;
        set_mode(out, MODE_ALARM);
        return;
    }
    uint32_t quiet = 0;
    bool have_quiet = mark_age(g.quiet_since_valid, g.quiet_since, &quiet);
    if (have_quiet && quiet >= (uint32_t)cfg(CFG_sleep_after_s) * 1000u && pin_low()) {
        begin_sleep(out);
    }
}

static void effective_lux(uint16_t *lux, bool *ok)
{
    if (g.inj_lux_valid) {
        *lux = g.inj_lux;
        *ok = true;
        return;
    }
    if (!g.lux_valid) {
        *lux = 0;
        *ok = false;
        return;
    }
    if (bike_elapsed(g.now, g.lux_ms) >= (uint32_t)cfg(CFG_lux_stale_ms)) {
        *lux = g.lux_sample;
        *ok = false;
        return;
    }
    *lux = g.lux_sample;
    *ok = true;
}

static void effective_range(uint16_t *value, bool *ok)
{
    if (g.inj_range_valid) {
        *value = g.inj_range;
        *ok = true;
        return;
    }
    if (!g.range_sample_valid) {
        *value = 0;
        *ok = false;
        return;
    }
    if (bike_elapsed(g.now, g.range_ms) >= (uint32_t)cfg(CFG_range_stale_ms)) {
        *value = 0;
        *ok = false;
        return;
    }
    *value = g.range_sample;
    *ok = true;
}

static void fill_range(void)
{
    uint16_t value = 0;
    bool ok = false;
    effective_range(&value, &ok);
    if (!ok) {
        g.obstacle = false;
        g.eff_range = 0xFFFF;
        return;
    }
    g.eff_range = value;
    g.obstacle = value < (uint16_t)cfg(CFG_range_warn_mm);
}

static void fill_turn(act_t *act)
{
    uint32_t period = (uint32_t)cfg(CFG_blink_period_ms);
    bool phase_on = period > 0 && (g.now % period) < (uint32_t)cfg(CFG_blink_on_ms);
    bool left = g.sw[BIKE_SW_LEFT].stable;
    bool right = g.sw[BIKE_SW_RIGHT].stable;
    if (left && right) {
        act->left_lit = true;
        act->right_lit = true;
    } else if (left) {
        act->left_lit = true;
    } else if (right) {
        act->right_lit = true;
    }
    uint16_t duty = (uint16_t)cfg(CFG_on_duty);
    act->left = (act->left_lit && phase_on) ? duty : 0;
    act->right = (act->right_lit && phase_on) ? duty : 0;
}

static void fill_horn(act_t *act)
{
    bool held = g.sw[BIKE_SW_HORN].stable;
    act->horn_from_alarm = false;
    if (!held) {
        act->horn = false;
        g.horn_lockout = false;
        g.horn_since_valid = false;
        return;
    }
    if (g.horn_lockout) {
        act->horn = false;
        return;
    }
    if (!g.horn_since_valid) {
        g.horn_since = g.now;
        g.horn_since_valid = true;
    }
    if (bike_elapsed(g.now, g.horn_since) >= (uint32_t)cfg(CFG_horn_max_on_s) * 1000u) {
        g.horn_lockout = true;
        act->horn = false;
        return;
    }
    act->horn = true;
}

static act_t ride_policy(void)
{
    act_t act = blank_act();
    uint16_t lux = 0;
    bool lux_ok = false;
    effective_lux(&lux, &lux_ok);
    if (g.sw[BIKE_SW_LIGHT].stable) {
        act.head = (uint16_t)cfg(CFG_on_duty);
    } else {
        if (lux_ok) {
            if (lux < (uint16_t)cfg(CFG_lux_on)) {
                g.head_on = true;
            } else if (lux > (uint16_t)cfg(CFG_lux_off)) {
                g.head_on = false;
            }
        }
        act.head = g.head_on ? (uint16_t)cfg(CFG_on_duty) : 0;
    }
    if (lux_ok) {
        g.eff_lux = lux;
    }
    if (!lux_ok && !g.inj_lux_valid && g.lux_valid) {
        g.eff_lux = g.lux_sample;
    }
    act.tail = g.mode == MODE_RIDING ? (uint16_t)cfg(CFG_on_duty) : 0;
    act.brake = g.sw[BIKE_SW_BRAKE].stable;
    fill_turn(&act);
    fill_horn(&act);
    fill_range();
    return act;
}

static act_t alarm_policy(void)
{
    act_t act = blank_act();
    uint32_t period = (uint32_t)cfg(CFG_alarm_period_ms);
    uint32_t age = period == 0 ? 0 : bike_elapsed(g.now, g.alarm_since) % period;
    if (age < (uint32_t)cfg(CFG_alarm_horn_ms)) {
        act.horn = true;
        act.horn_from_alarm = true;
    }
    if (age < (uint32_t)cfg(CFG_alarm_lamp_ms)) {
        uint16_t duty = (uint16_t)cfg(CFG_on_duty);
        act.head = duty;
        act.tail = duty;
        act.left = duty;
        act.right = duty;
        act.left_lit = true;
        act.right_lit = true;
        act.brake = true;
    }
    fill_range();
    uint16_t lux = 0;
    bool lux_ok = false;
    effective_lux(&lux, &lux_ok);
    if (lux_ok && g.inj_lux_valid) {
        g.eff_lux = g.inj_lux;
    }
    return act;
}

static void apply_turn_hold(act_t *act, int name, const hold_t *hold)
{
    uint32_t period = (uint32_t)cfg(CFG_blink_period_ms);
    bool phase_on = period > 0 && (g.now % period) < (uint32_t)cfg(CFG_blink_on_ms);
    bool *lit = name == CH_LEFT ? &act->left_lit : &act->right_lit;
    uint16_t *duty = name == CH_LEFT ? &act->left : &act->right;
    if (hold->kind == HOLD_ON) {
        *lit = true;
        *duty = phase_on ? (uint16_t)cfg(CFG_on_duty) : 0;
    } else if (hold->kind == HOLD_OFF) {
        *lit = false;
        *duty = 0;
    } else {
        *duty = (uint16_t)hold->duty;
        *lit = hold->duty != 0;
    }
}

static void apply_holds(bike_reply_t *out, act_t *act)
{
    bool expired = false;
    for (int i = 0; i < CH_N; i++) {
        hold_t *hold = &g.holds[i];
        if (!hold->used) {
            continue;
        }
        if (bike_elapsed(g.now, hold->since) >= 30000u) {
            hold->used = false;
            expired = true;
            continue;
        }
        if (i == CH_LEFT || i == CH_RIGHT) {
            apply_turn_hold(act, i, hold);
        } else if (i == CH_HEAD || i == CH_TAIL) {
            uint16_t *duty = i == CH_HEAD ? &act->head : &act->tail;
            if (hold->kind == HOLD_ON) {
                *duty = (uint16_t)cfg(CFG_on_duty);
            } else if (hold->kind == HOLD_OFF) {
                *duty = 0;
            } else {
                *duty = (uint16_t)hold->duty;
            }
        } else if (hold->kind == HOLD_ON) {
            if (i == CH_BRAKE) {
                act->brake = true;
            } else if (i == CH_HORN) {
                act->horn = true;
                act->horn_from_alarm = false;
            } else {
                act->aux = true;
            }
        } else if (i == CH_BRAKE) {
            act->brake = false;
        } else if (i == CH_HORN) {
            act->horn = false;
        } else {
            act->aux = false;
        }
    }
    if (expired) {
        say(out, "evt hold=off", true);
    }
}

static void horn_budget(act_t *act)
{
    if (act->horn_from_alarm || cfg(CFG_horn_current_ma) != 0) {
        return;
    }
    if (act->head != 0 && act->tail != 0 && (act->left_lit || act->right_lit)) {
        act->horn = false;
    }
}

static int inhibit_reason(void)
{
    if (!power_valid()) {
        return INHIBIT_POWER;
    }
    if (g.fault_latch) {
        return INHIBIT_FAULT;
    }
    if (g.uvlo) {
        return INHIBIT_UVLO;
    }
    if (!g.armed) {
        return INHIBIT_DISARMED;
    }
    return INHIBIT_NONE;
}

static int load_current(void)
{
    if (g.plant->use_measured_i) {
        return g.plant->measured_ma;
    }
    const uint16_t duty[4] = {g.out.head, g.out.tail, g.out.left, g.out.right};
    const int idx[4] = {BIKE_LOAD_HEAD, BIKE_LOAD_TAIL, BIKE_LOAD_LEFT, BIKE_LOAD_RIGHT};
    int total = 0;
    for (int i = 0; i < 4; i++) {
        total += (int)(((uint32_t)g.plant->loads_ma[idx[i]] * duty[i]) / 1023u);
    }
    if (g.out.brake) {
        total += g.plant->loads_ma[BIKE_LOAD_BRAKE];
    }
    if (g.out.horn) {
        total += g.plant->loads_ma[BIKE_LOAD_HORN];
    }
    if (g.out.aux) {
        total += g.plant->loads_ma[BIKE_LOAD_AUX];
    }
    return total;
}

static void update_uvlo(bike_reply_t *out)
{
    if (!power_valid()) {
        g.uvlo_low_valid = false;
        g.uvlo_high_valid = false;
        return;
    }
    uint16_t bus = g.bus_mv;
    if (bus < (uint16_t)cfg(CFG_uvlo_mv)) {
        g.uvlo_high_valid = false;
        if (!g.uvlo_low_valid) {
            g.uvlo_low_since = g.now;
            g.uvlo_low_valid = true;
        }
        if (!g.uvlo && bike_elapsed(g.now, g.uvlo_low_since) >= (uint32_t)cfg(CFG_uvlo_enter_ms)) {
            g.uvlo = true;
            g.uvlo_count++;
            if (g.uvlo_trip_n < 8) {
                g.uvlo_trips[g.uvlo_trip_n++] = g.now;
            }
            uint32_t window = (uint32_t)cfg(CFG_uvlo_window_ms);
            int kept = 0;
            for (int i = 0; i < g.uvlo_trip_n; i++) {
                if (bike_elapsed(g.now, g.uvlo_trips[i]) <= window) {
                    g.uvlo_trips[kept++] = g.uvlo_trips[i];
                }
            }
            g.uvlo_trip_n = kept;
            if (g.uvlo_trip_n >= cfg(CFG_uvlo_trip_count)) {
                set_fault(out, true);
            }
        }
    } else if (bus >= (uint16_t)cfg(CFG_uvlo_recover_mv)) {
        g.uvlo_low_valid = false;
        if (!g.uvlo_high_valid) {
            g.uvlo_high_since = g.now;
            g.uvlo_high_valid = true;
        }
        if (g.uvlo && !g.fault_latch &&
            bike_elapsed(g.now, g.uvlo_high_since) >= (uint32_t)cfg(CFG_uvlo_exit_ms)) {
            g.uvlo = false;
        }
    } else {
        g.uvlo_low_valid = false;
        g.uvlo_high_valid = false;
    }
}

static void observe_power(bike_reply_t *out)
{
    if (!power_valid()) {
        g.current_ma = 0;
        return;
    }
    int raw = load_current();
    g.current_ma = raw;
    g.bus_mv = g.plant->bus_mv;
    int oc_i = raw < 0 ? 0 : raw;
    bool trip = oc_i >= cfg(CFG_oc_immediate_ma) ||
                (oc_i > cfg(CFG_oc_ma) && g.oc_since_valid &&
                 bike_elapsed(g.now, g.oc_since) >= (uint32_t)cfg(CFG_oc_ms));
    if (trip) {
        set_fault(out, true);
        g.out = blank_act();
        g.current_ma = 0;
        set_inhibit(out, INHIBIT_FAULT);
        drive_outputs();
    }
    if (power_valid() && g.current_ma > cfg(CFG_oc_ma)) {
        if (!g.oc_since_valid) {
            g.oc_since = g.now;
            g.oc_since_valid = true;
        }
    } else {
        g.oc_since_valid = false;
    }
    update_uvlo(out);
}

static void integrate_energy(void)
{
    int64_t delta = (int64_t)g.bus_mv * (int64_t)g.current_ma * 10;
    if (delta <= 0) {
        return;
    }
    uint64_t add = (uint64_t)delta / 3600000000000ULL;
    uint64_t sum = (uint64_t)g.energy_mwh + add;
    g.energy_mwh = sum > 0xFFFFFFFFULL ? 0xFFFFFFFFULL : (uint32_t)sum;
}

static void actuate(bike_reply_t *out)
{
    act_t want = g.mode == MODE_ALARM ? alarm_policy() : ride_policy();
    if (!g.holds[CH_AUX].used) {
        want.aux = g.aux_latch;
    }
    apply_holds(out, &want);
    g.want = want;
    horn_budget(&want);
    int reason = inhibit_reason();
    g.out = reason == INHIBIT_NONE ? want : blank_act();
    set_inhibit(out, reason);
    integrate_energy();
    drive_outputs();
    drive_led();
}

static void tick(bike_reply_t *out)
{
    int mark = out != NULL ? out->count : 0;
    sample_world();
    if (g.sleep_phase == 1) {
        sleep_slice(out, mark);
        drive_led();
        return;
    }
    sample_switches();
    uint8_t cmd = dequeue();
    apply_side(out, cmd);
    mode_step(out, cmd);
    if (g.sleep_phase == 1) {
        zero_outputs(out);
        drive_outputs();
        drive_led();
        return;
    }
    actuate(out);
    observe_power(out);
    if (g.scan_pending) {
        g.scan_pending = false;
        char line[64];
        int n = snprintf(line, sizeof line, "ok addr=");
        bool first = true;
        for (int i = 0; i < BIKE_I2C_N && n > 0 && n < (int)sizeof line; i++) {
            if (!g.plant->i2c[i]) {
                continue;
            }
            n += snprintf(line + n, sizeof line - (size_t)n, "%s%02x", first ? "" : ",", I2C_ADDR[i]);
            first = false;
        }
        say(out, line, true);
    }
}

static void run_at(uint32_t now, bike_reply_t *out)
{
    g.now = now;
    if (g.asleep) {
        if (!g.plant->gpio38) {
            return;
        }
        g.asleep = false;
        say(out, "evt wake=imu", true);
    }
    if (g.stalled) {
        if (!g.failsafe_tripped &&
            bike_elapsed(g.now, g.last_kick) >= (uint32_t)cfg(CFG_failsafe_ms)) {
            g.failsafe_tripped = true;
            g.failsafe_count++;
            g.out = blank_act();
            g.inhibit = INHIBIT_FAULT;
            drive_outputs();
        }
        return;
    }
    tick(out);
    g.last_kick = g.now;
    g.failsafe_tripped = false;
    bike_kick_ms = g.now;
}

void bike_advance(uint32_t ms, bike_reply_t *out)
{
    if (out != NULL) {
        out->count = 0;
    }
    if (ms > 3600000u) {
        say(out, "err range", false);
        return;
    }
    uint32_t steps = ms / 10u;
    for (uint32_t i = 0; i < steps; i++) {
        run_at(g.now + 10u, out);
    }
}

void bike_step(uint32_t now_ms, bike_reply_t *out)
{
    if (out != NULL) {
        out->count = 0;
    }
    run_at(now_ms, out);
}

void bike_reset(int reason, bike_reply_t *out)
{
    if (out != NULL) {
        out->count = 0;
    }
    bool armed = reason == BIKE_RESET_DEEPSLEEP && rtc_ok() && g.armed;
    boot(armed);
    g.asleep = false;
    say(out, "ok", false);
}

static bool all_digits(const char *text)
{
    if (text == NULL || text[0] == '\0') {
        return false;
    }
    for (const char *p = text; *p != '\0'; p++) {
        if (*p < '0' || *p > '9') {
            return false;
        }
    }
    return true;
}

static int split_line(const char *line, char parts[][32], int max_parts)
{
    int n = 0;
    const char *p = line;
    while (*p != '\0' && n < max_parts) {
        size_t len = 0;
        while (p[len] != '\0' && p[len] != ' ') {
            len++;
        }
        if (len == 0 || len >= 32) {
            return -1;
        }
        memcpy(parts[n], p, len);
        parts[n][len] = '\0';
        n++;
        p += len;
        if (*p == ' ') {
            p++;
            if (*p == '\0' || *p == ' ') {
                return -1;
            }
        }
    }
    if (*p != '\0') {
        return -1;
    }
    return n;
}

static int channel_of(const char *name)
{
    const char *names[CH_N] = {"head", "tail", "left", "right", "brake", "horn", "aux"};
    for (int i = 0; i < CH_N; i++) {
        if (strcmp(name, names[i]) == 0) {
            return i;
        }
    }
    return -1;
}

static bool settable(int id, int *lo, int *hi, bool *needs_debug, bool *saveable)
{
    struct {
        int id;
        int lo;
        int hi;
        bool debug;
        bool save;
    } table[] = {
        {CFG_horn_current_ma, 0, 5000, false, true},
        {CFG_shunt_cal, 1, 65535, false, true},
        {CFG_stop_idle_s, 5, 3600, true, false},
        {CFG_sleep_after_s, 5, 3600, true, false},
        {CFG_alarm_s, 1, 120, true, false},
        {CFG_alarm_gap_s, 0, 60, true, false},
        {CFG_alarm_motion_ms, 50, 5000, true, false},
        {CFG_debounce_ms, 0, 500, true, false},
        {CFG_oc_ma, 100, 2500, true, false},
        {CFG_uvlo_mv, 3000, 4500, true, false},
    };
    for (size_t i = 0; i < sizeof table / sizeof table[0]; i++) {
        if (table[i].id == id) {
            *lo = table[i].lo;
            *hi = table[i].hi;
            *needs_debug = table[i].debug;
            *saveable = table[i].save;
            return true;
        }
    }
    return false;
}

static int cfg_index(const char *name)
{
    for (int i = 0; i < CFG_COUNT; i++) {
        if (strcmp(CFG_NAME[i], name) == 0) {
            return i;
        }
    }
    return -1;
}

static void clear_inject(void)
{
    g.inj_lux_valid = false;
    g.inj_motion = -1;
    g.inj_range_valid = false;
    g.inj_pin = -1;
}

static void reply_ok(bike_reply_t *out)
{
    say(out, "ok", false);
}

static void reply_queued(bike_reply_t *out, uint8_t cmd)
{
    say(out, enqueue(cmd) ? "ok queued" : "err queue", false);
}

static void format_status(char *dst, size_t n)
{
    snprintf(dst, n,
             "ok mode=%s armed=%d fault=%d uvlo=%d inhibit=%s debug=%d v=%u i=%d lux=%u range=%u motion=%d",
             MODE_NAME[g.mode], g.armed ? 1 : 0, g.fault_latch ? 1 : 0, g.uvlo ? 1 : 0,
             INHIBIT_NAME[g.inhibit], g.debug ? 1 : 0, g.bus_mv, g.current_ma, g.eff_lux,
             g.eff_range, g.motion ? 1 : 0);
}

static void format_inputs(char *dst, size_t n)
{
    const char *names[5] = {"left", "right", "horn", "light", "brake"};
    int used = snprintf(dst, n, "ok");
    for (int i = 0; i < 5 && used > 0 && (size_t)used < n; i++) {
        used += snprintf(dst + used, n - (size_t)used, " raw_%s=%d stable_%s=%d",
                         names[i], switch_raw(i) ? 1 : 0, names[i], g.sw[i].stable ? 1 : 0);
    }
    int hazard = g.sw[BIKE_SW_LEFT].stable && g.sw[BIKE_SW_RIGHT].stable;
    if (used > 0 && (size_t)used < n) {
        snprintf(dst + used, n - (size_t)used, " hazard=%d", hazard);
    }
}

static void format_sense(char *dst, size_t n)
{
    char addr[32] = "";
    int used = 0;
    for (int i = 0; i < BIKE_I2C_N; i++) {
        if (!g.plant->i2c[i]) {
            continue;
        }
        used += snprintf(addr + used, sizeof addr - (size_t)used, "%s%02x", used ? "," : "", I2C_ADDR[i]);
    }
    int lux_age = g.lux_valid ? (int)bike_elapsed(g.now, g.lux_ms) : -1;
    int range_age = g.range_sample_valid ? (int)bike_elapsed(g.now, g.range_ms) : -1;
    int power_age = (int)bike_elapsed(g.now, g.power_ms);
    char inj[32] = "";
    int iu = 0;
    if (g.inj_lux_valid) {
        iu += snprintf(inj + iu, sizeof inj - (size_t)iu, "lux");
    }
    if (g.inj_motion >= 0) {
        iu += snprintf(inj + iu, sizeof inj - (size_t)iu, "%smotion", iu ? "," : "");
    }
    if (g.inj_range_valid) {
        iu += snprintf(inj + iu, sizeof inj - (size_t)iu, "%srange", iu ? "," : "");
    }
    if (g.inj_pin >= 0) {
        snprintf(inj + iu, sizeof inj - (size_t)iu, "%spin", iu ? "," : "");
    }
    unsigned sensor_range = g.range_sample_valid ? g.range_sample : 0xFFFFu;
    unsigned sensor_lux = g.lux_valid ? g.lux_sample : 0;
    snprintf(dst, n,
             "ok addr=%s lux=%u lux_eff=%u range=%u range_eff=%u lux_age=%d range_age=%d power_age=%d gps_fix=%d inj=%s",
             addr, sensor_lux, g.eff_lux, sensor_range, g.eff_range, lux_age, range_age, power_age,
             g.gps_fix ? 1 : 0, inj);
}

static void format_power(char *dst, size_t n)
{
    int power_dw = (int)(((int32_t)g.bus_mv * g.current_ma) / 100000);
    snprintf(dst, n, "ok bus_mv=%u current_ma=%d power_dw=%d energy_mwh=%u power_valid=%d",
             g.bus_mv, g.current_ma, power_dw, (unsigned)g.energy_mwh, power_valid() ? 1 : 0);
}

static void format_gates(char *dst, size_t n)
{
    const char *names[CH_N] = {"head", "tail", "left", "right", "brake", "horn", "aux"};
    int want[CH_N] = {g.want.head, g.want.tail, g.want.left, g.want.right,
                      g.want.brake, g.want.horn, g.want.aux};
    int outv[CH_N] = {g.out.head, g.out.tail, g.out.left, g.out.right,
                      g.out.brake, g.out.horn, g.out.aux};
    int used = snprintf(dst, n, "ok");
    for (int i = 0; i < CH_N && used > 0 && (size_t)used < n; i++) {
        used += snprintf(dst + used, n - (size_t)used, " want_%s=%d", names[i], want[i]);
    }
    for (int i = 0; i < CH_N && used > 0 && (size_t)used < n; i++) {
        used += snprintf(dst + used, n - (size_t)used, " out_%s=%d", names[i], outv[i]);
    }
}

static void format_faults(char *dst, size_t n)
{
    snprintf(dst, n,
             "ok fault_latch=%d uvlo_count=%d cmd_dropped=%d failsafe_count=%d motion_fault=%d horn_lockout=%d",
             g.fault_latch ? 1 : 0, g.uvlo_count, g.cmd_dropped, g.failsafe_count,
             g.motion_fault ? 1 : 0, g.horn_lockout ? 1 : 0);
}

static void format_config(char *dst, size_t n)
{
    int used = snprintf(dst, n, "ok");
    for (int i = 0; i < CFG_COUNT && used > 0 && (size_t)used < n; i++) {
        used += snprintf(dst + used, n - (size_t)used, " %s=%d", CFG_NAME[i], g.cfg[i]);
    }
}

void bike_pack_snapshot(uint8_t raw[32])
{
    memset(raw, 0, 32);
    raw[0] = (uint8_t)(g.mode + 1);
    if (g.gps_fix) {
        raw[1] |= 1u << 0;
    }
    if (g.obstacle) {
        raw[1] |= 1u << 1;
    }
    if (g.motion) {
        raw[1] |= 1u << 2;
    }
    if (g.armed) {
        raw[1] |= 1u << 3;
    }
    int present = 0;
    for (int i = 0; i < BIKE_I2C_N; i++) {
        present += g.plant->i2c[i] ? 1 : 0;
    }
    if (present < 4) {
        raw[1] |= 1u << 4;
    }
    if (g.fault_latch) {
        raw[1] |= 1u << 5;
    }
    if (g.inhibit != INHIBIT_NONE) {
        raw[1] |= 1u << 6;
    }
    if (g.motion_fault) {
        raw[1] |= 1u << 7;
    }
    raw[2] = (uint8_t)(g.eff_lux & 0xFF);
    raw[3] = (uint8_t)((g.eff_lux >> 8) & 0xFF);
    raw[4] = (uint8_t)(g.eff_range & 0xFF);
    raw[5] = (uint8_t)((g.eff_range >> 8) & 0xFF);
    uint32_t lat = (uint32_t)g.lat_e7;
    uint32_t lon = (uint32_t)g.lon_e7;
    for (int i = 0; i < 4; i++) {
        raw[6 + i] = (uint8_t)((lat >> (8 * i)) & 0xFF);
        raw[10 + i] = (uint8_t)((lon >> (8 * i)) & 0xFF);
    }
    raw[14] = (uint8_t)(g.bus_mv & 0xFF);
    raw[15] = (uint8_t)((g.bus_mv >> 8) & 0xFF);
    int current = g.current_ma;
    if (current > 32767) {
        current = 32767;
    } else if (current < -32768) {
        current = -32768;
    }
    int power_dw = (int)(((int32_t)g.bus_mv * g.current_ma) / 100000);
    if (power_dw > 32767) {
        power_dw = 32767;
    } else if (power_dw < -32768) {
        power_dw = -32768;
    }
    raw[16] = (uint8_t)(current & 0xFF);
    raw[17] = (uint8_t)((current >> 8) & 0xFF);
    raw[18] = (uint8_t)(power_dw & 0xFF);
    raw[19] = (uint8_t)((power_dw >> 8) & 0xFF);
    for (int i = 0; i < 4; i++) {
        raw[20 + i] = (uint8_t)((g.energy_mwh >> (8 * i)) & 0xFF);
    }
    if (g.out.head) {
        raw[24] |= 1u << 0;
    }
    if (g.out.tail) {
        raw[24] |= 1u << 1;
    }
    if (g.out.brake) {
        raw[24] |= 1u << 2;
    }
    if (g.out.left) {
        raw[24] |= 1u << 3;
    }
    if (g.out.right) {
        raw[24] |= 1u << 4;
    }
    if (g.sw[BIKE_SW_LEFT].stable && g.sw[BIKE_SW_RIGHT].stable) {
        raw[24] |= 1u << 5;
    }
    if (g.out.horn) {
        raw[24] |= 1u << 6;
    }
    if (g.out.aux) {
        raw[24] |= 1u << 7;
    }
}

static void format_snapshot(char *dst, size_t n)
{
    uint8_t raw[32];
    bike_pack_snapshot(raw);
    char hex[80];
    int h = 0;
    for (int i = 0; i < 32 && h < (int)sizeof hex; i++) {
        h += snprintf(hex + h, sizeof hex - (size_t)h, "%02x", raw[i]);
    }
    snprintf(dst, n, "ok hex=%s", hex);
}

static void do_hold(bike_reply_t *out, char parts[][32], int n)
{
    if (!g.debug) {
        say(out, "err debug", false);
        return;
    }
    if (n == 2 && strcmp(parts[1], "off") == 0) {
        memset(g.holds, 0, sizeof g.holds);
        reply_ok(out);
        return;
    }
    if (n != 3) {
        say(out, "err syntax", false);
        return;
    }
    int ch = channel_of(parts[1]);
    if (ch < 0) {
        say(out, "err syntax", false);
        return;
    }
    bool gpio = ch == CH_BRAKE || ch == CH_HORN || ch == CH_AUX;
    const char *how = parts[2];
    if (gpio && strcmp(how, "on") != 0 && strcmp(how, "off") != 0) {
        say(out, "err syntax", false);
        return;
    }
    hold_t hold;
    memset(&hold, 0, sizeof hold);
    hold.used = true;
    hold.since = g.now;
    if (strcmp(how, "on") == 0) {
        hold.kind = HOLD_ON;
        hold.duty = cfg(CFG_on_duty);
    } else if (strcmp(how, "off") == 0) {
        hold.kind = HOLD_OFF;
    } else if (!gpio && all_digits(how)) {
        long duty = strtol(how, NULL, 10);
        if (duty > 1023) {
            say(out, "err range", false);
            return;
        }
        hold.kind = HOLD_DUTY;
        hold.duty = (int)duty;
    } else {
        say(out, "err syntax", false);
        return;
    }
    g.holds[ch] = hold;
    reply_ok(out);
}

static void do_inject(bike_reply_t *out, char parts[][32], int n)
{
    if (!g.debug) {
        say(out, "err debug", false);
        return;
    }
    if (n == 2 && strcmp(parts[1], "off") == 0) {
        clear_inject();
        reply_ok(out);
        return;
    }
    if (n == 3 && strcmp(parts[1], "clear") == 0 && strcmp(parts[2], "motion") == 0) {
        g.inj_motion = -1;
        reply_ok(out);
        return;
    }
    if (n != 3) {
        say(out, "err syntax", false);
        return;
    }
    if (strcmp(parts[1], "lux") == 0 && strcmp(parts[2], "off") == 0) {
        g.inj_lux_valid = false;
        reply_ok(out);
        return;
    }
    if (strcmp(parts[1], "lux") == 0 && all_digits(parts[2])) {
        long number = strtol(parts[2], NULL, 10);
        if (number > 65535) {
            say(out, "err range", false);
            return;
        }
        g.inj_lux = (uint16_t)number;
        g.inj_lux_valid = true;
        reply_ok(out);
        return;
    }
    if (strcmp(parts[1], "motion") == 0 && (strcmp(parts[2], "on") == 0 || strcmp(parts[2], "off") == 0)) {
        g.inj_motion = strcmp(parts[2], "on") == 0 ? 1 : 0;
        reply_ok(out);
        return;
    }
    if (strcmp(parts[1], "range") == 0 && strcmp(parts[2], "off") == 0) {
        g.inj_range_valid = false;
        reply_ok(out);
        return;
    }
    if (strcmp(parts[1], "range") == 0 && all_digits(parts[2])) {
        long number = strtol(parts[2], NULL, 10);
        if (number > 65534) {
            say(out, "err range", false);
            return;
        }
        g.inj_range = (uint16_t)number;
        g.inj_range_valid = true;
        reply_ok(out);
        return;
    }
    if (strcmp(parts[1], "pin") == 0 &&
        (strcmp(parts[2], "low") == 0 || strcmp(parts[2], "high") == 0 || strcmp(parts[2], "off") == 0)) {
        if (strcmp(parts[2], "off") == 0) {
            g.inj_pin = -1;
        } else {
            g.inj_pin = strcmp(parts[2], "high") == 0 ? 1 : 0;
        }
        reply_ok(out);
        return;
    }
    say(out, "err syntax", false);
}

static void do_config(bike_reply_t *out, char parts[][32], int n)
{
    if (n == 4 && strcmp(parts[1], "set") == 0 && all_digits(parts[3])) {
        int id = cfg_index(parts[2]);
        int lo = 0;
        int hi = 0;
        bool needs_debug = false;
        bool saveable = false;
        if (id < 0 || !settable(id, &lo, &hi, &needs_debug, &saveable)) {
            say(out, "err syntax", false);
            return;
        }
        if (needs_debug && !g.debug) {
            say(out, "err debug", false);
            return;
        }
        long number = strtol(parts[3], NULL, 10);
        if (number < lo || number > hi) {
            say(out, "err range", false);
            return;
        }
        g.cfg[id] = (int)number;
        reply_ok(out);
        return;
    }
    if (n == 3 && strcmp(parts[1], "save") == 0) {
        if (strcmp(parts[2], "horn_current_ma") != 0 && strcmp(parts[2], "shunt_cal") != 0) {
            say(out, "err syntax", false);
            return;
        }
        int value = strcmp(parts[2], "horn_current_ma") == 0 ? cfg(CFG_horn_current_ma) : cfg(CFG_shunt_cal);
        if (g.hooks.nvs_save != NULL && g.hooks.nvs_save(parts[2], value) != 0) {
            say(out, "err nvs", false);
            return;
        }
        if (strcmp(parts[2], "horn_current_ma") == 0) {
            g.nvs_horn = value;
        } else {
            g.nvs_shunt = value;
        }
        reply_ok(out);
        return;
    }
    say(out, "err syntax", false);
}

void bike_handle(const char *line, bike_reply_t *out)
{
    if (out != NULL) {
        out->count = 0;
    }
    if (line == NULL || strlen(line) > 80 || strstr(line, "  ") != NULL) {
        say(out, "err syntax", false);
        return;
    }
    char parts[6][32];
    int n = split_line(line, parts, 6);
    if (n <= 0) {
        say(out, "err syntax", false);
        return;
    }
    char scratch[BIKE_REPLY_LEN];
    if (n == 1 && strcmp(parts[0], "help") == 0) {
        for (size_t i = 0; i < sizeof HELP / sizeof HELP[0]; i++) {
            snprintf(scratch, sizeof scratch, "ok cmd=%s", HELP[i]);
            say(out, scratch, false);
        }
        return;
    }
    if (n == 1 && strcmp(parts[0], "status") == 0) {
        format_status(scratch, sizeof scratch);
        say(out, scratch, false);
        return;
    }
    if (n == 1 && strcmp(parts[0], "inputs") == 0) {
        format_inputs(scratch, sizeof scratch);
        say(out, scratch, false);
        return;
    }
    if (n == 1 && strcmp(parts[0], "sense") == 0) {
        format_sense(scratch, sizeof scratch);
        say(out, scratch, false);
        return;
    }
    if (n == 1 && strcmp(parts[0], "power") == 0) {
        format_power(scratch, sizeof scratch);
        say(out, scratch, false);
        return;
    }
    if (n == 1 && strcmp(parts[0], "gates") == 0) {
        format_gates(scratch, sizeof scratch);
        say(out, scratch, false);
        return;
    }
    if (n == 1 && strcmp(parts[0], "faults") == 0) {
        format_faults(scratch, sizeof scratch);
        say(out, scratch, false);
        return;
    }
    if (n == 1 && strcmp(parts[0], "config") == 0) {
        format_config(scratch, sizeof scratch);
        say(out, scratch, false);
        return;
    }
    if (n == 1 && strcmp(parts[0], "snapshot") == 0) {
        format_snapshot(scratch, sizeof scratch);
        say(out, scratch, false);
        return;
    }
    if (n == 2 && strcmp(parts[0], "watch") == 0 && strcmp(parts[1], "off") == 0) {
        g.watch_ms = 0;
        reply_ok(out);
        return;
    }
    if (n == 2 && strcmp(parts[0], "watch") == 0 && all_digits(parts[1])) {
        long ms = strtol(parts[1], NULL, 10);
        if (ms < 100 || ms > 5000) {
            say(out, "err range", false);
            return;
        }
        g.watch_ms = (uint32_t)ms;
        reply_ok(out);
        return;
    }
    if (n == 2 && strcmp(parts[0], "debug") == 0 &&
        (strcmp(parts[1], "on") == 0 || strcmp(parts[1], "off") == 0)) {
        g.debug = strcmp(parts[1], "on") == 0;
        if (!g.debug) {
            memset(g.holds, 0, sizeof g.holds);
            clear_inject();
        }
        reply_ok(out);
        return;
    }
    if (strcmp(parts[0], "hold") == 0) {
        do_hold(out, parts, n);
        return;
    }
    if (strcmp(parts[0], "inject") == 0) {
        do_inject(out, parts, n);
        return;
    }
    if (strcmp(parts[0], "config") == 0 && n >= 2) {
        do_config(out, parts, n);
        return;
    }
    if (n == 1 && strcmp(parts[0], "i2c") == 0) {
        g.scan_pending = true;
        say(out, "ok queued", false);
        return;
    }
    if (n == 1 && strcmp(parts[0], "sleep") == 0) {
        if (!g.debug) {
            say(out, "err debug", false);
            return;
        }
        reply_queued(out, Q_SLEEP);
        return;
    }
    if (n == 1 && strcmp(parts[0], "arm") == 0) {
        reply_queued(out, Q_ARM);
        return;
    }
    if (n == 1 && strcmp(parts[0], "disarm") == 0) {
        reply_queued(out, Q_DISARM);
        return;
    }
    if (n == 2 && strcmp(parts[0], "ride") == 0 && strcmp(parts[1], "start") == 0) {
        reply_queued(out, Q_RIDE_START);
        return;
    }
    if (n == 2 && strcmp(parts[0], "ride") == 0 && strcmp(parts[1], "stop") == 0) {
        reply_queued(out, Q_RIDE_STOP);
        return;
    }
    if (n == 1 && strcmp(parts[0], "dismiss") == 0) {
        reply_queued(out, Q_DISMISS);
        return;
    }
    if (n == 2 && strcmp(parts[0], "aux") == 0 && strcmp(parts[1], "on") == 0) {
        reply_queued(out, Q_AUX_ON);
        return;
    }
    if (n == 2 && strcmp(parts[0], "aux") == 0 && strcmp(parts[1], "off") == 0) {
        reply_queued(out, Q_AUX_OFF);
        return;
    }
    say(out, "err syntax", false);
}
