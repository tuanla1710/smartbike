idf_component_register(
    SRCS "bike_ctrl.c" "bike_lock.c" "vehicle_task.c" "rtc_arm.c"
    INCLUDE_DIRS "include"
    REQUIRES config board freertos esp_timer esp_system
)
