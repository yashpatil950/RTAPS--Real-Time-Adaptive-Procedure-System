# Column Flushing Procedure - Feedback Explanations

This document provides adaptive feedback explanations for the Column Flushing procedure based on workload probability (p).

## Workload Classification
- **Low (p = 0-0.3)**: No additional feedback
- **Medium (p = 0.3-0.7)**: Simple explanation
- **High (p = 0.7-1)**: Full explanation

---

## Step 1: Place ILIC-101 in Manual Control

### Medium Workload (Simple Explanation)
- Manual control prevents automatic level adjustments during flushing
- Ensures safe isolation of column from process control

### High Workload (Full Explanation)

**Why:**
- Automatic control would fight against your draining operation - controller would try to maintain level by opening valves, creating safety hazard
- Manual mode locks controller output, preventing interference with maintenance work

**What:**
- Controller is placed in manual mode, locking its output and preventing automatic valve movements
- This isolates the column from automatic process control, allowing safe manual intervention

**How:**
- Request CRO to place ILIC-101 (or ILIC-102 for Train 2) in Manual Control
- Grab radios and hand tools as required before starting this step

---

## Step 2: Wait for CRO Confirmation

### Medium Workload (Simple Explanation)
- Verification ensures controller is actually in manual mode
- Prevents proceeding with unsafe conditions

### High Workload (Full Explanation)

**Why:**
- Visual indicators can be misleading or delayed; CRO has real-time DCS view of actual controller state
- Prevents false assumption that could lead to dangerous situation

**What:**
- CRO verifies that controller output is locked, no automatic valve movements are occurring, and system is ready for manual intervention

**How:**
- Wait for explicit verbal or radio confirmation from CRO
- Do not proceed based on visual indicators alone

---

## Step 3: Close Lower Isolation Valve (M101-9)

### Medium Workload (Simple Explanation)
- Isolates column bottom to prevent process fluid from entering during flushing
- Creates controlled drainage path

### High Workload (Full Explanation)

**Why:**
- Prevents process fluids from flowing into column during maintenance and protects personnel from exposure to hot, pressurized, or hazardous fluids
- Bottom connection is where fluid accumulates - closing it first prevents new fluid from entering while you drain

**What:**
- Lower isolation valve is closed, creating barrier between column and process at bottom connection
- This allows safe depressurization and drainage without process interference

**How:**
- Close manual column valve M101-9 (lower isolation valve on level column), turning handle clockwise to close
- Verify valve is fully closed (check handle position, listen for no flow sound)

---

## Step 4: Close Upper Isolation Valve (M101-11)

### Medium Workload (Simple Explanation)
- Completes column isolation from process
- Prevents fluid entry from top connections

### High Workload (Full Explanation)

**Why:**
- Completes full isolation of column from process and prevents vapor or liquid from entering from overhead connections
- If closed first, pressure could build in column - closing lower first allows any trapped pressure to vent upward

**What:**
- Upper isolation valve is closed, completing full isolation of column from process
- With both valves closed, column is now isolated from process - safe for maintenance work

**How:**
- Close manual column valve M101-11 (upper isolation valve on level column), turning handle clockwise to close
- Verify both upper and lower valves are fully closed before proceeding

---

## Step 5: Remove Plug

### Medium Workload (Simple Explanation)
- Provides access point for drainage
- Standard maintenance procedure

### High Workload (Full Explanation)

**Why:**
- Creates opening for fluid drainage from float cage and allows connection of drain hose or bucket for controlled drainage

**What:**
- Plug is removed from drain connection at bottom of float cage, creating the opening needed for fluid drainage

**How:**
- Locate plug on drain connection at bottom of float cage
- Crack plug slowly first to verify no trapped pressure, then use proper tools to remove completely

---

## Step 6: Open Drain Valve on Float Cage Bottom

### Medium Workload (Simple Explanation)
- Allows accumulated fluids to drain from float cage
- Removes water, sediment, and contaminants

### High Workload (Full Explanation)

**Why:**
- Float cage accumulates water, sediment, and process contaminants that interfere with float operation, cause corrosion, or jam float causing false level readings
- Regular flushing prevents equipment failure and maintains accurate level measurement

**What:**
- Drain valve is opened, allowing accumulated fluids to flow out of float cage
- This removes water, sediment, and contaminants that interfere with level measurement accuracy

**How:**
- Open drain valve on bottom of float cage and monitor flow to ensure proper drainage
- Be prepared for potential trapped pressure release

---

## Step 7: Drain Fluids into Bucket with Secondary Containment

### Medium Workload (Simple Explanation)
- Secondary containment prevents environmental spills
- Proper disposal required for process fluids

### High Workload (Full Explanation)

**Why:**
- Process fluids are often hazardous (hydrocarbons, chemicals) - spills can cause environmental violations and safety hazards; regulatory requirement for secondary containment
- Column may contain pressurized fluids even after isolation - sudden release can cause violent fluid ejection

**What:**
- Fluids (water, hydrocarbons, sediment) are drained into bucket with secondary containment
- This collects all drained material for proper disposal per environmental regulations

