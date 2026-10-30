package com.example.collector.accounts;

import com.example.shared.model.Account;
import com.example.directory.model.DirectoryAccount;

/** Fills an account's identity from the customer directory. */
public class AccountMapper {

    public Account map(DirectoryAccount source) {
        Account account = new Account();
        account.setAccountId(source.getId());
        account.setProductType(ProductTypes.lookup(source.getProductCode()));
        account.setStatus(AccountStatuses.lookup(source.getStatusCode()));
        account.setJoint(source.getHolderCount() > 1);
        return account;
    }
}
