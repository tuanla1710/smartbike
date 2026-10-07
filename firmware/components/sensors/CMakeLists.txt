idf_component_register(
    SRCS "i2c_bus.c" "light.c" "imu.c" "lidar.c" "gps.c" "sensors_task.c"
    INCLUDE_DIRS "include"
    REQUIRES driver board vehicle power esp_timer
)
