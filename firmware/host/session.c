#define _POSIX_C_SOURCE 200809L

#include "bike_ctrl.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *const HW_HELP[] = {
    "press/release <left|right|horn|light|brake|hazard>",
    "lux <0..65535>",
    "range <0..65534>|none",
    "motion on|off",
    "pin high|low",
    "power <mV>|dead|auto",
    "load <kênh> <mA>",
    "i2c <40|23|29|68> on|off",
    "gps <lat> <lon>|bad|none",
    "stall on|off",
    "reset power|wdt|deepsleep",
    "wake",
    "status",
};

static int digits(const char *text)
{
    if (text == NULL || text[0] == '\0') {
        return 0;
    }
    for (const char *p = text; *p != '\0'; p++) {
        if (*p < '0' || *p > '9') {
            return 0;
        }
    }
    return 1;
}

static int load_index(const char *name)
{
    const char *names[] = {"head", "tail", "left", "right", "brake", "horn", "aux"};
    for (int i = 0; i < 7; i++) {
        if (strcmp(name, names[i]) == 0) {
            return i;
        }
    }
    return -1;
}

static int switch_index(const char *name)
{
    const char *names[] = {"left", "right", "horn", "light", "brake", "hazard"};
    for (int i = 0; i < 6; i++) {
        if (strcmp(name, names[i]) == 0) {
            return i;
        }
    }
    return -1;
}

static int i2c_index(const char *text)
{
    if (strcmp(text, "40") == 0) {
        return BIKE_I2C_INA;
    }
    if (strcmp(text, "23") == 0) {
        return BIKE_I2C_LUX;
    }
    if (strcmp(text, "29") == 0) {
        return BIKE_I2C_LIDAR;
    }
    if (strcmp(text, "68") == 0) {
        return BIKE_I2C_IMU;
    }
    return -1;
}

static void one(bike_reply_t *out, const char *line)
{
    snprintf(out->text[0], BIKE_REPLY_LEN, "%s", line);
    out->count = 1;
}

