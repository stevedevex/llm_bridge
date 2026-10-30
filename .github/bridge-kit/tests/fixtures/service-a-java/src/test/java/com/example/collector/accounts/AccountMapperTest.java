package com.example.collector.accounts;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.example.shared.model.Account;
import org.junit.jupiter.api.Test;

class AccountMapperTest {

    @Test
    void anAccountClosedUpstreamIsClosed() {
        Account account = new AccountMapper().map(Directory.account("AC-1002", "C"));

        assertEquals(Account.Status.CLOSED, account.getStatus());
    }
}
