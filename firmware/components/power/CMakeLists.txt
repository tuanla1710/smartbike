idf_component_register(
    SRCS "ina228.c"
    INCLUDE_DIRS "include"
    REQUIRES driver
)
target_include_directories(${COMPONENT_LIB} PRIVATE "${CMAKE_CURRENT_LIST_DIR}/../sensors/include")
