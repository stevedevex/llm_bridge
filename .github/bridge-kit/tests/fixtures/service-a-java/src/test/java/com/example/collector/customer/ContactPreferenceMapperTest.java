package com.example.collector.customer;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.example.shared.model.ContactPreferenceSlot;
import org.junit.jupiter.api.Test;

class ContactPreferenceMapperTest {

    @Test
    void mapsTheBestTimeAsSaid() {
        ContactPreferenceSlot slot = new ContactPreferenceMapper().map(Responses.customer("weekday mornings"));

        assertEquals("weekday mornings", slot.getContactTime());
    }
}
