#pragma once

#define BIKE_RSHUNT_OHM_NUM 1
#define BIKE_RSHUNT_OHM_DEN 100
#define BIKE_CURRENT_MAX_A 5
#define BIKE_SHUNT_CAL_DEFAULT 1250

#define BIKE_CFG_LIST(X) \
    X(debounce_ms, 30) \
    X(lux_on, 100) \
    X(lux_off, 200) \
    X(lux_stale_ms, 1000) \
    X(on_duty, 1023) \
    X(blink_period_ms, 800) \
    X(blink_on_ms, 400) \
    X(stop_idle_s, 180) \
    X(sleep_after_s, 600) \
    X(alarm_motion_ms, 400) \
    X(alarm_s, 30) \
    X(alarm_gap_s, 5) \
    X(alarm_period_ms, 1000) \
    X(alarm_horn_ms, 200) \
    X(alarm_lamp_ms, 500) \
    X(motion_hold_ms, 250) \
    X(motion_stuck_s, 120) \
    X(horn_max_on_s, 30) \
    X(range_warn_mm, 4000) \
    X(range_stale_ms, 500) \
    X(power_stale_ms, 200) \
    X(uvlo_mv, 4200) \
    X(uvlo_recover_mv, 4600) \
    X(uvlo_enter_ms, 50) \
    X(uvlo_exit_ms, 200) \
    X(uvlo_trip_count, 3) \
    X(uvlo_window_ms, 10000) \
    X(oc_ma, 2500) \
    X(oc_ms, 100) \
    X(oc_immediate_ma, 3000) \
    X(failsafe_ms, 50) \
    X(sleep_ack_ms, 200) \
    X(horn_current_ma, 0) \
    X(shunt_cal, 1250)
