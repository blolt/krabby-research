#include "unity.h"
#include "environment.h"
#include "src/display/ssd1306_adapter.h"
#include "src/display/display_renderer.h"
#include <algorithm>
#include <vector>

using namespace oled_native;

static TwoWire testWire(environment.bus);
static constexpr uint8_t NACK = 2, TIMEOUT = 5;

struct TestDisplay
{
    Ssd1306Adapter canvas;
    DisplayRenderer<Ssd1306Adapter> renderer;
    explicit TestDisplay(TwoWire &wire) : canvas(wire), renderer(canvas) {}
    bool initialize() { return renderer.initialize(); }
    bool isInitialized() const { return canvas.isInitialized(); }
    bool render(const DisplayFrame &frame) { return renderer.render(frame); }
    void invalidate() { renderer.invalidate(); }
};


void setUp() { oled_native::reset(); }
void tearDown()
{
    TEST_ASSERT_TRUE(Wire.state().events.empty());
    TEST_ASSERT_TRUE(Wire.state().errors.empty());
    if (!environment.bus.errors.empty()) TEST_FAIL_MESSAGE(environment.bus.errors.front().c_str());
    if (!environment.errors.empty()) TEST_FAIL_MESSAGE(environment.errors.front().c_str());
    TEST_ASSERT_TRUE(environment.panel.pings.empty());
    TEST_ASSERT_TRUE(environment.bus.transfers.empty());
    TEST_ASSERT_TRUE(environment.sda.empty());
}

