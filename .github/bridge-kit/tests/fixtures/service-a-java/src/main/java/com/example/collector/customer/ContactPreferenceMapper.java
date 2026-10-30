package com.example.collector.customer;

import com.example.shared.model.ContactPreferenceSlot;
import com.example.upstream1.model.CustomerResponse;

/** Fills the customer API's slot from upstream-1's GET /customers/{id}. */
public class ContactPreferenceMapper {

    public ContactPreferenceSlot map(CustomerResponse response) {
        ContactPreferenceSlot slot = new ContactPreferenceSlot();
        if (response.getContactPreference() == null) {
            return slot;
        }
        var preference = response.getContactPreference();
        slot.setEmail(preference.getEmail());
        slot.setPreferredLanguage(preference.getLanguage() == null ? null : preference.getLanguage().toLowerCase());
        slot.setContactTime(preference.getBestTime());
        slot.setMarketingConsent("Y".equals(preference.getMarketingFlag()));
        if (preference.getUpdatedAt() != null) {
            slot.setUpdatedDate(preference.getUpdatedAt().toLocalDate());
        }
        return slot;
    }
}