**How:**
- Position bucket with secondary containment under drain valve and wear gloves and safety glasses (PPE)
- Monitor flow rate (sudden increase indicates pressure release) and bucket capacity to prevent overflow

---

## Step 8: Remove Top Plug and Vent Pressure

### Medium Workload (Simple Explanation)
- Venting verifies complete drainage
- Slow venting prevents sudden pressure release

### High Workload (Full Explanation)

**Why:**
- Verifies all fluids have drained (if air/vapor comes out, column is empty) and releases any trapped pressure or vapor
- Sudden pressure release can cause violent fluid ejection, equipment damage, or safety hazard to personnel

**What:**
- Top plug is removed and vent is opened, allowing pressure to escape
- If only vapor/air comes out = drainage complete; if liquid comes out = drainage incomplete, continue draining

**How:**
- Remove plug from top of float cage and open vent slowly, releasing pressure a little at a time
- Vent to location away from personnel and monitor what comes out: vapor/air indicates complete drainage

---

## Step 9: Close Vent and Reinstall Plug

### Medium Workload (Simple Explanation)
- Seals column after verification
- Prepares for refilling operation

### High Workload (Full Explanation)

**Why:**
- Seals column to prevent contamination during refill and maintains controlled environment for level restoration
- Prevents air ingress that could affect level measurement

**What:**
- Vent valve is closed and plug is reinstalled, sealing the top of float cage
- Column is now sealed and ready for refilling operation

**How:**
- Close the vent valve completely, clean plug threads, and reinstall plug - tighten to specification (not too tight)
- Verify no leaks after installation

---

## Step 10: Close Drain Valve and Reinstall Plug

### Medium Workload (Simple Explanation)
- Seals bottom connection
- Completes column sealing for refill

### High Workload (Full Explanation)

**Why:**
- Prevents fluid loss during refill and ensures proper level restoration
- Bottom plug is last to be installed (after drain closed) - ensures any remaining fluid doesn't leak out

**What:**
- Drain valve is closed and bottom plug is reinstalled
- Column is now completely sealed and ready for refilling

**How:**
- Close the drain valve completely, clean plug threads, and reinstall bottom plug ensuring complete seal
- Check for leaks around plug and valve before proceeding

---

## Step 11: Open Upper Isolation Valve (M101-11)

### Medium Workload (Simple Explanation)
- Restores process connection from top
- Allows column to refill with process fluid

### High Workload (Full Explanation)

**Why:**
- Allows process fluid to enter from top (normal flow direction) and prevents air entrapment by filling from top down
- Opening lower valve first could cause rapid fill or pressure issues

**What:**
- Upper isolation valve is opened, restoring process connection from top
- Process fluid flows in from overhead connections, allowing column to fill gradually

**How:**
- Open manual column valve M101-11 (upper isolation valve on level column) slowly to allow gradual pressure equalization
- Monitor for proper fluid flow and level rise

---

## Step 12: Open Lower Isolation Valve (M101-9)

### Medium Workload (Simple Explanation)
- Completes restoration of process connections
- Returns column to normal operation

### High Workload (Full Explanation)

**Why:**
- Restores normal process flow path and allows column to function in normal operation mode
- Column should be partially filled before opening bottom - prevents sudden flow surges

**What:**
- Lower isolation valve is opened, completing restoration of process connections
- Column now connected to process at both ends with normal flow path restored

**How:**
- Open manual column valve M101-9 (lower isolation valve on level column) after upper valve and after column has partially filled
- Open slowly to allow gradual return to normal operation

---

## Step 13: Observe Fluid Rise and ILIC Return to Normal

### Medium Workload (Simple Explanation)
- Verifies column is refilling properly
- Confirms level controller returning to automatic operation

### High Workload (Full Explanation)

**Why:**
- Confirms flushing was successful (no blockages) and verifies equipment integrity after maintenance
- Ensures level measurement is working correctly and validates that system is ready for automatic control

**What:**
- Fluid level rises in column (visual or gauge indication) and ILIC controller responds to level changes
- Normal operating condition: Level stabilizes at setpoint, controller maintains level automatically, no alarms

**How:**
- Observe fluid level rising in column and monitor ILIC controller response to level changes
- Check for no leaks from connections or valves and verify smooth transition back to normal operation

---

## Step 14: Dispose of Collected Fluids in Wet Oil Tank

### Medium Workload (Simple Explanation)
- Proper disposal prevents environmental issues
- Wet Oil Tank is designated collection point

### High Workload (Full Explanation)

**Why:**
- Designated collection point for process fluids meets environmental disposal requirements and allows recovery of hydrocarbons for reprocessing
- Improper disposal can result in environmental violations, safety hazards, and lost product recovery

**What:**
- Collected fluids (water, hydrocarbons, sediment) are transferred to Wet Oil Tank
- May contain recoverable oil that can be reprocessed

**How:**
- Transfer fluids from secondary containment to Wet Oil Tank
- Document disposal (may be required for environmental compliance) and clean secondary containment for next use
