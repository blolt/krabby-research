# Pinned SparkFun device drivers, compiled on the host so adapter suites can run
# the real driver code against device fakes behind the TwoWire fake. Versions
# match the arduino-cli pins in firmware/Makefile; bump both together.

FetchContent_Declare(
    sparkfun_toolkit
    URL https://github.com/sparkfun/SparkFun_Toolkit/archive/refs/tags/v1.2.0.tar.gz
    URL_HASH SHA256=44e02fceaa0db83765b021b964de701e6d0a057fff62ff3a1eea80d98d4b034d
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)
FetchContent_Declare(
    sparkfun_ina2xx
    URL https://github.com/sparkfun/SparkFun_INA2XX_Arduino_Library/archive/refs/tags/v1.0.0.tar.gz
    URL_HASH SHA256=51ea7aa21b219707f9f43504b3e815a797b848d2a1e2077babb9e56cf4b50265
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)
FetchContent_Declare(
    sparkfun_lsm6dso
    URL https://github.com/sparkfun/SparkFun_Qwiic_6DoF_LSM6DSO_Arduino_Library/archive/4addc5ffd7cb71a0481aee259ab85c232aa92afe.tar.gz
    URL_HASH SHA256=7dca3c2616a980e521213a1f823e6ed0b18e6523f024c31e96032ee3ceb2effc
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)
FetchContent_Declare(
    sparkfun_qwiic_oled
    URL https://github.com/sparkfun/SparkFun_Qwiic_OLED_Arduino_Library/archive/refs/tags/v1.0.9.tar.gz
    URL_HASH SHA256=245eccce3898ae0b2804d93932e1392fa0df6412bc70ec3710ca483ac2d76a74
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)
# None of the archives has a CMakeLists.txt, so this only downloads and unpacks.
FetchContent_MakeAvailable(sparkfun_toolkit sparkfun_ina2xx sparkfun_lsm6dso sparkfun_qwiic_oled)

# Arduino, SPI and program-space declarations the drivers compile against. The
# suites define millis/delay/pinMode/digitalWrite in their own environments.
add_library(sparkfun_host_runtime STATIC fakes/vendor_runtime/SPI.cpp)
target_include_directories(sparkfun_host_runtime PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/fakes/vendor_runtime")
target_link_libraries(sparkfun_host_runtime PUBLIC wire_native_support)
if(MSVC)
    target_compile_options(sparkfun_host_runtime PRIVATE /W4 /WX)
else()
    target_compile_options(sparkfun_host_runtime PRIVATE -Wall -Wextra -Werror)
endif()

# Vendor code is built as-is: its warnings are not ours to fix, and SYSTEM keeps
# its headers from tripping -Werror in the suites that include them.
function(add_sparkfun_library name source_dir)
    add_library(${name} STATIC ${ARGN})
    target_include_directories(${name} SYSTEM PUBLIC "${source_dir}/src")
    target_link_libraries(${name} PUBLIC sparkfun_host_runtime)
    if(NOT MSVC)
        target_compile_options(${name} PRIVATE -w)
    endif()
endfunction()

add_sparkfun_library(sparkfun_toolkit_native "${sparkfun_toolkit_SOURCE_DIR}"
    "${sparkfun_toolkit_SOURCE_DIR}/src/sfTk/sfToolkit.cpp"
    "${sparkfun_toolkit_SOURCE_DIR}/src/sfTkArdI2C.cpp"
    "${sparkfun_toolkit_SOURCE_DIR}/src/sfTkArdSPI.cpp"
    "${sparkfun_toolkit_SOURCE_DIR}/src/sfTkArduino.cpp")

add_sparkfun_library(sparkfun_ina2xx_native "${sparkfun_ina2xx_SOURCE_DIR}"
    "${sparkfun_ina2xx_SOURCE_DIR}/src/sfTk/sfDevINA2XX.cpp"
    "${sparkfun_ina2xx_SOURCE_DIR}/src/sfTk/sfDevINA228.cpp"
    "${sparkfun_ina2xx_SOURCE_DIR}/src/sfTk/sfDevINA237.cpp")
target_link_libraries(sparkfun_ina2xx_native PUBLIC sparkfun_toolkit_native)

add_sparkfun_library(sparkfun_lsm6dso_native "${sparkfun_lsm6dso_SOURCE_DIR}"
    "${sparkfun_lsm6dso_SOURCE_DIR}/src/SparkFunLSM6DSO.cpp")

add_sparkfun_library(sparkfun_qwiic_oled_native "${sparkfun_qwiic_oled_SOURCE_DIR}"
    "${sparkfun_qwiic_oled_SOURCE_DIR}/src/qwiic_grbuffer.cpp"
    "${sparkfun_qwiic_oled_SOURCE_DIR}/src/qwiic_grssd1306.cpp"
    "${sparkfun_qwiic_oled_SOURCE_DIR}/src/qwiic_i2c.cpp")
