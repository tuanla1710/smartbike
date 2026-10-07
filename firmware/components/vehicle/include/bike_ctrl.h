#pragma once

#include "bike_types.h"

#include <stddef.h>

#define BIKE_REPLY_LINES 40
#define BIKE_REPLY_LEN 768

typedef struct {
    int count;
    char text[BIKE_REPLY_LINES][BIKE_REPLY_LEN];
} bike_reply_t;

typedef struct {
    void (*apply)(uint16_t head, uint16_t tail, uint16_t left, uint16_t right,
                  bool brake, bool horn, bool aux);
    void (*led)(bool on);
    void (*xshut)(bool high);
    void (*deep_sleep)(void);
    int (*nvs_save)(const char *key, int value);
} bike_hooks_t;

typedef void (*bike_emit_fn)(const char *line, void *ctx);

void bike_plant_init(bike_plant_t *plant);
void bike_setup(bike_plant_t *plant, bool armed);
void bike_set_hooks(const bike_hooks_t *hooks);
void bike_set_emit(bike_emit_fn fn, void *ctx);
void bike_mark(uint32_t now_ms);

void bike_handle(const char *line, bike_reply_t *out);
void bike_advance(uint32_t ms, bike_reply_t *out);
void bike_step(uint32_t now_ms, bike_reply_t *out);
void bike_reset(int reason, bike_reply_t *out);
void bike_stall(bool on);

bool bike_enqueue_opcode(uint8_t opcode);
bool bike_sleep_pending(void);
extern volatile uint32_t bike_kick_ms;

static inline uint32_t bike_last_kick(void)
{
    return bike_kick_ms;
}
uint32_t bike_watch_period(void);
void bike_export_rtc(uint8_t *armed, uint8_t *crc);
void bike_pack_snapshot(uint8_t raw[32]);
void bike_restore_saved(int horn_current_ma, int shunt_cal);
int bike_shunt_cal(void);
uint8_t bike_crc8(const uint8_t *data, size_t len);

bike_plant_t *bike_plant(void);
