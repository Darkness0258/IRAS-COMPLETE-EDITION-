IRAS RC7 CANDIDATE — COGNITIVE CORE
===================================

This package is cumulative. If RC6 Automation + Wake Voice is not already installed,
apply-iras-rc7.ps1 installs the bundled RC6 update first and then applies RC7.

WHAT RC7 ADDS
-------------
1. Self-directed agency (bounded)
   - Persistent drives: completion, reliability, learning, curiosity, creativity, efficiency.
   - IRAS creates internal intentions from its goals and learning state.
   - It can generate associative idea/creation briefs.
   - Intentions do NOT grant themselves Windows or account authority.

2. Continuous nature
   - A low-cost deterministic cognition loop runs continuously with v5 services.
   - Default cognitive tick: 10 seconds.
   - Change with IRAS_V5_COGNITION_TICK_SECONDS.
   - It does not continuously call an LLM.

3. Scalable / effectively unbounded memory
   - No application-level memory item count cap.
   - SQLite locally, PostgreSQL when DATABASE_URL is configured.
   - Real limit = available storage/database resources.

4. Neuron-style memory
   - Concepts become persistent neuron nodes.
   - Memories connect to neurons with weights.
   - Neuron-to-neuron synapses form through co-occurrence.
   - Feedback strengthens/weakens associations.

5. Neural signal profile
   - Biological reference speed: 75 m/s (inside the requested 50–100 m/s range).
   - Actual software propagation is NOT slowed down; it runs at hardware speed.

6. Inductive + deductive reasoning
   - Deductive fuzzy rule inference from facts/rules.
   - Inductive feature -> outcome hypothesis learning from examples.
   - Associative memory evidence is included in reasoning.

7. Learning
   - Reinforcement adjusts confidence, importance and associative weights.
   - Automation success/failure becomes learning feedback automatically.

8. Fuzzy logic
   - Intention willingness uses graded confidence, utility, urgency, risk and novelty.

NEW TOOLS
---------
v5_cognition_status
v5_cognition_drives
v5_cognition_set_drive
v5_cognition_remember
v5_cognition_recall
v5_cognition_propagate
v5_cognition_reason
v5_cognition_learn
v5_cognition_intentions
v5_cognition_create_intention
v5_cognition_resolve_intention
v5_cognition_create_idea
v5_cognition_tick

INSTALL
-------
Extract this ZIP, open PowerShell in the extracted folder and run:

  .\apply-iras-rc7.ps1 -Repo "D:\Projects\IRAS-complete" -Test

Then run the full existing validation:

  cd D:\Projects\IRAS-complete
  .\.venv\Scripts\Activate.ps1
  .\run-v500-validation.ps1

STATUS CHECK AFTER STARTING IRAS
--------------------------------
Ask IRAS to use v5_cognition_status, or inspect v5 status. It should report:
- continuous = true
- memory_policy = no_application_item_cap_storage_bounded
- reasoning = inductive, deductive, fuzzy
- biological_reference_signal_speed_mps = 75.0

ROLLBACK
--------
  .\restore-iras-rc7.ps1 -Repo "D:\Projects\IRAS-complete"

If this package also installed RC6 and you want RC6 removed too:
  .\rc6\restore-iras-rc6.ps1 -Repo "D:\Projects\IRAS-complete"

IMPORTANT REALITY CHECK
-----------------------
"Unlimited memory" cannot literally exceed physical storage. RC7 removes an artificial
application-level item limit and uses persistent scalable storage. Likewise, biological
50–100 m/s transmission is a human-neuron property; IRAS keeps a 75 m/s reference profile
but actual software execution remains much faster.

AUTONOMY BOUNDARY
-----------------
RC7 does not turn cognition into a permission bypass. External state changes still pass
through ToolRegistry permissions, RC6 automation authority caps, Remote authentication,
local Master Control where required, audit logging, Emergency Stop, filesystem boundaries,
and Windows/UAC.
