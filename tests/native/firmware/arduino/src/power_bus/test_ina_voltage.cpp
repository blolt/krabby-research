#include <limits>
#include <type_traits>

#include "unity.h"

#include "src/power_bus/ina_voltage.h"
#include "src/power_bus/power_bus_constants.h"
#include "src/power_bus/voltage_calibration.h"

static_assert(!std::is_convertible<float, Volts>::value,
              "raw floats must not implicitly become volts");

void setUp() {}
void tearDown() {}

static float corrected(float rawVoltage, float offset)
{
    return correctInaBusVoltage(Volts(rawVoltage), Volts(offset)).value;
}

static void test_offset_correction_applies_once()
{
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, 26.55f, corrected(26.55f, 0.0f));
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, 20.5f, corrected(20.0f, 0.5f));
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, 19.5f, corrected(20.0f, -0.5f));
}

static void test_offset_solver_accepts_positive_negative_and_exact_bounds()
{
    Volts result(99.0f);

    TEST_ASSERT_TRUE(calculateVoltageOffset(
        Volts(24.5f), Volts(24.0f), Volts(2.0f), result));
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, 0.5f, result.value);
    TEST_ASSERT_TRUE(calculateVoltageOffset(
        Volts(23.5f), Volts(24.0f), Volts(2.0f), result));
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, -0.5f, result.value);
    TEST_ASSERT_TRUE(calculateVoltageOffset(
        Volts(26.0f), Volts(24.0f), Volts(2.0f), result));
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, 2.0f, result.value);
    TEST_ASSERT_TRUE(calculateVoltageOffset(
        Volts(22.0f), Volts(24.0f), Volts(2.0f), result));
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, -2.0f, result.value);
}

static void test_offset_solver_rejects_out_of_range_without_mutating_result()
{
    Volts result(99.0f);

    TEST_ASSERT_FALSE(calculateVoltageOffset(
        Volts(26.001f), Volts(24.0f), Volts(2.0f), result));
    TEST_ASSERT_EQUAL_FLOAT(99.0f, result.value);
    TEST_ASSERT_FALSE(calculateVoltageOffset(
        Volts(21.999f), Volts(24.0f), Volts(2.0f), result));
    TEST_ASSERT_EQUAL_FLOAT(99.0f, result.value);
    TEST_ASSERT_FALSE(calculateVoltageOffset(
        Volts(24.0f), Volts(24.0f), Volts(-0.1f), result));
    TEST_ASSERT_EQUAL_FLOAT(99.0f, result.value);
}

static void test_offset_solver_rejects_nonfinite_without_mutating_result()
{
    const float nonfinite[] = {
        std::numeric_limits<float>::quiet_NaN(),
        std::numeric_limits<float>::infinity(),
        -std::numeric_limits<float>::infinity(),
    };

    for (size_t index = 0; index < 3; ++index)
    {
        Volts result(99.0f);
        TEST_ASSERT_FALSE(calculateVoltageOffset(
            Volts(nonfinite[index]), Volts(24.0f), Volts(2.0f), result));
        TEST_ASSERT_EQUAL_FLOAT(99.0f, result.value);
        TEST_ASSERT_FALSE(calculateVoltageOffset(
            Volts(24.0f), Volts(nonfinite[index]), Volts(2.0f), result));
        TEST_ASSERT_EQUAL_FLOAT(99.0f, result.value);
        TEST_ASSERT_FALSE(calculateVoltageOffset(
            Volts(24.0f), Volts(24.0f), Volts(nonfinite[index]), result));
        TEST_ASSERT_EQUAL_FLOAT(99.0f, result.value);
    }
}

static void test_nonfinite_corrected_inputs_propagate_for_caller_validation()
{
    const float nan = std::numeric_limits<float>::quiet_NaN();
    const float inf = std::numeric_limits<float>::infinity();

    TEST_ASSERT_TRUE(isnan(corrected(nan, 0.0f)));
    TEST_ASSERT_TRUE(isinf(corrected(inf, 0.0f)));
    TEST_ASSERT_TRUE(isnan(corrected(24.0f, nan)));
    TEST_ASSERT_TRUE(isinf(corrected(24.0f, inf)));
}

