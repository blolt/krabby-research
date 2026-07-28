#pragma once

enum BoardRole { ROLE_UNKNOWN, ROLE_FRONT, ROLE_LEFT, ROLE_RIGHT };

struct ControllerSlotLinks
{
    bool displayOwner;
    bool frontLocal;
    bool leftAssigned;
    bool rightAssigned;
};

static bool roleOwnsControllerDisplay(BoardRole role)
{
    return role == ROLE_FRONT || role == ROLE_UNKNOWN;
}

// Role election establishes display ownership and the identity of each
// controller slot. Telemetry freshness is deliberately applied later.
static ControllerSlotLinks controllerSlotLinks(
    BoardRole role,
    bool hasLeftLink,
    bool hasRightLink)
{
    const bool ownsDisplay = roleOwnsControllerDisplay(role);
    ControllerSlotLinks slots = {
        ownsDisplay,
        ownsDisplay,
        ownsDisplay && hasLeftLink,
        ownsDisplay && hasRightLink
    };
    return slots;
}
