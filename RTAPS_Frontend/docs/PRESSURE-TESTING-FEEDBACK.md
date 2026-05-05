# Pressure Testing Procedure - Feedback Explanations

This document provides adaptive feedback explanations for the Pressure Testing procedure based on workload probability (p).

## Workload Classification
- **Low (p = 0-0.3)**: No additional feedback
- **Medium (p = 0.3-0.7)**: Simple explanation
- **High (p = 0.7-1)**: Full explanation

---

## Step 1: Notify Control Room

### Medium Workload (Simple Explanation)
- Ensures CRO is aware of testing activities
- Establishes communication protocol for coordination

### High Workload (Full Explanation)

**Why:**
- CRO monitors entire process - needs to know about testing that affects operations and can prepare for bypass operations
- Establishes communication channel for coordination during test and documents testing activity for operational records

**What:**
- Communication plan is established covering testing process, timeline, check-in points, documentation requirements, and CRO support needed

**How:**
- Notify Control Room before starting testing with communication plan in place
- Cover Testing Process and any needed documentation, establishing check-in points and expectations for CRO support

---

## Step 2: Place PST-111 in Override/Bypass

### Medium Workload (Simple Explanation)
- Bypass prevents safety shutdown during testing
- Allows controlled pressure application without triggering trips

### High Workload (Full Explanation)

**Why:**
- Testing will intentionally exceed normal operating pressure to test switch - without bypass, system would shutdown during test, preventing completion
- Safety systems require authorized access (typically CRO level) - prevents unauthorized bypass that could create unsafe conditions

**What:**
- PST is placed in Override/Bypass mode, temporarily disabling automatic safety shutdown
- System can now be tested without triggering shutdowns

**How:**
- Request CRO to place PST-111 (or PST-112 for Train 2) in Override/Bypass
- Have CRO verify when shutdown is in bypass and verify bypass is actually active through visual/DCS confirmation before proceeding

---

## Step 3: Close PST-111 Isolation Valves

### Medium Workload (Simple Explanation)
- Isolates pressure switch from process pressure
- Allows external test pressure application without process interference

### High Workload (Full Explanation)

**Why:**
- Process pressure would interfere with test pressure readings; isolation allows controlled test pressure application
- Safety: Isolates test area from live process; typically two isolation valves for double block and bleed safety

**What:**
- Isolation valves are closed, creating barrier between process and test connection
- Allows test pressure to be applied independently without process interference

**How:**
- Close PST-111 isolation valves (or PST-112 for Train 2), turning valve handles clockwise to close
- Verify fully closed (check handle position, no pressure indication) and ensure both valves are closed

---

## Step 4: Depressurize Test Connection

### Medium Workload (Simple Explanation)
- Ensures test connection is at atmospheric pressure
- Prevents pressure lock that could affect test accuracy

### High Workload (Full Explanation)

**Why:**
- Residual pressure in test connection would add to test pressure, causing false readings and leading to incorrect switch calibration
- Safety: Prevents sudden pressure release when connecting test source

**What:**
- Test connection is depressurized to atmospheric pressure (zero pressure)
- This ensures accurate test pressure readings and safe equipment connection

**How:**
- Use pressure gauge on test connection to verify zero pressure (atmospheric)
- Visual check: No hissing or pressure indication; verify completely before proceeding

---

## Step 5: Connect External Pressure Testing Source

### Medium Workload (Simple Explanation)
- Provides controlled pressure source for testing
- Allows precise pressure application and measurement

### High Workload (Full Explanation)

**Why:**
- Process pressure is variable and uncontrolled - external source provides precise control needed for switch testing
- Allows testing at specific pressure setpoints with controlled, measurable pressure independent of process

**What:**
- External pressure source is connected to test connection
- Provides controlled pressure for accurate switch testing with gradual pressure increase/decrease capability

**How:**
- Connect external pressure source (hydraulic pump, nitrogen cylinder, or compressed air) with proper fittings to prevent leaks
- Install pressure gauge to monitor applied pressure and include relief valve for safety
- After connection, verify no leaks before proceeding - leaks affect test accuracy and create safety hazard

---

## Step 6: Increase Pressure Until PSH Trips

### Medium Workload (Simple Explanation)
- PSH (Pressure Safety High) should trip at setpoint
- Verifies high-pressure protection is functioning

### High Workload (Full Explanation)

**Why:**
- PSH protects equipment from over-pressurization and initiates shutdown if pressure exceeds safe operating limit - critical safety function
- Regulatory requirement (BSEE: monthly testing) ensures safety system will function in emergency and verifies switch calibration

**What:**
- Pressure is gradually increased until PSH switch trips at its setpoint
- Exact trip pressure is noted and compared to setpoint (should match within tolerance, typically ±2-5%)

**How:**
- Gradually increase pressure (prevents overshoot) while monitoring pressure gauge continuously
- Note exact pressure when switch trips and compare to setpoint
- Wear PPE (gloves, safety glasses) and have CRO verify when shutdown is active

---

## Step 7: Reduce Pressure Until PSH Resets

### Medium Workload (Simple Explanation)
- PSH must reset before testing PSL
- Verifies switch returns to normal state