struct RecordingIna
{
    float voltage;
    int reads;

    float readBusVoltage()
    {
        ++reads;
        return voltage;
    }
};

static VoltageCalibrationLimits calibrationLimits()
{
    const VoltageCalibrationLimits limits = {
        Volts(40.0f), Volts(20.0f), Volts(2.0f)};
    return limits;
}

static void assertOffsetsUnchanged(const VoltageOffsets& offsets)
{
    TEST_ASSERT_EQUAL_FLOAT(8.0f, offsets.packVoltageOffset.value);
    TEST_ASSERT_EQUAL_FLOAT(9.0f, offsets.midpointVoltageOffset.value);
}

static void test_capture_reads_each_device_once_and_commits_both_offsets()
{
    RecordingIna pack = {25.0f, 0};
    RecordingIna midpoint = {12.0f, 0};
    VoltageOffsets offsets = {Volts(8.0f), Volts(9.0f)};

    TEST_ASSERT_TRUE(captureVoltageOffsets(
        pack, midpoint, Volts(25.5f), Volts(11.75f),
        calibrationLimits(), offsets));
    TEST_ASSERT_FLOAT_WITHIN(
        0.00001f, 0.5f, offsets.packVoltageOffset.value);
    TEST_ASSERT_FLOAT_WITHIN(
        0.00001f, -0.25f, offsets.midpointVoltageOffset.value);
    TEST_ASSERT_EQUAL_INT(1, pack.reads);
    TEST_ASSERT_EQUAL_INT(1, midpoint.reads);
}

static void test_capture_accepts_exact_offset_bounds()
{
    RecordingIna pack = {25.0f, 0};
    RecordingIna midpoint = {12.0f, 0};
    VoltageOffsets offsets = {Volts(8.0f), Volts(9.0f)};

    TEST_ASSERT_TRUE(captureVoltageOffsets(
        pack, midpoint, Volts(27.0f), Volts(10.0f),
        calibrationLimits(), offsets));
    TEST_ASSERT_EQUAL_FLOAT(2.0f, offsets.packVoltageOffset.value);
    TEST_ASSERT_EQUAL_FLOAT(-2.0f, offsets.midpointVoltageOffset.value);
}

static void test_capture_rejects_every_invalid_reference_before_reading()
{
    const float invalidPackReferences[] = {
        0.0f, -1.0f, 40.001f,
        std::numeric_limits<float>::quiet_NaN(),
        std::numeric_limits<float>::infinity(),
        -std::numeric_limits<float>::infinity()};
    const float invalidMidpointReferences[] = {
        0.0f, -1.0f, 20.001f,
        std::numeric_limits<float>::quiet_NaN(),
        std::numeric_limits<float>::infinity(),
        -std::numeric_limits<float>::infinity()};

    for (size_t index = 0;
         index < sizeof(invalidPackReferences) / sizeof(float);
         ++index)
    {
        RecordingIna pack = {25.0f, 0};
        RecordingIna midpoint = {12.0f, 0};
        VoltageOffsets offsets = {Volts(8.0f), Volts(9.0f)};
        TEST_ASSERT_FALSE(captureVoltageOffsets(
            pack, midpoint, Volts(invalidPackReferences[index]), Volts(12.0f),
            calibrationLimits(), offsets));
        assertOffsetsUnchanged(offsets);
        TEST_ASSERT_EQUAL_INT(0, pack.reads);
        TEST_ASSERT_EQUAL_INT(0, midpoint.reads);
    }

    for (size_t index = 0;
         index < sizeof(invalidMidpointReferences) / sizeof(float);
         ++index)
    {
        RecordingIna pack = {25.0f, 0};
        RecordingIna midpoint = {12.0f, 0};
        VoltageOffsets offsets = {Volts(8.0f), Volts(9.0f)};
        TEST_ASSERT_FALSE(captureVoltageOffsets(
            pack, midpoint, Volts(25.0f),
            Volts(invalidMidpointReferences[index]),
            calibrationLimits(), offsets));
        assertOffsetsUnchanged(offsets);
        TEST_ASSERT_EQUAL_INT(0, pack.reads);
        TEST_ASSERT_EQUAL_INT(0, midpoint.reads);
    }
}

