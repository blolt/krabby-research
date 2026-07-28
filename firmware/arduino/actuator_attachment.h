#pragma once

#include <stdint.h>

enum ActuatorAttachmentState
{
    ATTACHMENT_UNKNOWN,
    ATTACHMENT_ATTACHED,
    ATTACHMENT_DISCONNECTED
};

struct ActuatorAttachmentTracker
{
    ActuatorAttachmentState state;
    uint8_t attachedEvidenceCount;
    uint8_t disconnectedEvidenceCount;

    ActuatorAttachmentTracker()
        : state(ATTACHMENT_UNKNOWN),
          attachedEvidenceCount(0),
          disconnectedEvidenceCount(0)
    {
    }

    void reset()
    {
        state = ATTACHMENT_UNKNOWN;
        attachedEvidenceCount = 0;
        disconnectedEvidenceCount = 0;
    }

    void update(
        bool currentEvidenceUsable,
        int measuredCurrent,
        int currentPresentFloor,
        uint8_t requiredConsecutiveSamples)
    {
        if (!currentEvidenceUsable || requiredConsecutiveSamples == 0)
        {
            attachedEvidenceCount = 0;
            disconnectedEvidenceCount = 0;
            return;
        }

        if (measuredCurrent >= currentPresentFloor)
        {
            disconnectedEvidenceCount = 0;
            if (attachedEvidenceCount < requiredConsecutiveSamples)
                ++attachedEvidenceCount;
            if (attachedEvidenceCount >= requiredConsecutiveSamples)
                state = ATTACHMENT_ATTACHED;
            return;
        }

        attachedEvidenceCount = 0;
        if (disconnectedEvidenceCount < requiredConsecutiveSamples)
            ++disconnectedEvidenceCount;
        if (disconnectedEvidenceCount >= requiredConsecutiveSamples)
            state = ATTACHMENT_DISCONNECTED;
    }

    bool isAttachedOrUnknown() const
    {
        return state != ATTACHMENT_DISCONNECTED;
    }
};

static bool actuatorConnectionIsValid(
    bool positionValid,
    const ActuatorAttachmentTracker &attachment)
{
    return positionValid && attachment.isAttachedOrUnknown();
}