### High Workload (Full Explanation)

**Why:**
- PSH is latching switch - stays tripped until pressure drops below reset point; must reset before testing low-pressure switch (PSL)
- If switch doesn't reset, it indicates switch malfunction, mechanical binding, or calibration issue

**What:**
- Pressure is reduced until PSH switch resets
- Reset point is typically 5-10% below trip point (hysteresis) - prevents switch from chattering near setpoint

**How:**
- Gradually reduce pressure from trip point while monitoring pressure gauge
- Note exact pressure when switch resets and have CRO verify shutdown is reset

---

## Step 8: Reduce Pressure Until PSL Trips

### Medium Workload (Simple Explanation)
- PSL (Pressure Safety Low) protects against under-pressurization
- Verifies low-pressure protection is functioning

### High Workload (Full Explanation)

**Why:**
- PSL protects against under-pressurization conditions and prevents equipment damage from low pressure (vacuum, leaks)
- Regulatory compliance requirement - safety system must respond to low-pressure conditions

**What:**
- Pressure is reduced until PSL switch trips at its setpoint
- Switch initiates shutdown when low-pressure trip point is reached

**How:**
- Continue reducing pressure from PSH reset point while monitoring pressure gauge continuously
- Note exact pressure when PSL trips, compare to setpoint, and have CRO verify when shutdown is active

---

## Step 9: Reduce Test Pressure Completely

### Medium Workload (Simple Explanation)
- Returns system to atmospheric pressure
- Prepares for test equipment disconnection

### High Workload (Full Explanation)

**Why:**
- Safety: No residual pressure when disconnecting test equipment prevents sudden pressure release during disconnection
- Disconnecting under pressure can cause violent pressure release, equipment damage, or personnel injury

**What:**
- All test pressure is released, returning system to atmospheric pressure
- System is now in safe state for equipment disconnection

**How:**
- Gradually reduce pressure to zero (atmospheric) and verify pressure gauge reads zero
- Confirm safe to disconnect equipment and have CRO verify when shutdown is reset

---

## Step 10: Disconnect Test Pressure Source

### Medium Workload (Simple Explanation)
- Removes test equipment
- Prepares system for return to normal operation

### High Workload (Full Explanation)

**Why:**
- Test equipment is no longer needed and must be removed before restoring process connections
- If present, closing test valve before disconnecting prevents any residual pressure release

**What:**
- External pressure source is disconnected from test connection
- System is prepared for restoration of process connections

**How:**
- Verify zero pressure before disconnecting and close test valve first (if present) to isolate
- Disconnect slowly to check for residual pressure and use proper tools and techniques

---

## Step 11: Open PST-111 Isolation Valve

### Medium Workload (Simple Explanation)
- Restores process connection to pressure switch
- Returns switch to normal monitoring function

### High Workload (Full Explanation)

**Why:**
- Restores process pressure connection to switch and returns switch to normal monitoring mode
- Test equipment must be removed first - prevents mixing test pressure with process pressure

**What:**
- Isolation valve is opened, restoring process connection to pressure switch
- Switch returns to normal monitoring function

**How:**
- Open PST-111 isolation valve (or PST-112 for Train 2) slowly to allow gradual pressure equalization
- Monitor for proper pressure restoration

---

## Step 12: Verify Pressure Increases to Safe Operating Limits

### Medium Workload (Simple Explanation)
- Confirms system is returning to normal operation
- Validates pressure switch is monitoring correctly

### High Workload (Full Explanation)

**Why:**
- Confirms system integrity after testing and validates that isolation didn't cause issues
- Pressure should be above PSL setpoint and below PSH setpoint - within normal operating range

**What:**
- Process pressure is restoring and within normal operating range
- Switch is responding to process pressure correctly with no leaks or abnormal conditions

**How:**
- Verify process pressure is restoring and check pressure is within normal operating range (above PSL, below PSH)
- Monitor switch response to process pressure and notify CRO testing is complete

---

## Step 13: Remove Override/Bypass

### Medium Workload (Simple Explanation)
- Restores automatic safety protection
- Returns system to normal safety mode

### High Workload (Full Explanation)

**Why:**
- Testing is complete - no longer need to prevent shutdowns; must restore automatic safety protection
- System is unprotected if bypass remains active - safety hazard

**What:**
- Bypass is removed, restoring automatic safety protection
- System returns to normal safety mode with full interlocks active

**How:**
- Request CRO to remove Override/Bypass
- CRO ensures proper restoration of safety systems and verifies safety systems are active

---

## Step 14: Notify CRO Equipment Ready for Service

### Medium Workload (Simple Explanation)
- Final communication confirms testing complete
- Documents system status for operations

### High Workload (Full Explanation)

**Why:**
- Confirms all testing steps completed and documents system is ready for normal operation
- Completes communication protocol established in Step 1; notification may be logged for compliance and operational records

**What:**
- CRO is informed that testing completed successfully, all safety systems restored, equipment ready for normal operation, and any issues or concerns noted

**How:**
- Notify the Control Room Operator that equipment is ready to return to service
- Provide summary of testing results and report any issues or concerns