static size_t count(const char *name)
{
    return std::count_if(environment.events.begin(), environment.events.end(),
        [name](const Event &e) { return e.name == name; });
}
static size_t dataAt(long clock)
{
    return std::count_if(environment.events.begin(), environment.events.end(),
        [clock](const Event &e) { return e.name == "data" && e.args == std::vector<long>{clock}; });
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
// Outcome of the next empty transaction: the adapter's probes and the library's pings
// share one queue in bus order. Unscripted ones ACK.
static void ping(uint8_t status = 0) { environment.panel.pings.push_back(status); }
static void init(TestDisplay &adapter, bool succeeds = true)
{
    if (!succeeds) ping(NACK);
    TEST_ASSERT_EQUAL_INT(succeeds, adapter.initialize());
    TEST_ASSERT_EQUAL_INT(succeeds, adapter.isInitialized());
}
static void at(uint64_t ms) { environment.microseconds = ms * 1000; }
static void noDrawing()
{
    TEST_ASSERT_EQUAL_UINT(0, dataAt(400000));
    TEST_ASSERT_EQUAL_UINT(0, count("clock"));
}
static void transferSuffix()
{
    TEST_ASSERT_TRUE(environment.events.size() >= 3);
    auto end = environment.events.end();
    const Event expected[] = {{"clock",{400000},""}, {"data",{400000},""}, {"clock",{100000},""}};
    for (int i = 0; i < 3; ++i) TEST_ASSERT_TRUE(expected[i] == end[i - 3]);
    TEST_ASSERT_EQUAL_UINT(1, dataAt(400000));
    TEST_ASSERT_EQUAL_UINT32(100000, environment.bus.clock);
}
static void waitTwo(TestDisplay &adapter, const DisplayFrame &frame)
{ TEST_ASSERT_FALSE(adapter.render(frame)); TEST_ASSERT_FALSE(adapter.render(frame)); }

static void test_canvas_forwards_driver_operations_and_results()
{
    Ssd1306Adapter canvas(testWire);
    ping(NACK); TEST_ASSERT_FALSE(canvas.initialize());
    TEST_ASSERT_TRUE(canvas.initialize());
    events({{"ping",{2},""},{"ping",{0},""},{"setup",{},""},{"data",{100000},""}});
    TEST_ASSERT_TRUE(environment.panel.isOn());
    // Once initialized, the library's begin returns true without touching the bus.
    environment.events.clear(); TEST_ASSERT_TRUE(canvas.initialize());
    TEST_ASSERT_TRUE(environment.events.empty());
    environment.events.clear();
    canvas.useStatusFont(); canvas.pixel(3,9); canvas.display();
    events({{"clock",{400000},""},{"data",{400000},""},{"clock",{100000},""}});
    TEST_ASSERT_TRUE(environment.panel.pixel(3,9));
    environment.events.clear(); canvas.erase(); canvas.display();
    events({{"clock",{400000},""},{"data",{400000},""},{"clock",{100000},""}});
    TEST_ASSERT_FALSE(environment.panel.pixel(3,9));
}
static void test_canvas_draw_arguments_and_coordinate_conversion()
{
    Ssd1306Adapter canvas(testWire);
    TEST_ASSERT_TRUE(canvas.initialize());
    // Arguments narrow to uint8_t, so these wrap back onto the panel.
    canvas.pixel(258,259);
    canvas.line(257,266,261,266);
    canvas.rectangle(276,276,6,5);
    canvas.rectangleFill(296,286,3,4,257);
    canvas.rectangleFill(297,287,2,2,256);
    canvas.text(304,40,"#");
    canvas.display();
    const auto &panel = environment.panel;
    TEST_ASSERT_TRUE(panel.pixel(2,3)); TEST_ASSERT_FALSE(panel.pixel(1,3));
    for (uint8_t x = 1; x <= 5; ++x) TEST_ASSERT_TRUE(panel.pixel(x,10));
    TEST_ASSERT_FALSE(panel.pixel(0,10)); TEST_ASSERT_FALSE(panel.pixel(6,10));
    TEST_ASSERT_TRUE(panel.pixel(20,20)); TEST_ASSERT_TRUE(panel.pixel(25,20));
    TEST_ASSERT_TRUE(panel.pixel(20,24)); TEST_ASSERT_TRUE(panel.pixel(20,22));
    TEST_ASSERT_FALSE(panel.pixel(22,22));
    // Colour 257 narrows to 1 (set) and 256 to 0 (clear).
    TEST_ASSERT_TRUE(panel.pixel(40,30)); TEST_ASSERT_TRUE(panel.pixel(41,30));
    TEST_ASSERT_TRUE(panel.pixel(40,32)); TEST_ASSERT_FALSE(panel.pixel(41,31));
    bool glyph = false;
    for (uint8_t x = 48; x < 54; ++x)
        for (uint8_t y = 40; y < 48; ++y) glyph = glyph || panel.pixel(x,y);
    TEST_ASSERT_TRUE(glyph);
}
static void test_initialize_success_and_failure()
{
    TestDisplay adapter(testWire); TEST_ASSERT_FALSE(adapter.isInitialized());
    init(adapter,false); events({{"ping",{2},""}});
    environment.events.clear(); init(adapter);
    events({{"ping",{0},""},{"setup",{},""},{"data",{100000},""}});
    // The library ignores begin once initialized, so initializing again succeeds silently.
    environment.events.clear(); init(adapter);
    TEST_ASSERT_TRUE(environment.events.empty());
}
static void test_first_unchanged_changed_and_invalidated_frames()
{
    TestDisplay adapter(testWire); DisplayFrame frame; init(adapter);
    environment.events.clear(); TEST_ASSERT_TRUE(adapter.render(frame)); transferSuffix();
    const auto full = environment.panel.ram();
    environment.events.clear(); TEST_ASSERT_FALSE(adapter.render(frame));
    events({{"clearTimeout",{},""},{"ping",{0},""}});
    environment.events.clear(); frame.role = ROLE_FRONT;
    TEST_ASSERT_TRUE(adapter.render(frame)); transferSuffix();
    const auto changed = environment.panel.ram();
    TEST_ASSERT_TRUE(changed != full);
    environment.events.clear(); adapter.invalidate(); TEST_ASSERT_TRUE(adapter.render(frame)); transferSuffix();
    TEST_ASSERT_TRUE(environment.panel.ram() == changed);
    // A fresh adapter clears the panel and draws the same frame identically.
    TestDisplay fresh(testWire); init(fresh);
    TEST_ASSERT_TRUE(environment.panel.ram() != changed);
    environment.events.clear(); TEST_ASSERT_TRUE(fresh.render(frame));
    TEST_ASSERT_TRUE(environment.panel.ram() == changed);
}
static void test_disconnection_stops_drawing_even_for_unchanged_frame()
{
    TestDisplay adapter(testWire); DisplayFrame frame; init(adapter); TEST_ASSERT_TRUE(adapter.render(frame));
    environment.events.clear(); ping(NACK); TEST_ASSERT_FALSE(adapter.render(frame));
    TEST_ASSERT_FALSE(adapter.isInitialized()); noDrawing();
    TEST_ASSERT_EQUAL_UINT(1,count("ping"));
    TEST_ASSERT_FALSE(adapter.render(frame)); TEST_ASSERT_EQUAL_UINT(1,count("ping"));
}
static void test_reset_recovery_redraws_same_frame()
{
    TestDisplay adapter(testWire); DisplayFrame frame; init(adapter); TEST_ASSERT_TRUE(adapter.render(frame));
    const auto full = environment.panel.ram();
    ping(NACK); TEST_ASSERT_FALSE(adapter.render(frame)); TEST_ASSERT_FALSE(adapter.render(frame));
    environment.events.clear();
    TEST_ASSERT_TRUE(adapter.render(frame)); TEST_ASSERT_TRUE(adapter.isInitialized());
    // Probe, reset (ping, setup and a cleared panel), probe, then a full redraw.
    TEST_ASSERT_EQUAL_UINT(3,count("ping")); TEST_ASSERT_EQUAL_UINT(1,count("setup"));
    TEST_ASSERT_TRUE(full == environment.panel.ram()); transferSuffix();
    TEST_ASSERT_EQUAL_UINT(0,count("wire.end"));
    TEST_ASSERT_EQUAL_UINT(0,count("getTimeout"));
    environment.events.clear(); TEST_ASSERT_FALSE(adapter.render(frame)); noDrawing();
}
static void test_failed_reset_and_retry_boundary_with_rollover()
{
    for (uint64_t start : {uint64_t(0), uint64_t(UINT32_MAX)-499})
    {
        tearDown(); oled_native::reset(); at(start);
        TestDisplay adapter(testWire); DisplayFrame frame; init(adapter,false); environment.events.clear();
        waitTwo(adapter,frame); TEST_ASSERT_TRUE(environment.events.empty());
        // The probe answers but the library's reset ping does not.
        ping(0); ping(NACK); TEST_ASSERT_FALSE(adapter.render(frame));
        TEST_ASSERT_FALSE(adapter.isInitialized()); noDrawing(); TEST_ASSERT_EQUAL_UINT(0,count("setup"));
        at(start+999); for(int i=0;i<3;++i) TEST_ASSERT_FALSE(adapter.render(frame));
        TEST_ASSERT_EQUAL_UINT(2,count("ping"));
        at(start+1000); environment.events.clear();
        TEST_ASSERT_TRUE(adapter.render(frame)); TEST_ASSERT_EQUAL_UINT(1,count("setup")); transferSuffix();
    }
}
static void test_nack_does_not_clear_bus_and_stale_timeout_is_cleared()
{
    TestDisplay adapter(testWire); DisplayFrame frame; waitTwo(adapter,frame);
    environment.bus.timeout = true; ping(NACK); TEST_ASSERT_FALSE(adapter.render(frame));
    events({{"clearTimeout",{},""},{"ping",{2},""},{"getTimeout",{0},""}});
    TEST_ASSERT_FALSE(adapter.isInitialized()); noDrawing();
}
static void test_timeout_recovery_on_free_bus()
{
    // A failed initialize leaves the library holding the bus its reset needs.
    TestDisplay adapter(testWire); DisplayFrame frame; init(adapter,false);
    environment.events.clear(); waitTwo(adapter,frame);
    ping(TIMEOUT);
    TEST_ASSERT_TRUE(adapter.render(frame));
    const std::vector<Event> expected = {{"clearTimeout",{},""},{"ping",{5},""},
        {"getTimeout",{1},""},{"wire.end",{},""},{"pinMode",{20,2},""},{"pinMode",{21,2},""},
        {"pinMode",{20,2},""},{"digitalRead",{20,1},""},{"pinMode",{20,2},""},{"digitalRead",{20,1},""},
        {"wire.begin",{},""},{"clock",{100000},""},{"timeout",{10000,1},""}};
    TEST_ASSERT_TRUE(environment.events.size() > expected.size());
    TEST_ASSERT_TRUE(std::equal(expected.begin(),expected.end(),environment.events.begin()));
    TEST_ASSERT_EQUAL_UINT(0,count("digitalWrite")); transferSuffix();
}
static void test_timeout_bus_clear_and_stop_sequence()
{
    TestDisplay adapter(testWire); DisplayFrame frame; init(adapter,false);
    waitTwo(adapter,frame);
    environment.sda = {0,0,0,1,1}; ping(TIMEOUT);
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
        TestDisplay adapter(testWire); DisplayFrame frame; init(adapter,false);
        environment.events.clear(); waitTwo(adapter,frame);
        // In bus order: the timed-out probe, the post-clear probe, the reset ping, the final probe.
        ping(TIMEOUT); ping(failure==0?NACK:0);
        if(failure>0) ping(failure==1?NACK:0);
        if(failure==2) ping(NACK);
        TEST_ASSERT_FALSE(adapter.render(frame)); TEST_ASSERT_FALSE(adapter.isInitialized());
        TEST_ASSERT_EQUAL_UINT(0,dataAt(400000));
        TEST_ASSERT_EQUAL_UINT(failure==2?1:0,count("setup"));
        TEST_ASSERT_EQUAL_UINT32(100000,environment.bus.clock);
    }
}
static void test_stuck_bus_latches_and_recovers_after_release()
{
    TestDisplay adapter(testWire); DisplayFrame frame; init(adapter,false);
    environment.events.clear(); environment.sdaHigh=false;
    waitTwo(adapter,frame); ping(TIMEOUT); TEST_ASSERT_FALSE(adapter.render(frame));
    TEST_ASSERT_EQUAL_UINT(9,count("digitalWrite")); TEST_ASSERT_EQUAL_UINT(0,count("wire.begin"));
    environment.events.clear(); at(1000); waitTwo(adapter,frame); ping(TIMEOUT);
    TEST_ASSERT_FALSE(adapter.render(frame)); TEST_ASSERT_EQUAL_UINT(0,count("digitalWrite")); noDrawing();
    environment.sdaHigh=true; at(2000); waitTwo(adapter,frame);
    ping(TIMEOUT);
    TEST_ASSERT_TRUE(adapter.render(frame)); TEST_ASSERT_EQUAL_UINT(0,count("digitalWrite")); transferSuffix();
}
static void test_initialize_clears_recovery_latch_timing_and_previous_frame()
{
    TestDisplay adapter(testWire); DisplayFrame frame; init(adapter); TEST_ASSERT_TRUE(adapter.render(frame));
    // Re-initializing drops the cached frame, so the same frame is drawn again.
    init(adapter); environment.events.clear(); TEST_ASSERT_TRUE(adapter.render(frame)); transferSuffix();
    ping(NACK); TEST_ASSERT_FALSE(adapter.render(frame)); TEST_ASSERT_FALSE(adapter.render(frame));
    environment.sdaHigh=false; ping(TIMEOUT); TEST_ASSERT_FALSE(adapter.render(frame));
    TEST_ASSERT_EQUAL_UINT(9,count("digitalWrite"));
    // Initialize resets the latch and retry timing: without that, the still-low SDA
    // would keep the latch shut and no pulses would be sent.
    init(adapter); environment.events.clear();
    ping(TIMEOUT); ping(TIMEOUT);
    for (int i = 0; i < 3; ++i) TEST_ASSERT_FALSE(adapter.render(frame));
    TEST_ASSERT_EQUAL_UINT(9,count("digitalWrite"));
}
static void test_display_nack_leaves_the_panel_stale_while_the_frame_counts_as_drawn()
{
    TestDisplay adapter(testWire); DisplayFrame frame; init(adapter);
    TEST_ASSERT_TRUE(adapter.render(frame));
    const auto before = environment.panel.ram();
    frame.role = ROLE_FRONT;
    environment.panel.nack = [](ssd1306_native::Transaction kind, const std::vector<uint8_t> &) {
        return kind == ssd1306_native::Transaction::Data;
    };
    // The library reports nothing, marks the pages clean, and the adapter caches the frame.
    TEST_ASSERT_TRUE(adapter.render(frame));
    TEST_ASSERT_TRUE(environment.panel.ram() == before);
    environment.panel.nack = nullptr;
    TEST_ASSERT_FALSE(adapter.render(frame));
    TEST_ASSERT_TRUE(environment.panel.ram() == before);
    // Only an invalidation sends the frame again.
    adapter.invalidate(); TEST_ASSERT_TRUE(adapter.render(frame));
    TEST_ASSERT_TRUE(environment.panel.ram() != before);
}
int main()
{
    UNITY_BEGIN();
    RUN_TEST(test_canvas_forwards_driver_operations_and_results);
    RUN_TEST(test_canvas_draw_arguments_and_coordinate_conversion);
    RUN_TEST(test_initialize_success_and_failure);
    RUN_TEST(test_first_unchanged_changed_and_invalidated_frames);
    RUN_TEST(test_disconnection_stops_drawing_even_for_unchanged_frame);
    RUN_TEST(test_reset_recovery_redraws_same_frame);
    RUN_TEST(test_failed_reset_and_retry_boundary_with_rollover);
    RUN_TEST(test_nack_does_not_clear_bus_and_stale_timeout_is_cleared);
    RUN_TEST(test_timeout_recovery_on_free_bus);
    RUN_TEST(test_timeout_bus_clear_and_stop_sequence);
    RUN_TEST(test_post_clear_probe_reset_and_final_probe_failures);
    RUN_TEST(test_stuck_bus_latches_and_recovers_after_release);
    RUN_TEST(test_initialize_clears_recovery_latch_timing_and_previous_frame);
    RUN_TEST(test_display_nack_leaves_the_panel_stale_while_the_frame_counts_as_drawn);
    return UNITY_END();
}
