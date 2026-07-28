cmake_minimum_required(VERSION 3.20)

project(krabby_firmware_native_tests LANGUAGES C CXX)

include(CTest)
include(FetchContent)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

FetchContent_Declare(
    unity
    URL https://github.com/ThrowTheSwitch/Unity/archive/refs/tags/v2.6.1.tar.gz
    URL_HASH SHA256=b41a66d45a6b99758fb3202ace6178177014d52fc524bf1f72687d93e9867292
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)
FetchContent_MakeAvailable(unity)

set(KRABBY_ARDUINO_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../firmware/arduino")

function(add_firmware_native_test test_name)
    add_executable("${test_name}" "${test_name}.cpp")
    target_include_directories("${test_name}" PRIVATE "${KRABBY_ARDUINO_DIR}")
    target_link_libraries("${test_name}" PRIVATE unity)
    if(MSVC)
        target_compile_options("${test_name}" PRIVATE /W4 /WX)
    else()
        target_compile_options("${test_name}" PRIVATE -Wall -Wextra -Werror)
    endif()
    add_test(NAME "${test_name}" COMMAND "${test_name}")
endfunction()

set(KRABBY_FIRMWARE_NATIVE_TESTS
    test_imu_initialization
    test_imu_sample
    test_controller_slots
    test_controller_freshness
)

foreach(test_name IN LISTS KRABBY_FIRMWARE_NATIVE_TESTS)
    if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/${test_name}.cpp")
        add_firmware_native_test("${test_name}")
    endif()
endforeach()
