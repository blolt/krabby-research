#include "unity.h"
#include "environment.h"
#include "src/display/ssd1306_adapter.h"
#include <algorithm>

using namespace oled_native;

static TwoWire testWire(environment.bus);
void setUp() { oled_native::reset(); }
void tearDown()
{
    TEST_ASSERT_TRUE(Wire.state().events.empty());
    TEST_ASSERT_TRUE(Wire.state().errors.empty());
    if (!environment.bus.errors.empty()) TEST_FAIL_MESSAGE(environment.bus.errors.front().c_str());
    if (!environment.errors.empty()) TEST_FAIL_MESSAGE(environment.errors.front().c_str());
    TEST_ASSERT_TRUE(environment.begins.empty());
    TEST_ASSERT_TRUE(environment.resets.empty());
    TEST_ASSERT_TRUE(environment.bus.transfers.empty());
    TEST_ASSERT_TRUE(environment.sda.empty());
}
static size_t count(const char *name)
{
    return std::count_if(environment.events.begin(), environment.events.end(),
        [name](const Event &e) { return e.name == name; });
}
static void events(std::initializer_list<Event> expected)
{
    TEST_ASSERT_EQUAL_UINT(expected.size(), environment.events.size());
    size_t i = 0;
    for (const auto &e : expected)
    {
        const auto &actual = environment.events[i++];
        TEST_ASSERT_EQUAL_STRING(e.name.c_str(), actual.name.c_str());
        TEST_ASSERT_TRUE(e.args == actual.args);
        TEST_ASSERT_EQUAL_STRING(e.text.c_str(), actual.text.c_str());
    }
}
static void probe(uint8_t status = 0, bool timeout = false) {
    wire_native::Transfer transfer;
    transfer.address = 0x3D;
    transfer.status = status;
    transfer.timeout = timeout;
    environment.bus.transfers.push_back(transfer);
}
static void init(Ssd1306Adapter &adapter, bool succeeds = true)
{
    environment.begins.push_back(succeeds);
    TEST_ASSERT_EQUAL_INT(succeeds, adapter.initialize());
    TEST_ASSERT_EQUAL_INT(succeeds, adapter.isInitialized());
}
static void at(uint64_t ms) { environment.microseconds = ms * 1000; }
static std::vector<Event> drawing()
{
    std::vector<Event> result;
    for (const auto &e : environment.events)
        if (e.name == "erase" || e.name == "pixel" || e.name == "line" ||
            e.name == "rectangle" || e.name == "fill" || e.name == "text") result.push_back(e);
    return result;
}
static void noDrawing()
{
    TEST_ASSERT_TRUE(drawing().empty());
    TEST_ASSERT_EQUAL_UINT(0, count("display"));
    TEST_ASSERT_EQUAL_UINT(0, count("clock"));
}
static void transferSuffix()
{
    TEST_ASSERT_TRUE(environment.events.size() >= 3);
    auto end = environment.events.end();
    const Event expected[] = {{"clock",{400000},""}, {"display",{400000},""}, {"clock",{100000},""}};
    for (int i = 0; i < 3; ++i) TEST_ASSERT_TRUE(expected[i] == end[i - 3]);
    TEST_ASSERT_EQUAL_UINT(1, count("display"));
    TEST_ASSERT_EQUAL_UINT32(100000, environment.bus.clock);
}
static void waitTwo(Ssd1306Adapter &adapter, const DisplayFrame &frame)
{ TEST_ASSERT_FALSE(adapter.render(frame)); TEST_ASSERT_FALSE(adapter.render(frame)); }

