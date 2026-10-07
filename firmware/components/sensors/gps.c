#include "gps.h"

#include "bike_ctrl.h"
#include "bike_port.h"
#include "bike_types.h"
#include "board.h"

#include "driver/uart.h"
#include "esp_task_wdt.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <ctype.h>
#include <stdlib.h>
#include <string.h>

static int hex_byte(const char *text)
{
    if (!isxdigit((unsigned char)text[0]) || !isxdigit((unsigned char)text[1])) {
        return -1;
    }
    return (int)strtol(text, NULL, 16);
}

static bool checksum_ok(const char *line)
{
    if (line[0] != '$') {
        return false;
    }
    const char *star = strchr(line, '*');
    if (star == NULL) {
        return false;
    }
    int expect = hex_byte(star + 1);
    if (expect < 0) {
        return false;
    }
    uint8_t crc = 0;
    for (const char *p = line + 1; p < star; p++) {
        crc ^= (uint8_t)*p;
    }
    return crc == (uint8_t)expect;
}

static double nmea_deg(const char *field, char hemi)
{
    char *end = NULL;
    double raw = strtod(field, &end);
    if (end == field) {
        return 0.0;
    }
    int deg = (int)(raw / 100.0);
    double minutes = raw - (double)deg * 100.0;
    double dec = (double)deg + minutes / 60.0;
    if (hemi == 'S' || hemi == 'W') {
        dec = -dec;
    }
    return dec;
}

static void apply_fix(double lat, double lon, bool valid)
{
    bike_port_lock();
    bike_plant_t *plant = bike_plant();
    if (valid) {
        plant->gps_lat = lat;
        plant->gps_lon = lon;
        plant->gps_mode = BIKE_GPS_FIX;
    } else {
        plant->gps_mode = BIKE_GPS_BAD;
    }
    bike_port_unlock();
}

static void parse_line(char *line)
{
    if (!checksum_ok(line)) {
        apply_fix(0, 0, false);
        return;
    }
    char *star = strchr(line, '*');
    if (star != NULL) {
        *star = '\0';
    }
    char *field[16];
    int n = 0;
    field[n++] = line;
    for (char *p = line; *p != '\0' && n < 16; p++) {
        if (*p == ',') {
            *p = '\0';
            field[n++] = p + 1;
        }
    }
    bool rmc = strstr(field[0], "RMC") != NULL;
    bool gga = strstr(field[0], "GGA") != NULL;
    if (rmc && n >= 7) {
        bool active = field[2][0] == 'A';
        apply_fix(nmea_deg(field[3], field[4][0]), nmea_deg(field[5], field[6][0]), active);
        return;
    }
    if (gga && n >= 7) {
        bool active = field[6][0] >= '1' && field[6][0] <= '9';
        apply_fix(nmea_deg(field[2], field[3][0]), nmea_deg(field[4], field[5][0]), active);
    }
}

static void gps_task(void *arg)
{
    (void)arg;
    uart_config_t cfg = {
        .baud_rate = 9600,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    uart_driver_install(UART_NUM_1, 512, 0, 0, NULL, 0);
    uart_param_config(UART_NUM_1, &cfg);
    uart_set_pin(UART_NUM_1, BOARD_GPS_TX, BOARD_GPS_RX, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    esp_task_wdt_add(NULL);

    char line[128];
    int len = 0;
    bool drop = false;
    for (;;) {
        uint8_t byte = 0;
        int got = uart_read_bytes(UART_NUM_1, &byte, 1, pdMS_TO_TICKS(100));
        esp_task_wdt_reset();
        if (got <= 0) {
            bike_port_lock();
            if (bike_plant()->gps_mode != BIKE_GPS_NONE) {
                bike_plant()->gps_mode = BIKE_GPS_NONE;
            }
            bike_port_unlock();
            continue;
        }
        if (byte == '\r') {
            continue;
        }
        if (byte == '\n') {
            if (!drop && len > 0) {
                line[len] = '\0';
                parse_line(line);
            }
            len = 0;
            drop = false;
            continue;
        }
        if (drop || len >= 127) {
            drop = true;
            len = 0;
            continue;
        }
        line[len++] = (char)byte;
    }
}

void gps_start(void)
{
    xTaskCreate(gps_task, "gps", 4096, NULL, 6, NULL);
}