void host_exec(const char *text, bike_reply_t *out)
{
    out->count = 0;
    if (strcmp(text, "hw help") == 0) {
        for (size_t i = 0; i < sizeof HW_HELP / sizeof HW_HELP[0]; i++) {
            snprintf(out->text[out->count], BIKE_REPLY_LEN, "ok hw=%s", HW_HELP[i]);
            out->count++;
        }
        return;
    }
    if (strcmp(text, "hw") == 0 || strncmp(text, "hw ", 3) == 0) {
        char buf[128];
        snprintf(buf, sizeof buf, "%s", text);
        char *argv[6];
        int argc = 0;
        char *save = NULL;
        for (char *tok = strtok_r(buf, " ", &save); tok != NULL && argc < 6; tok = strtok_r(NULL, " ", &save)) {
            argv[argc++] = tok;
        }
        if (argc < 2) {
            one(out, "err syntax");
            return;
        }
        bike_plant_t *plant = bike_plant();
        if (argc == 2 && strcmp(argv[1], "status") == 0) {
            char pressed[64] = "-";
            int n = 0;
            const char *names[] = {"left", "right", "horn", "light", "brake", "hazard"};
            for (int i = 0; i < 6; i++) {
                if (!plant->pressed[i]) {
                    continue;
                }
                n += snprintf(pressed + n, sizeof pressed - (size_t)n, "%s%s", n ? "," : "", names[i]);
            }
            if (n == 0) {
                snprintf(pressed, sizeof pressed, "-");
            }
            char range[16];
            if (plant->range_valid) {
                snprintf(range, sizeof range, "%u", plant->range_mm);
            } else {
                snprintf(range, sizeof range, "none");
            }
            snprintf(out->text[0], BIKE_REPLY_LEN,
                     "ok lux=%u range=%s motion=%d pin=%d bus_mv=%u power=%d pressed=%s",
                     plant->lux, range, plant->motion ? 1 : 0, plant->gpio38 ? 1 : 0, plant->bus_mv,
                     plant->power_alive ? 1 : 0, pressed);
            out->count = 1;
            return;
        }
        if (argc == 3 && strcmp(argv[1], "press") == 0) {
            int idx = switch_index(argv[2]);
            if (idx < 0) {
                one(out, "err syntax");
                return;
            }
            plant->pressed[idx] = true;
            one(out, "ok");
            return;
        }
        if (argc == 3 && strcmp(argv[1], "release") == 0) {
            int idx = switch_index(argv[2]);
            if (idx < 0) {
                one(out, "err syntax");
                return;
            }
            plant->pressed[idx] = false;
            one(out, "ok");
            return;
        }
        if (argc == 3 && strcmp(argv[1], "lux") == 0 && digits(argv[2])) {
            long value = strtol(argv[2], NULL, 10);
            if (value > 65535) {
                one(out, "err range");
                return;
            }
            plant->lux = (uint16_t)value;
            one(out, "ok");
            return;
        }
        if (argc == 3 && strcmp(argv[1], "range") == 0 && strcmp(argv[2], "none") == 0) {
            plant->range_valid = false;
            one(out, "ok");
            return;
        }
        if (argc == 3 && strcmp(argv[1], "range") == 0 && digits(argv[2])) {
            long value = strtol(argv[2], NULL, 10);
            if (value > 65534) {
                one(out, "err range");
                return;
            }
            plant->range_valid = true;
            plant->range_mm = (uint16_t)value;
            one(out, "ok");
            return;
        }
        if (argc == 3 && strcmp(argv[1], "motion") == 0 &&
            (strcmp(argv[2], "on") == 0 || strcmp(argv[2], "off") == 0)) {
            plant->motion = strcmp(argv[2], "on") == 0;
            one(out, "ok");
            return;
        }
        if (argc == 3 && strcmp(argv[1], "pin") == 0 &&
            (strcmp(argv[2], "high") == 0 || strcmp(argv[2], "low") == 0)) {
            plant->gpio38 = strcmp(argv[2], "high") == 0;
            one(out, "ok");
            return;
        }
        if (argc == 3 && strcmp(argv[1], "power") == 0 && strcmp(argv[2], "dead") == 0) {
            plant->power_alive = false;
            one(out, "ok");
            return;
        }
        if (argc == 3 && strcmp(argv[1], "power") == 0 && strcmp(argv[2], "auto") == 0) {
            plant->power_alive = true;
            plant->bus_mv = 4700;
            one(out, "ok");
            return;
        }
        if (argc == 3 && strcmp(argv[1], "power") == 0 && digits(argv[2])) {
            plant->power_alive = true;
            plant->bus_mv = (uint16_t)strtol(argv[2], NULL, 10);
            one(out, "ok");
            return;
        }
        if (argc == 4 && strcmp(argv[1], "load") == 0 && digits(argv[3])) {
            int idx = load_index(argv[2]);
            if (idx < 0) {
                one(out, "err syntax");
                return;
            }
            plant->loads_ma[idx] = (uint16_t)strtol(argv[3], NULL, 10);
            one(out, "ok");
            return;
        }
        if (argc == 4 && strcmp(argv[1], "i2c") == 0 &&
            (strcmp(argv[3], "on") == 0 || strcmp(argv[3], "off") == 0)) {
            int idx = i2c_index(argv[2]);
            if (idx < 0) {
                one(out, "err syntax");
                return;
            }
            plant->i2c[idx] = strcmp(argv[3], "on") == 0;
            one(out, "ok");
            return;
        }
        if (argc == 3 && strcmp(argv[1], "gps") == 0 &&
            (strcmp(argv[2], "bad") == 0 || strcmp(argv[2], "none") == 0)) {
            plant->gps_mode = strcmp(argv[2], "bad") == 0 ? BIKE_GPS_BAD : BIKE_GPS_NONE;
            one(out, "ok");
            return;
        }
        if (argc == 4 && strcmp(argv[1], "gps") == 0) {
            char *end_a = NULL;
            char *end_b = NULL;
            double lat = strtod(argv[2], &end_a);
            double lon = strtod(argv[3], &end_b);
            if (end_a == argv[2] || end_b == argv[3] || *end_a != '\0' || *end_b != '\0') {
                one(out, "err syntax");
                return;
            }
            plant->gps_lat = lat;
            plant->gps_lon = lon;
            plant->gps_mode = BIKE_GPS_FIX;
            one(out, "ok");
            return;
        }
        if (argc == 3 && strcmp(argv[1], "stall") == 0 &&
            (strcmp(argv[2], "on") == 0 || strcmp(argv[2], "off") == 0)) {
            bike_stall(strcmp(argv[2], "on") == 0);
            one(out, "ok");
            return;
        }
        if (argc == 3 && strcmp(argv[1], "reset") == 0) {
            int reason = -1;
            if (strcmp(argv[2], "power") == 0) {
                reason = BIKE_RESET_POWER;
            } else if (strcmp(argv[2], "wdt") == 0) {
                reason = BIKE_RESET_WDT;
            } else if (strcmp(argv[2], "deepsleep") == 0) {
                reason = BIKE_RESET_DEEPSLEEP;
            }
            if (reason < 0) {
                one(out, "err syntax");
                return;
            }
            bike_reset(reason, out);
            return;
        }
        if (argc == 2 && strcmp(argv[1], "wake") == 0) {
            plant->gpio38 = true;
            one(out, "ok");
            return;
        }
        one(out, "err syntax");
        return;
    }
    if (strcmp(text, "tick") == 0 || strncmp(text, "tick ", 5) == 0) {
        const char *arg = text + 4;
        while (*arg == ' ') {
            arg++;
        }
        if (!digits(arg)) {
            one(out, "err syntax");
            return;
        }
        bike_advance((uint32_t)strtoul(arg, NULL, 10), out);
        return;
    }
    bike_handle(text, out);
}
