# Configurable Application Settings — Clarification Questions

I detected one ambiguity from combining two of your answers that needs resolving before I write the requirements document.

## Ambiguity 1: "Wait for poll cycle to finish" vs. "no automated restart"

You answered Question 2 = **C** (no automated restart — saving a setting shows a "Restart required" banner with a manual command; there is no automated trigger that actually restarts anything) and Question 4 = **B** (wait for the current poll cycle to finish before restarting).

Question 4 was written assuming something in the system decides *when* to actually perform the restart — which only applies if the restart is automated. Since Question 2 ruled that out, "wait for the current poll cycle to finish" needs a different, concrete meaning: is it about what the **banner itself does**, or is it just advice to the human running the command?

### Clarification Question 1
When `ingestion-worker` settings are changed and a restart is needed, how should "wait for the current poll cycle to finish" actually manifest in a manual-restart (Question 2 = C) design?

A) The Settings page shows a live "worker busy / idle" indicator (backed by the existing heartbeat file or a new status check) — the "Restart required" banner/command is only presented as safe to run once the worker is confirmed idle; if it's mid-cycle, the banner says "wait, worker is currently processing" instead

B) The banner appears immediately regardless of worker state, with static advisory text ("we recommend waiting a few seconds for any in-progress statement processing to finish before restarting") — no live status check, just a warning

C) This distinction doesn't matter enough to build — treat it the same as Question 4 = A (restart is safe any time, the poll loop already tolerates interruption) and drop the "wait" requirement entirely

D) Other (please describe after [Answer]: tag below)

[Answer]:A
