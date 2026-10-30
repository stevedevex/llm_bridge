package com.example.collector.audit;

/** Logs each upstream call's outcome. */
public class CallLog {

    public void record(CallResult result) {
        System.out.println(result.getUpstream() + ": " + result.getStatus());
    }
}