static void test_capture_failure_matrix_preserves_complete_prior_result()
{
    const float nan = std::numeric_limits<float>::quiet_NaN();
    const float rawPairs[][2] = {
        {nan, 12.0f}, {25.0f, nan}, {nan, nan},
        {22.999f, 12.0f}, {25.0f, 14.001f},
        {12.0f, 25.0f}};

    for (size_t index = 0; index < sizeof(rawPairs) / sizeof(rawPairs[0]);
         ++index)
    {
        RecordingIna pack = {rawPairs[index][0], 0};
        RecordingIna midpoint = {rawPairs[index][1], 0};
        VoltageOffsets offsets = {Volts(8.0f), Volts(9.0f)};
        TEST_ASSERT_FALSE(captureVoltageOffsets(
            pack, midpoint, Volts(25.0f), Volts(12.0f),
            calibrationLimits(), offsets));
        assertOffsetsUnchanged(offsets);
        TEST_ASSERT_EQUAL_INT(1, pack.reads);
        TEST_ASSERT_EQUAL_INT(1, midpoint.reads);
    }
}

static void test_capture_rejects_invalid_limits_without_committing()
{
    const VoltageCalibrationLimits invalidLimits[] = {
        {Volts(0.0f), Volts(20.0f), Volts(2.0f)},
        {Volts(40.0f), Volts(0.0f), Volts(2.0f)},
        {Volts(40.0f), Volts(20.0f), Volts(-1.0f)},
        {Volts(40.0f), Volts(20.0f),
         Volts(std::numeric_limits<float>::infinity())}};

    for (size_t index = 0;
         index < sizeof(invalidLimits) / sizeof(invalidLimits[0]);
         ++index)
    {
        RecordingIna pack = {25.0f, 0};
        RecordingIna midpoint = {12.0f, 0};
        VoltageOffsets offsets = {Volts(8.0f), Volts(9.0f)};
        TEST_ASSERT_FALSE(captureVoltageOffsets(
            pack, midpoint, Volts(25.0f), Volts(12.0f),
            invalidLimits[index], offsets));
        assertOffsetsUnchanged(offsets);
    }
}

static void test_device_boundary_reads_the_supplied_ina_instance_once()
{
    RecordingIna pack = {26.4f, 0};
    RecordingIna midpoint = {13.1f, 0};

    const Volts packVoltage =
        readCorrectedInaBusVoltage(pack, Volts(0.0f));
    const Volts midpointVoltage =
        readCorrectedInaBusVoltage(midpoint, Volts(0.05f));

    TEST_ASSERT_FLOAT_WITHIN(0.00001f, 26.4f, packVoltage.value);
    TEST_ASSERT_FLOAT_WITHIN(0.00001f, 13.15f, midpointVoltage.value);
    TEST_ASSERT_EQUAL_INT(1, pack.reads);
    TEST_ASSERT_EQUAL_INT(1, midpoint.reads);
}

int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_offset_correction_applies_once);
    RUN_TEST(test_offset_solver_accepts_positive_negative_and_exact_bounds);
    RUN_TEST(test_offset_solver_rejects_out_of_range_without_mutating_result);
    RUN_TEST(test_offset_solver_rejects_nonfinite_without_mutating_result);
    RUN_TEST(test_nonfinite_corrected_inputs_propagate_for_caller_validation);
    RUN_TEST(test_capture_reads_each_device_once_and_commits_both_offsets);
    RUN_TEST(test_capture_accepts_exact_offset_bounds);
    RUN_TEST(test_capture_rejects_every_invalid_reference_before_reading);
    RUN_TEST(test_capture_failure_matrix_preserves_complete_prior_result);
    RUN_TEST(test_capture_rejects_invalid_limits_without_committing);
    RUN_TEST(test_device_boundary_reads_the_supplied_ina_instance_once);
    return UNITY_END();
}
