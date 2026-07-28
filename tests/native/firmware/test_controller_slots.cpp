#include "controller_slots.h"
#include "unity.h"

void setUp() {}
void tearDown() {}

static void check(
    BoardRole role,
    bool hasLeft,
    bool hasRight,
    bool ownsDisplay,
    bool frontLocal,
    bool leftAssigned,
    bool rightAssigned
) {
    const ControllerSlotLinks slots =
        controllerSlotLinks(role, hasLeft, hasRight);
    TEST_ASSERT_EQUAL(ownsDisplay, slots.displayOwner);
    TEST_ASSERT_EQUAL(frontLocal, slots.frontLocal);
    TEST_ASSERT_EQUAL(leftAssigned, slots.leftAssigned);
    TEST_ASSERT_EQUAL(rightAssigned, slots.rightAssigned);
}

static void test_every_role_and_link_permutation() {
    const BoardRole roles[] = {
        ROLE_UNKNOWN, ROLE_FRONT, ROLE_LEFT, ROLE_RIGHT
    };

    for (unsigned int roleIndex = 0; roleIndex < 4; ++roleIndex) {
        const BoardRole role = roles[roleIndex];
        const bool ownsDisplay =
            role == ROLE_UNKNOWN || role == ROLE_FRONT;
        TEST_ASSERT_EQUAL(
            ownsDisplay, roleOwnsControllerDisplay(role)
        );

        for (unsigned int links = 0; links < 4; ++links) {
            const bool hasLeft = (links & 1) != 0;
            const bool hasRight = (links & 2) != 0;
            check(
                role,
                hasLeft,
                hasRight,
                ownsDisplay,
                ownsDisplay,
                ownsDisplay && hasLeft,
                ownsDisplay && hasRight
            );
        }
    }
}

static void test_asymmetric_follower_links_are_not_swapped_or_coupled() {
    check(ROLE_FRONT, true, false, true, true, true, false);
    check(ROLE_FRONT, false, true, true, true, false, true);
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_every_role_and_link_permutation);
    RUN_TEST(test_asymmetric_follower_links_are_not_swapped_or_coupled);
    return UNITY_END();
}