static void test_canvas_forwards_driver_operations_and_results()
{
    Ssd1306Canvas canvas(testWire);
    environment.begins = {false,true};
    TEST_ASSERT_FALSE(canvas.begin()); TEST_ASSERT_TRUE(canvas.begin());
    environment.resets = {false,true};
    TEST_ASSERT_FALSE(canvas.reset()); TEST_ASSERT_TRUE(canvas.reset());
    canvas.useStatusFont(); canvas.erase(); canvas.display();
    events({{"begin",{0},""},{"begin",{0},""},{"reset",{1},""},{"reset",{1},""},
        {"font",{1},""},{"erase",{},""},{"display",{100000},""}});
}
static void test_canvas_draw_arguments_and_coordinate_conversion()
{
    Ssd1306Canvas canvas(testWire);
    environment.begins.push_back(true);
    TEST_ASSERT_TRUE(canvas.begin());
    environment.events.clear();
    canvas.pixel(2,3); canvas.line(1,2,3,4); canvas.rectangle(5,6,7,8);
    canvas.rectangleFill(9,10,11,12,0); canvas.text(13,14,"hello");
    canvas.pixel(-1,256); canvas.line(-2,257,258,-3); canvas.rectangle(-4,259,260,-5);
    canvas.rectangleFill(-6,261,262,-7,257); canvas.text(-8,263,"");
    events({{"pixel",{2,3,1},""},{"line",{1,2,3,4,1},""},{"rectangle",{5,6,7,8,1},""},
        {"fill",{9,10,11,12,0},""},{"text",{13,14,1},"hello"},
        {"pixel",{255,0,1},""},{"line",{254,1,2,253,1},""},{"rectangle",{252,3,4,251,1},""},
        {"fill",{250,5,6,249,1},""},{"text",{248,7,1},""}});
}
static void test_initialize_success_failure_and_font()
{
    Ssd1306Adapter adapter(testWire); TEST_ASSERT_FALSE(adapter.isInitialized());
    init(adapter,false); events({{"begin",{0},""}});
    environment.events.clear(); init(adapter);
    events({{"begin",{0},""},{"font",{1},""}});
    environment.events.clear(); init(adapter,false);
    events({{"begin",{0},""}});
}
static void test_first_unchanged_changed_and_invalidated_frames()
{
    Ssd1306Adapter adapter(testWire); DisplayFrame frame; init(adapter);
    environment.events.clear(); probe(); TEST_ASSERT_TRUE(adapter.render(frame));
    const auto full = drawing(); TEST_ASSERT_FALSE(full.empty());
    TEST_ASSERT_EQUAL_UINT(1,count("erase")); transferSuffix();
    TEST_ASSERT_EQUAL_UINT(1,count("font"));
    environment.events.clear(); probe(); TEST_ASSERT_FALSE(adapter.render(frame));
    events({{"clearTimeout",{},""},{"probe",{0x3D},""},{"endTransmission",{1},""}});
    environment.events.clear(); frame.role = ROLE_FRONT; probe();
    TEST_ASSERT_TRUE(adapter.render(frame));
    TEST_ASSERT_EQUAL_UINT(0,count("erase")); TEST_ASSERT_TRUE(drawing().size() < full.size()); transferSuffix();
    environment.events.clear(); adapter.invalidate(); probe(); TEST_ASSERT_TRUE(adapter.render(frame));
    TEST_ASSERT_EQUAL_UINT(1,count("erase")); transferSuffix();
    const auto invalidated = drawing();
    Ssd1306Adapter fresh(testWire); init(fresh); environment.events.clear(); probe();
    TEST_ASSERT_TRUE(fresh.render(frame)); TEST_ASSERT_TRUE(invalidated == drawing());
}
static void test_disconnection_stops_drawing_even_for_unchanged_frame()
{
    Ssd1306Adapter adapter(testWire); DisplayFrame frame; init(adapter); probe(); TEST_ASSERT_TRUE(adapter.render(frame));
    environment.events.clear(); probe(2); TEST_ASSERT_FALSE(adapter.render(frame));
    TEST_ASSERT_FALSE(adapter.isInitialized()); noDrawing();
    TEST_ASSERT_EQUAL_UINT(1,count("probe"));
    TEST_ASSERT_FALSE(adapter.render(frame)); TEST_ASSERT_EQUAL_UINT(1,count("probe"));
}
static void test_reset_recovery_redraws_same_frame_and_restores_font()
{
    Ssd1306Adapter adapter(testWire); DisplayFrame frame; init(adapter); probe(); TEST_ASSERT_TRUE(adapter.render(frame));
    const auto full = drawing();
    probe(2); TEST_ASSERT_FALSE(adapter.render(frame)); TEST_ASSERT_FALSE(adapter.render(frame));
    environment.events.clear(); probe(); environment.resets.push_back(true); probe();
    TEST_ASSERT_TRUE(adapter.render(frame)); TEST_ASSERT_TRUE(adapter.isInitialized());
    TEST_ASSERT_EQUAL_UINT(1,count("reset")); TEST_ASSERT_EQUAL_UINT(2,count("font"));
    TEST_ASSERT_EQUAL_UINT(1,count("erase")); TEST_ASSERT_TRUE(full == drawing()); transferSuffix();
    TEST_ASSERT_EQUAL_UINT(0,count("wire.end"));
    TEST_ASSERT_EQUAL_UINT(0,count("getTimeout"));
    environment.events.clear(); probe(); TEST_ASSERT_FALSE(adapter.render(frame)); noDrawing();
}
static void test_failed_reset_and_retry_boundary_with_rollover()
{
    for (uint64_t start : {uint64_t(0), uint64_t(UINT32_MAX)-499})
    {
        tearDown(); oled_native::reset(); at(start);
        Ssd1306Adapter adapter(testWire); DisplayFrame frame; init(adapter,false); environment.events.clear();
        waitTwo(adapter,frame); TEST_ASSERT_TRUE(environment.events.empty());
        probe(); environment.resets.push_back(false); TEST_ASSERT_FALSE(adapter.render(frame));
        TEST_ASSERT_FALSE(adapter.isInitialized()); noDrawing(); TEST_ASSERT_EQUAL_UINT(0,count("font"));
        at(start+999); for(int i=0;i<3;++i) TEST_ASSERT_FALSE(adapter.render(frame));
        TEST_ASSERT_EQUAL_UINT(1,count("reset"));
        at(start+1000); probe(); environment.resets.push_back(true); probe(); environment.events.clear();
        TEST_ASSERT_TRUE(adapter.render(frame)); transferSuffix();
    }
}
static void test_nack_does_not_clear_bus_and_stale_timeout_is_cleared()
{
    Ssd1306Adapter adapter(testWire); DisplayFrame frame; waitTwo(adapter,frame);
    environment.bus.timeout = true; probe(2); TEST_ASSERT_FALSE(adapter.render(frame));
    events({{"clearTimeout",{},""},{"probe",{0x3D},""},{"endTransmission",{1},""},{"getTimeout",{0},""}});
    TEST_ASSERT_FALSE(adapter.isInitialized()); noDrawing();
}
static void test_timeout_recovery_on_free_bus()
{
    Ssd1306Adapter adapter(testWire); DisplayFrame frame; waitTwo(adapter,frame);
    probe(2,true); probe(); environment.resets.push_back(true); probe();
    TEST_ASSERT_TRUE(adapter.render(frame));
    const std::vector<Event> expected = {{"clearTimeout",{},""},{"probe",{0x3D},""},{"endTransmission",{1},""},
        {"getTimeout",{1},""},{"wire.end",{},""},{"pinMode",{20,2},""},{"pinMode",{21,2},""},
        {"pinMode",{20,2},""},{"digitalRead",{20,1},""},{"pinMode",{20,2},""},{"digitalRead",{20,1},""},
        {"wire.begin",{},""},{"clock",{100000},""},{"timeout",{10000,1},""}};
    TEST_ASSERT_TRUE(environment.events.size() > expected.size());
    TEST_ASSERT_TRUE(std::equal(expected.begin(),expected.end(),environment.events.begin()));
    TEST_ASSERT_EQUAL_UINT(0,count("digitalWrite")); transferSuffix();
}
static void test_timeout_bus_clear_and_stop_sequence()
{
    Ssd1306Adapter adapter(testWire); DisplayFrame frame; waitTwo(adapter,frame);
    environment.sda = {0,0,0,1,1}; probe(2,true); probe(); environment.resets.push_back(true); probe();
    TEST_ASSERT_TRUE(adapter.render(frame));
    std::vector<Event> writes;
    for(const auto &e:environment.events) if(e.name=="digitalWrite") writes.push_back(e);
    const std::vector<Event> expected={{"digitalWrite",{21,0},""},{"digitalWrite",{21,0},""},{"digitalWrite",{20,0},""}};
    TEST_ASSERT_TRUE(writes==expected);
    const auto stop=std::find(environment.events.begin(),environment.events.end(),expected.back());
    const std::vector<Event> sequence={{"digitalWrite",{20,0},""},{"pinMode",{20,1},""},{"delayUs",{5},""},
        {"pinMode",{21,2},""},{"delayUs",{5},""},{"pinMode",{20,2},""},{"delayUs",{5},""},{"wire.begin",{},""}};
    TEST_ASSERT_TRUE(size_t(environment.events.end()-stop)>=sequence.size());
    TEST_ASSERT_TRUE(std::equal(sequence.begin(),sequence.end(),stop)); transferSuffix();
}
static void test_post_clear_probe_reset_and_final_probe_failures()
{
    for(int failure=0;failure<3;++failure)
    {
        tearDown(); oled_native::reset();
        Ssd1306Adapter adapter(testWire); DisplayFrame frame; waitTwo(adapter,frame);
        probe(2,true); probe(failure==0?2:0);
        if(failure>0) environment.resets.push_back(failure!=1);
        if(failure==2) probe(2);
        TEST_ASSERT_FALSE(adapter.render(frame)); TEST_ASSERT_FALSE(adapter.isInitialized());
        TEST_ASSERT_TRUE(drawing().empty()); TEST_ASSERT_EQUAL_UINT(0,count("display"));
        TEST_ASSERT_EQUAL_UINT(failure==0?0:1,count("reset"));
        TEST_ASSERT_EQUAL_UINT(failure==2?1:0,count("font"));
        TEST_ASSERT_EQUAL_UINT32(100000,environment.bus.clock);
    }
}
static void test_stuck_bus_latches_and_recovers_after_release()
{
    Ssd1306Adapter adapter(testWire); DisplayFrame frame; environment.sdaHigh=false;
    waitTwo(adapter,frame); probe(2,true); TEST_ASSERT_FALSE(adapter.render(frame));
    TEST_ASSERT_EQUAL_UINT(9,count("digitalWrite")); TEST_ASSERT_EQUAL_UINT(0,count("wire.begin"));
    environment.events.clear(); at(1000); waitTwo(adapter,frame); probe(2,true);
    TEST_ASSERT_FALSE(adapter.render(frame)); TEST_ASSERT_EQUAL_UINT(0,count("digitalWrite")); noDrawing();
    environment.sdaHigh=true; at(2000); waitTwo(adapter,frame);
    probe(2,true); probe(); environment.resets.push_back(true); probe();
    TEST_ASSERT_TRUE(adapter.render(frame)); TEST_ASSERT_EQUAL_UINT(0,count("digitalWrite")); transferSuffix();
}
static void test_initialize_clears_recovery_latch_timing_and_previous_frame()
{
    Ssd1306Adapter adapter(testWire); DisplayFrame frame; init(adapter); probe(); TEST_ASSERT_TRUE(adapter.render(frame));
    init(adapter); environment.events.clear(); probe(); TEST_ASSERT_TRUE(adapter.render(frame));
    TEST_ASSERT_EQUAL_UINT(1,count("erase"));
    probe(2); TEST_ASSERT_FALSE(adapter.render(frame)); TEST_ASSERT_FALSE(adapter.render(frame));
    environment.sdaHigh=false; probe(2,true); TEST_ASSERT_FALSE(adapter.render(frame));
    init(adapter,false); environment.events.clear(); waitTwo(adapter,frame); probe(2,true);
    TEST_ASSERT_FALSE(adapter.render(frame));
    TEST_ASSERT_EQUAL_UINT(9,count("digitalWrite"));
}
int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_canvas_forwards_driver_operations_and_results);
    RUN_TEST(test_canvas_draw_arguments_and_coordinate_conversion);
    RUN_TEST(test_initialize_success_failure_and_font);
    RUN_TEST(test_first_unchanged_changed_and_invalidated_frames);
    RUN_TEST(test_disconnection_stops_drawing_even_for_unchanged_frame);
    RUN_TEST(test_reset_recovery_redraws_same_frame_and_restores_font);
    RUN_TEST(test_failed_reset_and_retry_boundary_with_rollover);
    RUN_TEST(test_nack_does_not_clear_bus_and_stale_timeout_is_cleared);
    RUN_TEST(test_timeout_recovery_on_free_bus);
    RUN_TEST(test_timeout_bus_clear_and_stop_sequence);
    RUN_TEST(test_post_clear_probe_reset_and_final_probe_failures);
    RUN_TEST(test_stuck_bus_latches_and_recovers_after_release);
    RUN_TEST(test_initialize_clears_recovery_latch_timing_and_previous_frame);
    return UNITY_END();
}
